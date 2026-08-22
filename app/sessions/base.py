import time

from .models import Session


class SessionStore:
    """Persistence contract for sessions. Postgres is the only implementation.

    Sessions and messages live in relational tables; history is retained in
    full (no trimming) so audit and evaluation can reconstruct conversations.
    """

    timeout_seconds: float
    retains_full_history: bool = True

    async def get(self, session_id: str) -> Session | None:
        """Return the session, or None if it does not exist or is expired."""
        raise NotImplementedError

    async def save(self, session: Session) -> None:
        """Persist the session and refresh its idle timeout."""
        raise NotImplementedError

    async def delete(self, session_id: str) -> bool:
        """Remove the session; return True if it existed."""
        raise NotImplementedError

    async def aclose(self) -> None:
        pass

    def _expired(self, last_activity: float) -> bool:
        return time.time() - last_activity > self.timeout_seconds
