import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.llm import ChatResult, extract_answer
from app.main import app

client = TestClient(app)

CHAT_URL = "/chat"


@pytest.fixture(autouse=True)
def mock_triage(monkeypatch):
    async def fake_triage(message, temperature=0.0):
        return '{"urgency": "general"}'

    monkeypatch.setattr("app.services.chat.llm.triage", fake_triage)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_extract_answer_strips_response_tags():
    content = (
        'The user\'s message "hi there" is a greeting and falls under general '
        "chit-chat. No medical specialist assessment is needed.\n\n"
        "<response>\nHello! How can I help you today?\n</response>"
    )
    assert extract_answer(content) == "Hello! How can I help you today?"


def test_extract_answer_passes_through_plain_content():
    assert extract_answer("Hello! How can I help you?") == "Hello! How can I help you?"
    assert extract_answer("  trimmed  ") == "trimmed"


def test_chat_rejects_empty_message():
    response = client.post(CHAT_URL, json={"message": ""})
    assert response.status_code == 422


def test_chat_rejects_missing_message():
    response = client.post(CHAT_URL, json={})
    assert response.status_code == 422


def test_chat_returns_model_response(monkeypatch):
    async def fake_route(messages, tools, temperature=0.7, model=None):
        assert messages[0]["role"] == "system"
        assert messages[-1] == {"role": "user", "content": "Hello"}
        return ChatResult(content="Hello! How can I help you?", tool_calls=[])

    monkeypatch.setattr("app.services.chat.llm.chat_with_tools", fake_route)
    response = client.post(CHAT_URL, json={"message": "Hello"})
    assert response.status_code == 200
    body = response.json()
    assert body["response"] == "Hello! How can I help you?"
    assert body["session_id"]


@pytest.mark.asyncio
async def test_chat_model_unreachable(monkeypatch):
    async def fake_route(messages, tools, temperature=0.7, model=None):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr("app.services.chat.llm.chat_with_tools", fake_route)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(CHAT_URL, json={"message": "hi"})
    assert response.status_code == 503


def test_settings_defaults():
    assert settings.model_name == "qwen3:4b"
    assert settings.specialist_model_name == "medgemma1.5:4b"
    assert settings.triage_model_name == "qwen3:0.6b"
    assert settings.triage_enabled is True
    assert settings.ollama_base_url == "http://localhost:11434"
    assert settings.session_store_type in ("memory", "redis", "postgres")
    assert settings.max_history_messages == 40
    assert settings.max_context_messages == 20
    assert settings.processing_mode in ("sync", "queued")
    assert settings.job_result_expire_seconds == 3600
    assert settings.job_max_retries == 3
    assert settings.job_concurrency == 1


def test_chat_accumulates_history(monkeypatch):
    turns = []

    async def fake_route(messages, tools, temperature=0.7, model=None):
        turns.append([m["role"] for m in messages])
        return ChatResult(content=f"reply-{len(turns)}", tool_calls=[])

    monkeypatch.setattr("app.services.chat.llm.chat_with_tools", fake_route)

    first = client.post(CHAT_URL, json={"message": "Hello, how are you?"})
    assert first.status_code == 200
    session_id = first.json()["session_id"]

    second = client.post(CHAT_URL, json={"message": "Tell me more.", "session_id": session_id})
    assert second.status_code == 200

    assert turns[0] == ["system", "system", "user"]
    assert turns[1] == ["system", "system", "user", "assistant", "user"]
    assert second.json()["session_id"] == session_id


def test_session_reset(monkeypatch):
    async def fake_route(messages, tools, temperature=0.7, model=None):
        return ChatResult(content="ok", tool_calls=[])

    monkeypatch.setattr("app.services.chat.llm.chat_with_tools", fake_route)

    created = client.post(CHAT_URL, json={"message": "hi"})
    session_id = created.json()["session_id"]

    reset = client.delete(f"/sessions/{session_id}")
    assert reset.status_code == 204

    reused = client.post(CHAT_URL, json={"message": "hi", "session_id": session_id})
    assert reused.status_code == 410


def test_reset_unknown_session_returns_404():
    response = client.delete("/sessions/nonexistent-session")
    assert response.status_code == 404


def test_chat_with_unknown_session_returns_410():
    response = client.post(CHAT_URL, json={"message": "hi", "session_id": "unknown-session"})
    assert response.status_code == 410