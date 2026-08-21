import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from app.audit import (
    AuditLogger,
    CompositeAuditLogger,
    JsonFileAuditLogger,
    NullAuditLogger,
    trim_llm_payload,
)
from app.core.config import settings
from app.llm import ChatResult
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def mock_llm(monkeypatch):
    async def fake_triage(message, temperature=0.0, image_b64=None):
        return '{"urgency": "self_care"}'

    async def fake_route(messages, tools, temperature=0.7, model=None):
        return ChatResult(content="hello back", tool_calls=[])

    monkeypatch.setattr("app.services.chat.llm.triage", fake_triage)
    monkeypatch.setattr("app.services.chat.llm.chat_with_tools", fake_route)


def _jsonl_lines(path) -> list[dict]:
    return [json.loads(line) for line in open(path, encoding="utf-8").read().splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# JsonFileAuditLogger
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_json_file_audit_appends_one_line_per_event(tmp_path):
    logger = JsonFileAuditLogger(tmp_path / "audit.jsonl")
    await logger.append(module="triage", event_type="triage_result", payload={"urgency": "routine"}, session_id="s1", turn_id="t1")
    await logger.append(module="chat", event_type="turn_completed", payload={"response": "ok"}, session_id="s1", turn_id="t1")

    records = _jsonl_lines(tmp_path / "audit.jsonl")
    assert len(records) == 2
    first, second = records
    assert first["module"] == "triage"
    assert first["event_type"] == "triage_result"
    assert first["payload"] == {"urgency": "routine"}
    assert first["session_id"] == "s1"
    assert first["turn_id"] == "t1"
    assert isinstance(first["timestamp"], float)
    assert second["event_type"] == "turn_completed"


@pytest.mark.asyncio
async def test_json_file_audit_is_append_only(tmp_path):
    path = tmp_path / "audit.jsonl"
    logger = JsonFileAuditLogger(path)
    await logger.append(module="chat", event_type="turn_completed", payload={"response": "a"})
    await logger.append(module="chat", event_type="turn_completed", payload={"response": "b"})
    assert [r["payload"]["response"] for r in _jsonl_lines(path)] == ["a", "b"]


@pytest.mark.asyncio
async def test_json_file_audit_trims_llm_content(tmp_path):
    logger = JsonFileAuditLogger(tmp_path / "audit.jsonl", trim_llm_chars=20)
    await logger.append(
        module="specialist",
        event_type="specialist_output",
        payload={
            "note": "x" * 500,
            "tool_calls": [{"function": {"name": "call_medical_specialist", "arguments": "y" * 100}}],
            "small": "ok",
        },
        session_id="s1",
        turn_id="t1",
    )
    record = _jsonl_lines(tmp_path / "audit.jsonl")[0]
    payload = record["payload"]
    assert len(payload["note"]) == 20 + len("…[+480 chars trimmed]")
    assert payload["note"].endswith("[+480 chars trimmed]")
    assert payload["tool_calls"][0]["function"]["arguments"].endswith("[+80 chars trimmed]")
    assert payload["small"] == "ok"


def test_trim_llm_payload_recursive():
    trimmed = trim_llm_payload({"deep": {"note": "a" * 10}, "keep": 5}, cap=3)
    assert trimmed["deep"]["note"].endswith("[+7 chars trimmed]")
    assert trimmed["keep"] == 5


# ---------------------------------------------------------------------------
# CompositeAuditLogger
# ---------------------------------------------------------------------------


class FakeSink(AuditLogger):
    def __init__(self) -> None:
        self.calls = []

    async def append(self, *, module, event_type, payload, session_id=None, turn_id=None) -> None:
        self.calls.append((module, event_type))


class FailingSink(AuditLogger):
    async def append(self, **kwargs) -> None:
        raise RuntimeError("sink down")


@pytest.mark.asyncio
async def test_composite_fans_out_to_all_sinks():
    a, b = FakeSink(), FakeSink()
    logger = CompositeAuditLogger([a, b])
    await logger.append(module="safety", event_type="safety_override", payload={})
    assert a.calls == [("safety", "safety_override")]
    assert b.calls == [("safety", "safety_override")]


@pytest.mark.asyncio
async def test_composite_swallows_sink_failures():
    good, failing = FakeSink(), FailingSink()
    logger = CompositeAuditLogger([failing, good])
    await logger.append(module="safety", event_type="safety_override", payload={})
    assert good.calls == [("safety", "safety_override")]


# ---------------------------------------------------------------------------
# Every transaction lands in the JSON file audit trail
# ---------------------------------------------------------------------------


@pytest.fixture
def audit_file(monkeypatch, tmp_path):
    path = tmp_path / "audit.jsonl"
    logger = JsonFileAuditLogger(path)
    monkeypatch.setattr("app.services.chat.audit", logger)
    monkeypatch.setattr("app.main.audit", logger)
    return path


def test_chat_turn_writes_audit_jsonl(audit_file):
    response = client.post("/v1/chat", json={"message": "hello"})
    assert response.status_code == 200

    event_types = [r["event_type"] for r in _jsonl_lines(audit_file)]
    assert "triage_result" in event_types
    assert "routing_decision" in event_types
    assert "turn_completed" in event_types


def test_emergency_turn_writes_safety_override_audit(audit_file):
    response = client.post("/v1/chat", json={"message": "I have chest pain"})
    assert response.status_code == 200
    assert response.json()["urgency"] == "emergency"

    event_types = [r["event_type"] for r in _jsonl_lines(audit_file)]
    assert event_types == ["safety_override"]


def test_session_reset_writes_audit_jsonl(audit_file):
    created = client.post("/v1/chat", json={"message": "hi"})
    session_id = created.json()["session_id"]

    reset = client.delete(f"/v1/sessions/{session_id}")
    assert reset.status_code == 204

    event_types = [r["event_type"] for r in _jsonl_lines(audit_file)]
    assert event_types.count("session_reset") == 1


def test_queued_chat_enqueue_writes_job_audit(monkeypatch, audit_file):
    monkeypatch.setattr(settings, "processing_mode", "queued")

    def fake_apply_async(*, args, kwargs):
        return __import__("types").SimpleNamespace(id="job-audit-1")

    async def fake_mark(job_id):
        return None

    monkeypatch.setattr("app.main.process_turn.apply_async", fake_apply_async)
    monkeypatch.setattr("app.main.mark_enqueued", fake_mark)

    response = client.post("/v1/chat", json={"message": "hello"})
    assert response.status_code == 202

    event_types = [r["event_type"] for r in _jsonl_lines(audit_file)]
    assert "session_created" in event_types
    assert "job_enqueued" in event_types