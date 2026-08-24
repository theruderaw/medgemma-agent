from .models import Session


class SessionStore:
    """Persistence contract for sessions. Postgres is the only implementation.

    Sessions and messages live in relational tables; history is retained in
    full (no trimming) so audit and evaluation can reconstruct conversations.
    Conversations are permanent: no store method deletes or hides a session
    implicitly — only an explicit ``delete`` call (user-driven reset) does.
    """

    retains_full_history: bool = True

    async def get(self, session_id: str) -> Session | None:
        """Return the session, or None if it does not exist."""
        raise NotImplementedError

    async def save(self, session: Session) -> None:
        """Persist the session and refresh its last-activity timestamp."""
        raise NotImplementedError

    async def delete(self, session_id: str) -> bool:
        """Remove the session; return True if it existed."""
        raise NotImplementedError

    async def aclose(self) -> None:
        pass
