import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.llm import ChatResult
from app.main import app
from app.safety import RED_FLAG_RULES, detect_emergency
from app.triage import parse_triage_urgency

client = TestClient(app)

CHAT_URL = "/chat"


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


@pytest.mark.parametrize("value", ["emergency", "medical", "general"])
def test_parse_triage_urgency_valid_values(value):
    assert parse_triage_urgency(f'{{"urgency": "{value}"}}') == value


def test_parse_triage_urgency_tolerates_fences_and_prose():
    raw = "Here is the result:\n```json\n{\"urgency\": \"emergency\"}\n```\nDone."
    assert parse_triage_urgency(raw) == "emergency"


@pytest.mark.parametrize("bad", ["not json", '{"urgency": "maybe"}', '{"foo": 1}', ""])
def test_parse_triage_urgency_rejects_invalid(bad):
    with pytest.raises(ValueError):
        parse_triage_urgency(bad)


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


def test_triage_urgency_reaches_routing_context(monkeypatch):
    captured = {}

    async def fake_triage(message, temperature=0.0):
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

    async def fake_triage(message, temperature=0.0):
        called_triage["value"] = True
        return '{"urgency": "general"}'

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
    async def fake_triage(message, temperature=0.0):
        raise httpx.ConnectError("triage down")

    monkeypatch.setattr("app.services.chat.llm.triage", fake_triage)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(CHAT_URL, json={"message": "hello"})
    assert response.status_code == 503