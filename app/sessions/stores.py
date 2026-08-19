import asyncio
import json
import time
from abc import ABC, abstractmethod

import redis.asyncio as aioredis

from .models import Session

SESSION_KEY_PREFIX = "medgemma:session:"


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