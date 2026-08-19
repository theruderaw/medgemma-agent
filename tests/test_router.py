import pytest

from app.config import settings
from app.main import app
from app.router import CLINICAL_KEYWORDS, should_route_to_specialist
from app.sessions import InMemorySessionStore, SessionManager
from fastapi.testclient import TestClient

client = TestClient(app)

CHAT_URL = "/chat"


@pytest.mark.parametrize("keyword", CLINICAL_KEYWORDS)
def test_router_matches_each_keyword(keyword):
    assert should_route_to_specialist(f"I have a {keyword} today") is True


def test_router_ignores_case_and_whitespace():
    assert should_route_to_specialist("  FEVER!! ") is True


@pytest.mark.parametrize("message", ["Hello", "tell me a joke", "how does the app work", "thanks"])
def test_router_leaves_general_messages_direct(message):
    assert should_route_to_specialist(message) is False


def test_chat_routes_clinical_message_to_specialist_then_synthesis(monkeypatch):
    calls = []

    async def fake_chat(messages, temperature=0.7, model=None):
        calls.append({"model": model, "messages": messages})
        return "clinical note" if model == settings.specialist_model_name else "synthesis reply"

    monkeypatch.setattr("app.main.llm.chat", fake_chat)

    response = client.post(CHAT_URL, json={"message": "I have a bad headache."})
    assert response.status_code == 200
    assert response.json()["response"] == "synthesis reply"

    assert len(calls) == 2
    specialist, synthesis = calls
    assert specialist["model"] == settings.specialist_model_name
    assert specialist["messages"][-1]["content"] == "I have a bad headache."

    assert synthesis["model"] == settings.model_name
    roles = [m["role"] for m in synthesis["messages"]]
    assert roles == ["system", "system", "user"]
    assert "A clinical specialist model produced the following note" in synthesis["messages"][1]["content"]
    assert "clinical note" in synthesis["messages"][1]["content"]


def test_chat_keeps_general_message_on_direct_path(monkeypatch):
    calls = []

    async def fake_chat(messages, temperature=0.7, model=None):
        calls.append(model)
        return "hello back"

    monkeypatch.setattr("app.main.llm.chat", fake_chat)

    response = client.post(CHAT_URL, json={"message": "Hello there"})
    assert response.status_code == 200
    assert calls == [settings.model_name]


def test_route_can_be_overridden_by_reset(monkeypatch):
    """A session that started clinical can go back to general on the next turn."""
    calls = []

    async def fake_chat(messages, temperature=0.7, model=None):
        calls.append(model)
        return "ok"

    monkeypatch.setattr("app.main.llm.chat", fake_chat)

    r1 = client.post(CHAT_URL, json={"message": "My knee hurts"})
    session_id = r1.json()["session_id"]
    r2 = client.post(CHAT_URL, json={"message": "Thanks, that helps", "session_id": session_id})
    assert r2.status_code == 200

    assert calls == [settings.specialist_model_name, settings.model_name, settings.model_name]


@pytest.mark.asyncio
async def test_specialist_error_maps_to_503(monkeypatch):
    import httpx

    async def fake_chat(messages, temperature=0.7, model=None):
        raise httpx.ConnectError("specialist down")

    monkeypatch.setattr("app.main.llm.chat", fake_chat)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(CHAT_URL, json={"message": "I feel nauseous"})
    assert response.status_code == 503