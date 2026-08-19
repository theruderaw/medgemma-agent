import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

client = TestClient(app)

CHAT_URL = "/chat"


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_rejects_empty_message():
    response = client.post(CHAT_URL, json={"message": ""})
    assert response.status_code == 422


def test_chat_rejects_missing_message():
    response = client.post(CHAT_URL, json={})
    assert response.status_code == 422


def test_chat_returns_model_response(monkeypatch):
    async def fake_chat(messages, temperature=0.7, model=None):
        assert messages[0]["role"] == "system"
        assert messages[-1] == {"role": "user", "content": "Hello"}
        return "Hello! How can I help you?"

    monkeypatch.setattr("app.main.llm.chat", fake_chat)
    response = client.post(CHAT_URL, json={"message": "Hello"})
    assert response.status_code == 200
    body = response.json()
    assert body["response"] == "Hello! How can I help you?"
    assert body["session_id"]


@pytest.mark.asyncio
async def test_chat_model_unreachable(monkeypatch):
    async def fake_chat(messages, temperature=0.7, model=None):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr("app.main.llm.chat", fake_chat)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(CHAT_URL, json={"message": "hi"})
    assert response.status_code == 503


def test_settings_defaults():
    assert settings.model_name == "qwen3:4b"
    assert settings.ollama_base_url == "http://localhost:11434"
    assert settings.session_store_type == "memory"
    assert settings.max_history_messages == 40
    assert settings.max_context_messages == 20


def test_chat_accumulates_history(monkeypatch):
    turns = []

    async def fake_chat(messages, temperature=0.7, model=None):
        turns.append([m["role"] for m in messages])
        return f"reply-{len(turns)}"

    monkeypatch.setattr("app.main.llm.chat", fake_chat)

    first = client.post(CHAT_URL, json={"message": "Hello, how are you?"})
    assert first.status_code == 200
    session_id = first.json()["session_id"]

    second = client.post(CHAT_URL, json={"message": "Tell me more.", "session_id": session_id})
    assert second.status_code == 200

    assert turns[0] == ["system", "user"]
    assert turns[1] == ["system", "user", "assistant", "user"]
    assert second.json()["session_id"] == session_id


def test_session_reset(monkeypatch):
    async def fake_chat(messages, temperature=0.7, model=None):
        return "ok"

    monkeypatch.setattr("app.main.llm.chat", fake_chat)

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