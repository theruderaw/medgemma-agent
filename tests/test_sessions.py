import asyncio

import httpx
import pytest

from app.main import app
from app.sessions import (
    InMemorySessionStore,
    Session,
    SessionExpiredError,
    SessionManager,
)


def make_manager(
    *,
    timeout: float = 60.0,
    max_history_messages: int = 40,
    max_context_messages: int = 20,
    max_context_chars: int = 16000,
) -> SessionManager:
    return SessionManager(
        InMemorySessionStore(timeout_seconds=timeout),
        max_history_messages=max_history_messages,
        max_context_messages=max_context_messages,
        max_context_chars=max_context_chars,
    )


@pytest.mark.asyncio
async def test_roundtrip():
    manager = make_manager()
    session_id = manager.new_id()
    session = await manager.load_or_create(session_id, must_exist=False)
    await manager.append(session, "user", "hello")
    await manager.append(session, "assistant", "hi")
    await manager.save(session)

    loaded = await manager.load_or_create(session_id, must_exist=True)
    assert loaded.messages == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]


@pytest.mark.asyncio
async def test_unknown_session_raises_expired():
    manager = make_manager()
    with pytest.raises(SessionExpiredError):
        await manager.load_or_create("does-not-exist", must_exist=True)


@pytest.mark.asyncio
async def test_expired_session_is_not_found():
    manager = make_manager(timeout=30)
    session_id = manager.new_id()
    session = await manager.load_or_create(session_id, must_exist=False)
    await manager.save(session)
    session.last_activity = 0.0
    with pytest.raises(SessionExpiredError):
        await manager.load_or_create(session_id, must_exist=True)


@pytest.mark.asyncio
async def test_reset_deletes():
    manager = make_manager()
    session_id = manager.new_id()
    session = await manager.load_or_create(session_id, must_exist=False)
    await manager.save(session)
    assert await manager.reset(session_id) is True
    assert await manager.reset(session_id) is False


@pytest.mark.asyncio
async def test_history_size_cap():
    manager = make_manager(max_history_messages=4)
    session = await manager.load_or_create("s", must_exist=False)
    for i in range(6):
        await manager.append(session, "user" if i % 2 == 0 else "assistant", f"m{i}")
    await manager.save(session)
    assert [m["content"] for m in session.messages] == ["m2", "m3", "m4", "m5"]


@pytest.mark.asyncio
async def test_context_message_cap_keeps_pairs():
    manager = make_manager(max_context_messages=6)
    session = await manager.load_or_create("s", must_exist=False)
    for i in range(10):
        await manager.append(session, "user" if i % 2 == 0 else "assistant", f"m{i}")
    context = manager.build_messages(session)
    assert [m["content"] for m in context] == ["m4", "m5", "m6", "m7", "m8", "m9"]


@pytest.mark.asyncio
async def test_context_char_budget_keeps_at_least_one():
    manager = make_manager(max_context_chars=5)
    session = await manager.load_or_create("s", must_exist=False)
    await manager.append(session, "user", "a" * 100)
    await manager.append(session, "assistant", "b" * 100)
    context = manager.build_messages(session)
    assert len(context) >= 1
    assert context[-1]["content"] == "b" * 100


@pytest.mark.asyncio
async def test_context_budget_drops_from_front():
    manager = make_manager(max_context_chars=20)
    session = await manager.load_or_create("s", must_exist=False)
    await manager.append(session, "user", "x" * 10)
    await manager.append(session, "assistant", "y" * 10)
    await manager.append(session, "user", "z" * 10)
    context = manager.build_messages(session)
    total = sum(len(m["content"]) for m in context)
    assert total <= 20
    assert context[0]["role"] == "assistant"
    assert context[-1]["role"] == "user"


def _redis_available() -> bool:
    try:
        from app.config import settings

        import redis.asyncio as aioredis

        async def probe() -> bool:
            client = aioredis.from_url(settings.redis_url, decode_responses=True)
            try:
                return await client.ping()
            finally:
                await client.aclose()

        return asyncio.run(probe())
    except Exception:
        return False


@pytest.mark.skipif(not _redis_available(), reason="Redis server not available")
@pytest.mark.asyncio
async def test_redis_store_roundtrip():
    from app.sessions import RedisSessionStore
    from app.config import settings

    store = RedisSessionStore(settings.redis_url, 60)
    session = Session(session_id="redis-test-session")
    await store.save(session)
    try:
        loaded = await store.get("redis-test-session")
        assert loaded is not None
        assert loaded.session_id == "redis-test-session"
        assert await store.delete("redis-test-session") is True
        assert await store.get("redis-test-session") is None
    finally:
        await store.aclose()


@pytest.mark.asyncio
async def test_chat_expired_session_returns_410(monkeypatch):
    manager = make_manager(timeout=30)
    session_id = manager.new_id()
    session = await manager.load_or_create(session_id, must_exist=False)
    await manager.save(session)
    session.last_activity = 0.0

    monkeypatch.setattr("app.main.sessions", manager)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/chat", json={"message": "hi", "session_id": session_id})
    assert response.status_code == 410