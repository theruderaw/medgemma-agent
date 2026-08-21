"""Streaming contract: the SSE channel never goes silent.

Every turn emits a `start` frame immediately, pipeline audit events as each
stage completes, specialist note tokens while MedGemma writes, reply tokens
for the synthesis, and empty-token heartbeats whenever nothing else is ready.
"""

import asyncio
import base64
import io

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.audit import NullAuditLogger
from app.core.config import settings
from app.llm import ChatResult
from app.main import app
from app.sessions import InMemorySessionStore, SessionManager

client = TestClient(app)

STREAM_URL = "/v1/chat/stream"

SPECIALIST_CALL = {
    "id": "call_1",
    "type": "function",
    "function": {
        "name": "call_medical_specialist",
        "arguments": '{"reason": "rash on arm"}',
    },
}


def _image_b64() -> str:
    img = Image.new("RGB", (64, 64), (180, 60, 60))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode()


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch):
    monkeypatch.setattr(
        "app.services.chat.sessions",
        SessionManager(
            InMemorySessionStore(60),
            max_history_messages=40,
            max_context_messages=20,
            max_context_chars=16000,
        ),
    )
    monkeypatch.setattr("app.services.chat.audit", NullAuditLogger())


async def _collect_stream(**kwargs):
    from app.services.chat import run_chat_turn_stream

    events = []
    async for event in run_chat_turn_stream(**kwargs):
        events.append(event)
    return events


def _mock_full_pipeline(monkeypatch):
    """Mock every model call so the whole specialist path is offline."""

    async def fake_triage(message, temperature=0.0, image_b64=None):
        return '{"urgency": "urgent", "text_findings": ["rash"], "reasoning": ""}'

    async def fake_route(messages, tools, temperature=0.7, model=None):
        return ChatResult(content="", tool_calls=[SPECIALIST_CALL])

    async def fake_chat_with_images_stream(messages, images, temperature=0.7, model=None):
        for delta in ["visual ", "findings ", "note"]:
            yield delta

    async def fake_chat_stream(messages, temperature=0.7, model=None):
        for delta in ["see ", "a ", "doctor"]:
            yield delta

    async def fake_chat_with_images(messages, images, temperature=0.7, model=None):
        raise AssertionError("blocking specialist call must not run when streaming")

    async def fake_chat(messages, temperature=0.7, model=None):
        raise AssertionError("blocking synthesis call must not run when streaming")

    monkeypatch.setattr("app.services.chat.llm.triage", fake_triage)
    monkeypatch.setattr("app.services.chat.llm.chat_with_tools", fake_route)
    monkeypatch.setattr("app.services.chat.llm.chat_with_images_stream", fake_chat_with_images_stream)
    monkeypatch.setattr("app.services.chat.llm.chat_stream", fake_chat_stream)
    monkeypatch.setattr("app.services.chat.llm.chat_with_images", fake_chat_with_images)
    monkeypatch.setattr("app.services.chat.llm.chat", fake_chat)


def test_stream_event_ordering_covers_every_stage(monkeypatch):
    _mock_full_pipeline(monkeypatch)

    from app.core.images import decode_and_sanitize

    image = decode_and_sanitize(_image_b64(), "image/jpeg")
    events = asyncio.run(_collect_stream(message="look at my arm", image=image))

    types = [e["type"] for e in events]
    assert types[0] == "start"
    assert types[-1] == "done"

    assert types.count("pipeline") == 5
    pipeline_kinds = [e["event"]["event_type"] for e in events if e["type"] == "pipeline"]
    assert pipeline_kinds == [
        "image_received",
        "triage_result",
        "routing_decision",
        "specialist_output",
        "turn_completed",
    ]

    specialist_tokens = [e["content"] for e in events if e["type"] == "specialist_token"]
    assert "".join(specialist_tokens) == "visual findings note"

    reply_tokens = [e["content"] for e in events if e["type"] == "token"]
    assert "".join(reply_tokens) == "see a doctor"

    done = events[-1]
    assert done["response"] == "see a doctor"
    assert done["urgency"] == "urgent"
    assert len(done["events"]) == 5


def test_stream_general_path_still_streams_reply(monkeypatch):
    async def fake_triage(message, temperature=0.0, image_b64=None):
        return '{"urgency": "self_care"}'

    async def fake_route(messages, tools, temperature=0.7, model=None):
        return ChatResult(content="hello there", tool_calls=[])

    monkeypatch.setattr("app.services.chat.llm.triage", fake_triage)
    monkeypatch.setattr("app.services.chat.llm.chat_with_tools", fake_route)

    events = asyncio.run(_collect_stream(message="hi"))

    types = [e["type"] for e in events]
    assert types[0] == "start"
    assert types[-1] == "done"
    tokens = [e["content"] for e in events if e["type"] == "token"]
    assert "".join(tokens) == "hello there"
    assert not any(e["type"] == "specialist_token" for e in events)


def test_stream_emits_heartbeats_while_models_run(monkeypatch):
    _mock_full_pipeline(monkeypatch)
    monkeypatch.setattr("app.services.chat._STREAM_HEARTBEAT_SECONDS", 0.01)

    triage_calls = {"n": 0}

    async def slow_triage(message, temperature=0.0, image_b64=None):
        triage_calls["n"] += 1
        await asyncio.sleep(0.08)
        return '{"urgency": "routine"}'

    monkeypatch.setattr("app.services.chat.llm.triage", slow_triage)

    from app.core.images import decode_and_sanitize

    image = decode_and_sanitize(_image_b64(), "image/jpeg")
    events = asyncio.run(_collect_stream(message="look", image=image))

    heartbeats = [e for e in events if e["type"] == "token" and e["content"] == ""]
    assert heartbeats, "expected empty-token heartbeats while models were running"
    # Heartbeats bridge the gap before the specialist starts writing.
    first_specialist = next(i for i, e in enumerate(events) if e["type"] == "specialist_token")
    assert any(
        i < first_specialist and e["type"] == "token" and e["content"] == ""
        for i, e in enumerate(events)
    )


def test_sse_framing_uses_named_events(monkeypatch):
    _mock_full_pipeline(monkeypatch)

    response = client.post(
        STREAM_URL,
        json={
            "message": "look at my arm",
            "image_b64": _image_b64(),
            "image_mime": "image/jpeg",
        },
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    text = response.text

    for name in ("start", "pipeline", "specialist_token", "token", "done"):
        assert f"event: {name}" in text

    # Named frames stay parseable by the type-field parser.
    assert '"type": "pipeline"' in text.replace(" ", "") or '"type":"pipeline"' in text.replace(" ", "")
    assert text.index("event: start") < text.index("event: pipeline")
    assert text.index("event: specialist_token") < text.index("event: done")


def test_sse_error_frame_on_model_failure(monkeypatch):
    async def fake_triage(message, temperature=0.0, image_b64=None):
        raise httpx.ConnectError("model down")

    monkeypatch.setattr("app.services.chat.llm.triage", fake_triage)

    response = client.post(STREAM_URL, json={"message": "hi"})
    assert response.status_code == 200
    assert "event: error" in response.text
    assert "503" in response.text


def test_stream_rejects_invalid_image_before_stream_opens():
    response = client.post(
        STREAM_URL,
        json={
            "message": "look",
            "image_b64": base64.b64encode(b"garbage").decode(),
            "image_mime": "image/jpeg",
        },
    )
    assert response.status_code == 422


def test_worker_path_does_not_stream_specialist(monkeypatch):
    """Queued mode keeps the blocking specialist call — only sync streams."""
    captured = {}

    async def fake_run(message, *, session_id=None, temperature=0.7, image=None, on_event=None):
        captured["has_on_specialist_token"] = False
        from app.services.chat import TurnResult

        return TurnResult(session_id=session_id or "s", response="ok", urgency="routine", events=[])

    monkeypatch.setattr("app.services.chat.run_chat_turn", fake_run)

    from app.worker import process_turn

    process_turn("hi")
    assert captured["has_on_specialist_token"] is False
