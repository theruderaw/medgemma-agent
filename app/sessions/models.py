import time
from dataclasses import dataclass, field


class SessionExpiredError(Exception):
    pass


@dataclass
class Session:
    session_id: str
    messages: list[dict] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    persisted_count: int = 0

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