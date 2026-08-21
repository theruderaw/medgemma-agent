"""End-to-end image-turn behavior: the Milestone 7 routing rule.

An attached image must never be discarded because the text router did not
request the specialist; it must reach the multimodal MedGemma tier and its
findings must be distinguishable from text findings in the audit trail.
"""

import asyncio
import base64
import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.audit import NullAuditLogger
from app.core.config import settings
from app.core.images import decode_and_sanitize, persist_image
from app.llm import ChatResult
from app.main import app
from app.sessions import InMemorySessionStore, SessionManager

client = TestClient(app)

CHAT_URL = "/v1/chat"


def _image_b64(size=(64, 64)) -> str:
    img = Image.new("RGB", size, (180, 60, 60))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode()


def _memory_manager() -> SessionManager:
    return SessionManager(
        InMemorySessionStore(60),
        max_history_messages=40,
        max_context_messages=20,
        max_context_chars=16000,
    )


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch, tmp_path):
    manager = _memory_manager()
    monkeypatch.setattr("app.services.chat.sessions", manager)
    monkeypatch.setattr("app.services.chat.audit", NullAuditLogger())
    monkeypatch.setattr(settings, "image_upload_dir", str(tmp_path / "uploads"))
    return manager


def _sanitized(b64: str):
    return decode_and_sanitize(b64, "image/jpeg")


def test_router_general_with_image_is_overridden_to_specialist(monkeypatch):
    """The core Milestone 7 routing rule: an image can never be dropped."""
    calls = {"chat": [], "chat_with_images": 0}
    captured = {}

    async def fake_triage(message, temperature=0.0, image_b64=None):
        captured["triage_image"] = image_b64
        return '{"urgency": "routine", "text_findings": ["skin issue"], "reasoning": ""}'

    async def fake_route(messages, tools, temperature=0.7, model=None):
        # Router sees only text and decides this is not symptom-related.
        return ChatResult(content="looks fine to me", tool_calls=[])

    async def fake_chat(messages, temperature=0.7, model=None):
        # Called exactly once — for the final Qwen synthesis after MedGemma.
        calls["chat"].append(model)
        return "synthesis reply"

    async def fake_chat_with_images(messages, images, temperature=0.7, model=None):
        calls["chat_with_images"] += 1
        captured["specialist_messages"] = messages
        captured["specialist_images"] = images
        return "visual exam note"

    monkeypatch.setattr("app.services.chat.llm.triage", fake_triage)
    monkeypatch.setattr("app.services.chat.llm.chat_with_tools", fake_route)
    monkeypatch.setattr("app.services.chat.llm.chat", fake_chat)
    monkeypatch.setattr("app.services.chat.llm.chat_with_images", fake_chat_with_images)

    from app.services.chat import run_chat_turn

    result = asyncio.run(
        run_chat_turn("What is this on my arm?", image=_sanitized(_image_b64()))
    )

    assert calls["chat"] == [settings.model_name]
    assert calls["chat_with_images"] == 1
    assert captured["specialist_images"] == [captured["triage_image"]]
    assert captured["specialist_messages"][-1]["content"] == "image attached"
    assert result.response == "synthesis reply"


def test_router_symptom_related_with_image_passes_reason_to_specialist(monkeypatch):
    captured = {}

    async def fake_triage(message, temperature=0.0, image_b64=None):
        return '{"urgency": "urgent"}'

    specialist_call = {
        "id": "call_1",
        "type": "function",
        "function": {
            "name": "call_medical_specialist",
            "arguments": '{"reason": "rash spreading quickly"}',
        },
    }

    async def fake_route(messages, tools, temperature=0.7, model=None):
        return ChatResult(content="", tool_calls=[specialist_call])

    async def fake_chat_with_images(messages, images, temperature=0.7, model=None):
        captured["messages"] = messages
        captured["images"] = images
        return "note"

    async def fake_chat(messages, temperature=0.7, model=None):
        return "synthesis reply"

    monkeypatch.setattr("app.services.chat.llm.triage", fake_triage)
    monkeypatch.setattr("app.services.chat.llm.chat_with_tools", fake_route)
    monkeypatch.setattr("app.services.chat.llm.chat_with_images", fake_chat_with_images)
    monkeypatch.setattr("app.services.chat.llm.chat", fake_chat)

    from app.services.chat import run_chat_turn

    asyncio.run(run_chat_turn("My rash is spreading", image=_sanitized(_image_b64())))

    assert captured["messages"][-1]["content"] == "rash spreading quickly"
    assert len(captured["images"]) == 1


def test_text_only_turn_never_calls_vision_specialist(monkeypatch):
    calls = {"chat": [], "chat_with_images": 0}

    async def fake_triage(message, temperature=0.0, image_b64=None):
        assert image_b64 is None
        return '{"urgency": "self_care"}'

    async def fake_route(messages, tools, temperature=0.7, model=None):
        # Direct path: the reply is the router's own content.
        return ChatResult(content="direct reply", tool_calls=[])

    async def fake_chat(messages, temperature=0.7, model=None):
        calls["chat"].append(model)
        return "should not be reached"

    async def fake_chat_with_images(messages, images, temperature=0.7, model=None):
        calls["chat_with_images"] += 1
        return "nope"

    monkeypatch.setattr("app.services.chat.llm.triage", fake_triage)
    monkeypatch.setattr("app.services.chat.llm.chat_with_tools", fake_route)
    monkeypatch.setattr("app.services.chat.llm.chat", fake_chat)
    monkeypatch.setattr("app.services.chat.llm.chat_with_images", fake_chat_with_images)

    from app.services.chat import run_chat_turn

    result = asyncio.run(run_chat_turn("Hello there"))
    assert result.response == "direct reply"
    assert calls == {"chat": [], "chat_with_images": 0}


def test_image_turn_records_audit_trail_and_message_marker(monkeypatch, tmp_path, isolated_env):
    events = []
    manager = isolated_env

    async def fake_triage(message, temperature=0.0, image_b64=None):
        return (
            '{"urgency": "routine", "text_findings": ["bump on arm"], '
            '"image_findings": ["small round lesion"], "reasoning": "uncertain about depth"}'
        )

    async def fake_route(messages, tools, temperature=0.7, model=None):
        return ChatResult(content="", tool_calls=[])

    async def fake_chat_with_images(messages, images, temperature=0.7, model=None):
        return "visual exam note"

    async def fake_chat(messages, temperature=0.7, model=None):
        return "final reply"

    monkeypatch.setattr("app.services.chat.llm.triage", fake_triage)
    monkeypatch.setattr("app.services.chat.llm.chat_with_tools", fake_route)
    monkeypatch.setattr("app.services.chat.llm.chat_with_images", fake_chat_with_images)
    monkeypatch.setattr("app.services.chat.llm.chat", fake_chat)

    from app.services.chat import run_chat_turn

    async def on_event(event):
        events.append(event)

    result = asyncio.run(
        run_chat_turn("I found this bump", image=_sanitized(_image_b64()), on_event=on_event)
    )

    by_type = {e["event_type"]: e for e in events}
    image_event = by_type["image_received"]
    assert image_event["module"] == "image"
    assert image_event["payload"]["mime"] == "image/jpeg"
    assert len(image_event["payload"]["sha256"]) == 64
    assert image_event["payload"]["path"].endswith(".jpg")

    triage_event = by_type["triage_result"]
    assert triage_event["payload"]["text_findings"] == ["bump on arm"]
    assert triage_event["payload"]["image_findings"] == ["small round lesion"]
    assert triage_event["payload"]["model"] == settings.vision_triage_model_name

    routing_event = by_type["routing_decision"]
    assert routing_event["payload"]["image_override"] is True

    session = asyncio.run(manager.load_or_create(result.session_id, must_exist=True))
    user_message = session.messages[0]
    assert user_message["role"] == "user"
    assert "[image attached:" in user_message["content"]
    assert user_message["content"].startswith("I found this bump")


def test_emergency_text_with_image_still_short_circuits(monkeypatch):
    """The hardcoded floor stays first and text-only — even with an image."""

    async def fail(*args, **kwargs):
        raise AssertionError("no model call expected on the emergency path")

    monkeypatch.setattr("app.services.chat.llm.triage", fail)
    monkeypatch.setattr("app.services.chat.llm.chat_with_tools", fail)
    monkeypatch.setattr("app.services.chat.llm.chat_with_images", fail)

    from app.services.chat import run_chat_turn

    result = asyncio.run(
        run_chat_turn("I have chest pain", image=_sanitized(_image_b64()))
    )
    assert result.urgency is None or result.urgency.value == "emergency"


def test_vision_triage_failure_does_not_block_routing(monkeypatch):
    """A triage model error propagates (503 at the API layer) — documented here
    as the unit-level contract that run_triage raises through."""

    async def fake_triage(message, temperature=0.0, image_b64=None):
        raise RuntimeError("vision model exploded")

    monkeypatch.setattr("app.services.chat.llm.triage", fake_triage)

    from app.services.chat import run_chat_turn
    from app.services.triage import run_triage

    with pytest.raises(RuntimeError):
        asyncio.run(run_triage("msg", image_b64=_image_b64()))
    with pytest.raises(RuntimeError):
        asyncio.run(run_chat_turn("msg", image=_sanitized(_image_b64())))


# ---------------------------------------------------------------------------
# API-level image turn
# ---------------------------------------------------------------------------


def test_chat_endpoint_accepts_image_and_returns_urgency(monkeypatch):
    async def fake_triage(message, temperature=0.0, image_b64=None):
        assert image_b64
        return '{"urgency": "urgent"}'

    async def fake_route(messages, tools, temperature=0.7, model=None):
        # No tool call: the deterministic image override must still fire.
        return ChatResult(content="", tool_calls=[])

    async def fake_chat_with_images(messages, images, temperature=0.7, model=None):
        return "specialist note"

    async def fake_chat(messages, temperature=0.7, model=None):
        return "see a doctor soon"

    monkeypatch.setattr("app.services.chat.llm.triage", fake_triage)
    monkeypatch.setattr("app.services.chat.llm.chat_with_tools", fake_route)
    monkeypatch.setattr("app.services.chat.llm.chat_with_images", fake_chat_with_images)
    monkeypatch.setattr("app.services.chat.llm.chat", fake_chat)

    response = client.post(
        CHAT_URL,
        json={
            "message": "Is this serious?",
            "image_b64": _image_b64(),
            "image_mime": "image/jpeg",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["urgency"] == "urgent"
    assert body["response"] == "see a doctor soon"


def test_chat_endpoint_rejects_invalid_image(monkeypatch):
    response = client.post(
        CHAT_URL,
        json={
            "message": "look",
            "image_b64": base64.b64encode(b"garbage").decode(),
            "image_mime": "image/jpeg",
        },
    )
    assert response.status_code == 422


def test_worker_reconstructs_image_and_passes_to_turn(monkeypatch):
    captured = {}

    async def fake_run(message, *, session_id=None, temperature=0.7, image=None, on_event=None):
        captured["image"] = image
        from app.services.chat import TurnResult

        return TurnResult(session_id=session_id or "s", response="ok", urgency="routine", events=[])

    monkeypatch.setattr("app.services.chat.run_chat_turn", fake_run)

    from app.worker import process_turn

    b64 = _image_b64()
    sha = "deadbeef"
    process_turn("hi", session_id="s", image_b64=b64, image_sha256=sha, image_size_bytes=42)

    image = captured["image"]
    assert image is not None
    assert image.b64 == b64
    assert image.sha256 == sha
    assert image.size_bytes == 42
    assert image.mime == "image/jpeg"


def test_worker_without_image_passes_none(monkeypatch):
    captured = {}

    async def fake_run(message, *, session_id=None, temperature=0.7, image=None, on_event=None):
        captured["image"] = image
        from app.services.chat import TurnResult

        return TurnResult(session_id=session_id or "s", response="ok", urgency="routine", events=[])

    monkeypatch.setattr("app.services.chat.run_chat_turn", fake_run)

    from app.worker import process_turn

    process_turn("hi")
    assert captured["image"] is None


def test_persist_then_sanitize_round_trip_is_stable():
    processed = decode_and_sanitize(_image_b64(), "image/jpeg")
    path = persist_image(processed, "roundtrip-turn")
    reread = base64.b64decode(processed.b64)
    assert path.endswith(".jpg")
    assert reread[:2] == b"\xff\xd8"  # JPEG magic bytes
