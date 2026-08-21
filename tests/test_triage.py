import base64
import io

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import settings
from app.llm import ChatResult
from app.main import app
from app.safety import RED_FLAG_RULES, detect_emergency
from app.triage import TriageResult, Urgency, parse_triage_result

client = TestClient(app)

CHAT_URL = "/v1/chat"
TRIAGE_URL = "/v1/triage"


def _tiny_jpeg_b64(size: tuple[int, int] = (64, 64)) -> str:
    img = Image.new("RGB", size, (180, 60, 60))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode()


@pytest.mark.parametrize(
    "phrase",
    [
        "I have chest pain",
        "I can't breathe",
        "my face is drooping",
        "I want to end my life",
        "I am bleeding heavily",
        "my throat is swelling",
        "he is having a seizure",
        "she passed out",
    ],
)
def test_detect_emergency_matches_red_flags(phrase):
    assert detect_emergency(phrase) is not None


@pytest.mark.parametrize("message", ["Hello", "I have a mild headache", "my knee hurts a bit", "thanks"])
def test_detect_emergency_ignores_benign_text(message):
    assert detect_emergency(message) is None


def test_detect_emergency_is_case_insensitive():
    assert detect_emergency("CHEST PAIN") == "chest pain"


def test_urgency_enum_has_four_levels():
    assert [u.value for u in Urgency] == ["emergency", "urgent", "routine", "self_care"]


def test_parse_triage_result_full_schema():
    raw = (
        '{"urgency": "urgent", "red_flags": ["spreading redness"], '
        '"text_findings": ["rash on left arm for two days"], '
        '"image_findings": ["raised red rash with clear borders"], '
        '"reasoning": "localized rash, no systemic signs"}'
    )
    result = parse_triage_result(raw)
    assert result.urgency is Urgency.URGENT
    assert result.red_flags == ["spreading redness"]
    assert result.text_findings == ["rash on left arm for two days"]
    assert result.image_findings == ["raised red rash with clear borders"]
    assert result.reasoning == "localized rash, no systemic signs"


def test_parse_triage_result_defaults_missing_fields():
    result = parse_triage_result('{"urgency": "self_care"}')
    assert result.urgency is Urgency.SELF_CARE
    assert result.red_flags == []
    assert result.text_findings == []
    assert result.image_findings == []
    assert result.reasoning == ""


def test_parse_triage_result_tolerates_fences_and_prose():
    raw = "Here is the result:\n```json\n{\"urgency\": \"emergency\", \"red_flags\": [\"chest pain\"]}\n```\nDone."
    result = parse_triage_result(raw)
    assert result.urgency is Urgency.EMERGENCY
    assert result.red_flags == ["chest pain"]


def test_parse_triage_result_coerces_scalar_findings():
    result = parse_triage_result('{"urgency": "routine", "text_findings": "mild headache"}')
    assert result.text_findings == ["mild headache"]


@pytest.mark.parametrize("bad", ["not json", '{"urgency": "maybe"}', '{"foo": 1}', ""])
def test_parse_triage_result_rejects_invalid(bad):
    with pytest.raises(ValueError):
        parse_triage_result(bad)


def test_triage_result_to_dict_round_trips_schema():
    result = TriageResult(
        urgency=Urgency.ROUTINE,
        red_flags=[],
        text_findings=["headache"],
        image_findings=[],
        reasoning="benign",
    )
    assert result.to_dict() == {
        "urgency": "routine",
        "red_flags": [],
        "text_findings": ["headache"],
        "image_findings": [],
        "reasoning": "benign",
    }


# ---------------------------------------------------------------------------
# /v1/chat triage integration
# ---------------------------------------------------------------------------


def test_emergency_short_circuits_without_model_calls(monkeypatch):
    async def fail(*args, **kwargs):
        raise AssertionError("no model call expected on the emergency path")

    monkeypatch.setattr("app.services.chat.llm.chat", fail)
    monkeypatch.setattr("app.services.chat.llm.triage", fail)
    monkeypatch.setattr("app.services.chat.llm.chat_with_tools", fail)

    response = client.post(CHAT_URL, json={"message": "I have chest pain and can't breathe"})
    assert response.status_code == 200
    body = response.json()
    assert "medical emergency" in body["response"]
    assert "chest pain" in body["response"]
    assert body["session_id"]
    assert body["urgency"] == "emergency"


def test_chat_response_exposes_triage_urgency(monkeypatch):
    async def fake_triage(message, temperature=0.0, image_b64=None):
        return '{"urgency": "self_care"}'

    async def fake_route(messages, tools, temperature=0.7, model=None):
        return ChatResult(content="ok", tool_calls=[])

    monkeypatch.setattr("app.services.chat.llm.triage", fake_triage)
    monkeypatch.setattr("app.services.chat.llm.chat_with_tools", fake_route)

    response = client.post(CHAT_URL, json={"message": "It started after I ran"})
    assert response.status_code == 200
    body = response.json()
    assert body["urgency"] == "self_care"


def test_chat_response_urgency_null_when_triage_disabled(monkeypatch):
    monkeypatch.setattr(settings, "triage_enabled", False)

    async def fake_route(messages, tools, temperature=0.7, model=None):
        return ChatResult(content="ok", tool_calls=[])

    monkeypatch.setattr("app.services.chat.llm.chat_with_tools", fake_route)

    response = client.post(CHAT_URL, json={"message": "hello"})
    assert response.status_code == 200
    body = response.json()
    assert body["urgency"] is None


def test_triage_urgency_reaches_routing_context(monkeypatch):
    captured = {}

    async def fake_triage(message, temperature=0.0, image_b64=None):
        return '{"urgency": "emergency"}'

    async def fake_route(messages, tools, temperature=0.7, model=None):
        captured["messages"] = messages
        return ChatResult(content="ok", tool_calls=[])

    monkeypatch.setattr("app.services.chat.llm.triage", fake_triage)
    monkeypatch.setattr("app.services.chat.llm.chat_with_tools", fake_route)

    response = client.post(CHAT_URL, json={"message": "It started after I ran"})
    assert response.status_code == 200
    assert "urgency level: emergency" in captured["messages"][1]["content"]


def test_triage_disabled_skips_emergency_and_triage(monkeypatch):
    monkeypatch.setattr(settings, "triage_enabled", False)
    called_triage = {"value": False}

    async def fake_triage(message, temperature=0.0, image_b64=None):
        called_triage["value"] = True
        return '{"urgency": "self_care"}'

    async def fake_route(messages, tools, temperature=0.7, model=None):
        return ChatResult(content="ok", tool_calls=[])

    monkeypatch.setattr("app.services.chat.llm.triage", fake_triage)
    monkeypatch.setattr("app.services.chat.llm.chat_with_tools", fake_route)

    response = client.post(CHAT_URL, json={"message": "I have chest pain"})
    assert response.status_code == 200
    assert response.json()["response"] == "ok"
    assert called_triage["value"] is False


@pytest.mark.asyncio
async def test_triage_model_failure_maps_to_503(monkeypatch):
    async def fake_triage(message, temperature=0.0, image_b64=None):
        raise httpx.ConnectError("triage down")

    monkeypatch.setattr("app.services.chat.llm.triage", fake_triage)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(CHAT_URL, json={"message": "hello"})
    assert response.status_code == 503


# ---------------------------------------------------------------------------
# POST /v1/triage
# ---------------------------------------------------------------------------


def test_v1_triage_text_only(monkeypatch):
    async def fake_triage(message, temperature=0.0, image_b64=None):
        assert image_b64 is None
        return '{"urgency": "routine", "text_findings": ["headache for a week"], "reasoning": "persistent but stable"}'

    monkeypatch.setattr("app.services.chat.llm.triage", fake_triage)

    response = client.post(TRIAGE_URL, json={"message": "I've had a mild headache for a week."})
    assert response.status_code == 200
    body = response.json()
    assert body["urgency"] == "routine"
    assert body["text_findings"] == ["headache for a week"]
    assert body["image_findings"] == []
    assert body["red_flags"] == []
    assert body["reasoning"] == "persistent but stable"
    assert body["model"] == settings.triage_model_name
    assert body["source"] == "text"
    assert body["image"] is None


def test_v1_triage_with_image_dispatches_to_vision_model(monkeypatch):
    captured = {}

    async def fake_triage(message, temperature=0.0, image_b64=None):
        captured["image_b64"] = image_b64
        return (
            '{"urgency": "urgent", "red_flags": [], '
            '"text_findings": ["rash appeared yesterday"], '
            '"image_findings": ["red raised rash on the forearm"], '
            '"reasoning": "new spreading rash should be seen soon"}'
        )

    monkeypatch.setattr("app.services.chat.llm.triage", fake_triage)

    b64 = _tiny_jpeg_b64()
    response = client.post(
        TRIAGE_URL,
        json={"message": "This rash showed up yesterday.", "image_b64": b64, "image_mime": "image/jpeg"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["urgency"] == "urgent"
    assert body["source"] == "vision"
    assert body["model"] == settings.vision_triage_model_name
    assert body["image_findings"] == ["red raised rash on the forearm"]
    assert captured["image_b64"]

    image_meta = body["image"]
    assert image_meta["mime"] == "image/jpeg"
    assert image_meta["size_bytes"] > 0
    assert len(image_meta["sha256"]) == 64
    assert image_meta["path"].endswith(".jpg")


def test_v1_triage_red_flag_short_circuits_without_models(monkeypatch):
    async def fail(*args, **kwargs):
        raise AssertionError("no model call expected on the red-flag path")

    monkeypatch.setattr("app.services.chat.llm.triage", fail)

    response = client.post(TRIAGE_URL, json={"message": "I have severe bleeding from a cut"})
    assert response.status_code == 200
    body = response.json()
    assert body["urgency"] == "emergency"
    assert body["red_flags"] == ["severe bleeding"]
    assert body["source"] == "rules"
    assert body["model"] == "hardcoded_rules"


def test_v1_triage_rejects_bad_base64():
    response = client.post(
        TRIAGE_URL,
        json={
            "message": "look at this",
            "image_b64": base64.b64encode(b"not an image").decode(),
            "image_mime": "image/jpeg",
        },
    )
    assert response.status_code == 422


def test_v1_triage_rejects_disallowed_mime():
    response = client.post(
        TRIAGE_URL,
        json={"message": "look", "image_b64": _tiny_jpeg_b64(), "image_mime": "image/gif"},
    )
    assert response.status_code == 422


def test_v1_triage_rejects_partial_image_fields():
    response = client.post(TRIAGE_URL, json={"message": "look", "image_b64": _tiny_jpeg_b64()})
    assert response.status_code == 422
    response = client.post(TRIAGE_URL, json={"message": "look", "image_mime": "image/jpeg"})
    assert response.status_code == 422


def test_v1_triage_rejects_empty_message():
    response = client.post(TRIAGE_URL, json={"message": ""})
    assert response.status_code == 422


def test_v1_triage_disabled_returns_503(monkeypatch):
    monkeypatch.setattr(settings, "triage_enabled", False)
    response = client.post(TRIAGE_URL, json={"message": "hello"})
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_v1_triage_model_failure_maps_to_503(monkeypatch):
    async def fake_triage(message, temperature=0.0, image_b64=None):
        raise httpx.ConnectError("triage down")

    monkeypatch.setattr("app.services.chat.llm.triage", fake_triage)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(TRIAGE_URL, json={"message": "hello"})
    assert response.status_code == 503
