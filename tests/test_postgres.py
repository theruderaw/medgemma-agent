import asyncio
import json

import pytest

from app.audit import PostgresAuditLogger
from app.core.config import settings
from app.sessions import PostgresSessionStore, Session, SessionManager


def _postgres_available() -> bool:
    try:
        import asyncpg

        async def probe() -> bool:
            conn = await asyncpg.connect(settings.database_url)
            try:
                await conn.execute("SELECT 1")
                return True
            finally:
                await conn.close()

        return asyncio.run(probe())
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _postgres_available(), reason="PostgreSQL server not available")


@pytest.fixture(scope="module", autouse=True)
def _init_schema():
    from app.core.db import create_all

    asyncio.run(create_all())


@pytest.fixture
def _clean_tables():
    import asyncpg

    async def clean():
        conn = await asyncpg.connect(settings.database_url)
        try:
            await conn.execute("TRUNCATE sessions, audit_events RESTART IDENTITY CASCADE")
        finally:
            await conn.close()

    asyncio.run(clean())


def _make_manager() -> SessionManager:
    return SessionManager(
        PostgresSessionStore(settings.database_url, timeout_seconds=60),
        max_history_messages=40,
        max_context_messages=20,
        max_context_chars=16000,
    )


@pytest.mark.asyncio
async def test_postgres_store_roundtrip(_clean_tables):
    manager = _make_manager()
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
    assert loaded.session_id == session_id


@pytest.mark.asyncio
async def test_postgres_store_append_only_history(_clean_tables):
    manager = SessionManager(
        PostgresSessionStore(settings.database_url, timeout_seconds=60),
        max_history_messages=2,
        max_context_messages=20,
        max_context_chars=16000,
    )
    session = await manager.load_or_create("s", must_exist=False)
    for i in range(6):
        await manager.append(session, "user" if i % 2 == 0 else "assistant", f"m{i}")
    await manager.save(session)

    loaded = await manager.load_or_create("s", must_exist=True)
    assert [m["content"] for m in loaded.messages] == ["m0", "m1", "m2", "m3", "m4", "m5"]


@pytest.mark.asyncio
async def test_postgres_store_unknown_session(_clean_tables):
    manager = _make_manager()
    assert await manager.load_or_create("missing", must_exist=False) is not None
    assert await manager._store.get("missing") is None


@pytest.mark.asyncio
async def test_postgres_store_reset_deletes(_clean_tables):
    manager = _make_manager()
    session = await manager.load_or_create("s", must_exist=False)
    await manager.save(session)
    assert await manager.reset("s") is True
    assert await manager.reset("s") is False
    assert await manager._store.get("s") is None


@pytest.mark.asyncio
async def test_postgres_audit_append_only(_clean_tables):
    logger = PostgresAuditLogger(settings.database_url)
    await logger.append(
        module="safety",
        event_type="safety_override",
        payload={"category": "cardiac"},
        session_id="s1",
        turn_id="t1",
    )
    await logger.append(
        module="specialist",
        event_type="specialist_output",
        payload={"note": "full note body", "reason": "chest pain"},
        session_id="s1",
        turn_id="t1",
    )

    import asyncpg

    conn = await asyncpg.connect(settings.database_url)
    try:
        rows = await conn.fetch(
            "SELECT module, event_type, payload FROM audit_events ORDER BY id"
        )
    finally:
        await conn.close()

    assert len(rows) == 2
    assert rows[0]["module"] == "safety"
    assert rows[0]["event_type"] == "safety_override"
    payload = json.loads(rows[0]["payload"])
    assert payload == {"category": "cardiac"}
    assert json.loads(rows[1]["payload"]) == {"note": "full note body", "reason": "chest pain"}


@pytest.mark.asyncio
async def test_postgres_audit_is_append_only_no_update_path(_clean_tables):
    logger = PostgresAuditLogger(settings.database_url)
    await logger.append(module="chat", event_type="turn_completed", payload={"response": "a"})
    await logger.append(module="chat", event_type="turn_completed", payload={"response": "b"})

    import asyncpg

    conn = await asyncpg.connect(settings.database_url)
    try:
        count = await conn.fetchval("SELECT count(*) FROM audit_events")
    finally:
        await conn.close()
    assert count == 2