import asyncio
import json
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import redis.asyncio as aioredis

from .config import settings

SESSION_KEY_PREFIX = "medgemma:session:"


class SessionExpiredError(Exception):
    pass


@dataclass
class Session:
    session_id: str
    messages: list[dict] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "messages": self.messages,
            "created_at": self.created_at,
            "last_activity": self.last_activity,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Session":
        return cls(
            session_id=data["session_id"],
            messages=data.get("messages", []),
            created_at=data.get("created_at", time.time()),
            last_activity=data.get("last_activity", time.time()),
        )


class SessionStore(ABC):
    timeout_seconds: float

    @abstractmethod
    async def get(self, session_id: str) -> Session | None:
        """Return the session, or None if it does not exist or is expired."""

    @abstractmethod
    async def save(self, session: Session) -> None:
        """Persist the session and refresh its idle timeout."""

    @abstractmethod
    async def delete(self, session_id: str) -> bool:
        """Remove the session; return True if it existed."""

    async def aclose(self) -> None:
        pass

    def _expired(self, last_activity: float) -> bool:
        return time.time() - last_activity > self.timeout_seconds


class InMemorySessionStore(SessionStore):
    def __init__(self, timeout_seconds: float) -> None:
        self.timeout_seconds = timeout_seconds
        self._sessions: dict[str, Session] = {}
        self._lock = asyncio.Lock()

    async def get(self, session_id: str) -> Session | None:
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            if self._expired(session.last_activity):
                del self._sessions[session_id]
                return None
            return session

    async def save(self, session: Session) -> None:
        async with self._lock:
            session.last_activity = time.time()
            self._sessions[session.session_id] = session

    async def delete(self, session_id: str) -> bool:
        async with self._lock:
            return self._sessions.pop(session_id, None) is not None


class RedisSessionStore(SessionStore):
    """Redis-backed store.

    A fresh client is created per operation because redis-py async connections
    are bound to the event loop that created them, and loops may differ across
    requests (e.g. under test clients). Connection setup is negligible next to
    model latency.
    """

    def __init__(self, url: str, timeout_seconds: float) -> None:
        self.url = url
        self.timeout_seconds = timeout_seconds

    def _key(self, session_id: str) -> str:
        return f"{SESSION_KEY_PREFIX}{session_id}"

    async def get(self, session_id: str) -> Session | None:
        client = aioredis.from_url(self.url, decode_responses=True)
        try:
            raw = await client.get(self._key(session_id))
        finally:
            await client.aclose()
        if raw is None:
            return None
        return Session.from_dict(json.loads(raw))

    async def save(self, session: Session) -> None:
        session.last_activity = time.time()
        client = aioredis.from_url(self.url, decode_responses=True)
        try:
            await client.set(
                self._key(session.session_id),
                json.dumps(session.to_dict()),
                ex=int(self.timeout_seconds),
            )
        finally:
            await client.aclose()

    async def delete(self, session_id: str) -> bool:
        client = aioredis.from_url(self.url, decode_responses=True)
        try:
            return await client.delete(self._key(session_id)) > 0
        finally:
            await client.aclose()


def build_store() -> SessionStore:
    if settings.session_store_type == "redis":
        return RedisSessionStore(settings.redis_url, settings.session_timeout_seconds)
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
        """Return the context window to send to the model.

        Caps the message count (keeping user/assistant pairs intact) and then
        applies a back-to-front character budget so a single very long turn
        cannot blow up the context. At least one message is always kept.
        """
        messages = session.messages[:]
        count = len(messages)
        if count > self.max_context_messages:
            count = self.max_context_messages
            if count % 2 == 1:
                count -= 1
            messages = messages[-count:]
        total = sum(len(m.get("content", "")) for m in messages)
        while len(messages) > 1 and total > self.max_context_chars:
            messages.pop(0)
            total = sum(len(m.get("content", "")) for m in messages)
        while len(messages) > 2 and messages[0]["role"] != "user":
            messages.pop(0)
        return messages

    async def save(self, session: Session) -> None:
        if len(session.messages) > self.max_history_messages:
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