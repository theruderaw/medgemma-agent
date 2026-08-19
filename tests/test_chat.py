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
    async def fake_chat(message, temperature=0.7):
        assert message == "Hello"
        return "Hello! How can I help you?"

    monkeypatch.setattr("app.main.llm.chat", fake_chat)
    response = client.post(CHAT_URL, json={"message": "Hello"})
    assert response.status_code == 200
    assert response.json()["response"] == "Hello! How can I help you?"


@pytest.mark.asyncio
async def test_chat_model_unreachable(monkeypatch):
    async def fake_chat(message, temperature=0.7):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr("app.main.llm.chat", fake_chat)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(CHAT_URL, json={"message": "hi"})
    assert response.status_code == 503


def test_settings_defaults():
    assert settings.model_name == "qwen3:4b"
    assert settings.ollama_base_url == "http://localhost:11434"