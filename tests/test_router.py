import httpx
import pytest

from app.core.config import settings
from app.llm import ChatResult
from app.main import app
from app.routes import RouteCategory, parse_tool_calls
from fastapi.testclient import TestClient

client = TestClient(app)

CHAT_URL = "/v1/chat"


@pytest.fixture(autouse=True)
def mock_triage(monkeypatch):
    async def fake_triage(message, temperature=0.0, image_b64=None):
        return '{"urgency": "self_care"}'

    monkeypatch.setattr("app.services.chat.llm.triage", fake_triage)


SPECIALIST_CALL = {
    "id": "call_1",
    "type": "function",
    "function": {
        "name": "call_medical_specialist",
        "arguments": '{"reason": "persistent left-sided headache"}',
    },
}


def test_parse_tool_calls_returns_general_when_no_tool():
    decision = parse_tool_calls([])
    assert decision.category is RouteCategory.GENERAL
    assert decision.reason is None


def test_parse_tool_calls_returns_symptom_related():
    decision = parse_tool_calls([SPECIALIST_CALL])
    assert decision.category is RouteCategory.SYMPTOM_RELATED
    assert decision.reason == "persistent left-sided headache"


def test_parse_tool_calls_ignores_unknown_tools():
    unknown = {"function": {"name": "some_other_tool", "arguments": "{}"}}
    decision = parse_tool_calls([unknown])
    assert decision.category is RouteCategory.GENERAL


def test_parse_tool_calls_handles_malformed_arguments():
    malformed = {
        "function": {
            "name": "call_medical_specialist",
            "arguments": "not-json",
        }
    }
    decision = parse_tool_calls([malformed])
    assert decision.category is RouteCategory.SYMPTOM_RELATED
    assert decision.reason is None


def test_parse_tool_calls_never_returns_emergency():
    """The classifier must never be able to route to emergency — that belongs
    to the independent hardcoded safety check only."""
    for tool_calls in ([], [SPECIALIST_CALL], None):
        decision = parse_tool_calls(tool_calls)
        assert decision.category is not RouteCategory.EMERGENCY


def test_chat_routes_clinical_message_to_specialist_then_synthesis(monkeypatch):
    calls = []

    async def fake_route(messages, tools, temperature=0.7, model=None):
        return ChatResult(content="", tool_calls=[SPECIALIST_CALL])

    async def fake_chat(messages, temperature=0.7, model=None):
        calls.append({"model": model, "messages": messages})
        return "clinical note" if model == settings.specialist_model_name else "synthesis reply"

    monkeypatch.setattr("app.services.chat.llm.chat_with_tools", fake_route)
    monkeypatch.setattr("app.services.chat.llm.chat", fake_chat)

    response = client.post(CHAT_URL, json={"message": "I have a bad headache."})
    assert response.status_code == 200
    assert response.json()["response"] == "synthesis reply"

    assert len(calls) == 2
    specialist, synthesis = calls
    assert specialist["model"] == settings.specialist_model_name
    assert specialist["messages"][-1]["content"] == "persistent left-sided headache"

    assert synthesis["model"] == settings.model_name
    roles = [m["role"] for m in synthesis["messages"]]
    assert roles == ["system", "system", "system", "user"]
    triage_msg, specialist_msg = synthesis["messages"][1], synthesis["messages"][2]
    assert "urgency level: self_care" in triage_msg["content"]
    assert "A clinical specialist model produced the following note" in specialist_msg["content"]
    assert "clinical note" in specialist_msg["content"]


def test_chat_keeps_general_message_on_direct_path(monkeypatch):
    calls = []

    async def fake_route(messages, tools, temperature=0.7, model=None):
        return ChatResult(content="hello back", tool_calls=[])

    async def fake_chat(messages, temperature=0.7, model=None):
        calls.append(model)
        return "should not be reached"

    monkeypatch.setattr("app.services.chat.llm.chat_with_tools", fake_route)
    monkeypatch.setattr("app.services.chat.llm.chat", fake_chat)

    response = client.post(CHAT_URL, json={"message": "Hello there"})
    assert response.status_code == 200
    assert response.json()["response"] == "hello back"
    assert calls == []


def test_route_can_be_overridden_by_reset(monkeypatch):
    """A session that started clinical can go back to general on the next turn."""
    calls = []

    async def fake_route(messages, tools, temperature=0.7, model=None):
        last_user = next(m["content"] for m in reversed(messages) if m["role"] == "user")
        if "hurts" in last_user:
            return ChatResult(content="", tool_calls=[SPECIALIST_CALL])
        return ChatResult(content="ok", tool_calls=[])

    async def fake_chat(messages, temperature=0.7, model=None):
        calls.append(model)
        return "ok"

    monkeypatch.setattr("app.services.chat.llm.chat_with_tools", fake_route)
    monkeypatch.setattr("app.services.chat.llm.chat", fake_chat)

    r1 = client.post(CHAT_URL, json={"message": "My knee hurts"})
    session_id = r1.json()["session_id"]
    r2 = client.post(CHAT_URL, json={"message": "Thanks, that helps", "session_id": session_id})
    assert r2.status_code == 200

    assert calls == [settings.specialist_model_name, settings.model_name]


@pytest.mark.asyncio
async def test_specialist_error_maps_to_503(monkeypatch):
    async def fake_route(messages, tools, temperature=0.7, model=None):
        return ChatResult(content="", tool_calls=[SPECIALIST_CALL])

    async def fake_chat(messages, temperature=0.7, model=None):
        raise httpx.ConnectError("specialist down")

    monkeypatch.setattr("app.services.chat.llm.chat_with_tools", fake_route)
    monkeypatch.setattr("app.services.chat.llm.chat", fake_chat)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(CHAT_URL, json={"message": "I feel nauseous"})
    assert response.status_code == 503