import asyncio
import uuid

from ..core.config import settings
from ..core.context import trim_context
from .models import Session, SessionExpiredError
from .postgres import PostgresSessionStore
from .stores import InMemorySessionStore, RedisSessionStore, SessionStore


def build_store() -> SessionStore:
    if settings.session_store_type == "redis":
        return RedisSessionStore(settings.redis_url, settings.session_timeout_seconds)
    if settings.session_store_type == "postgres":
        return PostgresSessionStore(settings.database_url, settings.session_timeout_seconds)
    return InMemorySessionStore(settings.session_timeout_seconds)


class SessionManager:
    def __init__(
        self,
        store: SessionStore,
        *,
        max_history_messages: int,
        max_context_messages: int,
        max_context_chars: int,
    ) -> None:
        self._store = store
        self.max_history_messages = max_history_messages
        self.max_context_messages = max_context_messages
        self.max_context_chars = max_context_chars
        self._locks: dict[str, asyncio.Lock] = {}
        self._locks_guard = asyncio.Lock()

    @staticmethod
    def new_id() -> str:
        return uuid.uuid4().hex

    async def lock(self, session_id: str) -> asyncio.Lock:
        async with self._locks_guard:
            lock = self._locks.get(session_id)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[session_id] = lock
            return lock

    async def load_or_create(self, session_id: str, must_exist: bool) -> Session:
        if not must_exist:
            return Session(session_id=session_id)
        session = await self._store.get(session_id)
        if session is None:
            raise SessionExpiredError(f"Session {session_id} is unknown or expired")
        return session

    async def append(self, session: Session, role: str, content: str) -> None:
        session.messages.append({"role": role, "content": content})

    def build_messages(self, session: Session) -> list[dict]:
        return trim_context(
            session.messages,
            max_context_messages=self.max_context_messages,
            max_context_chars=self.max_context_chars,
        )

    async def save(self, session: Session) -> None:
        if not self._store.retains_full_history and len(session.messages) > self.max_history_messages:
            session.messages = session.messages[-self.max_history_messages:]
        await self._store.save(session)

    async def reset(self, session_id: str) -> bool:
        result = await self._store.delete(session_id)
        async with self._locks_guard:
            self._locks.pop(session_id, None)
        return result

    async def close(self) -> None:
        await self._store.aclose()


sessions = SessionManager(
    build_store(),
    max_history_messages=settings.max_history_messages,
    max_context_messages=settings.max_context_messages,
    max_context_chars=settings.max_context_chars,
)