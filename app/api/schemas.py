from typing import Any

from pydantic import BaseModel, Field

from ..domain.triage import TriageResult, Urgency


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    session_id: str | None = Field(default=None, min_length=1)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    image_b64: str | None = Field(default=None, min_length=1)
    image_mime: str | None = Field(default=None, min_length=1)


class AuditEvent(BaseModel):
    module: str
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    turn_id: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    response: str
    urgency: Urgency | None = None
    events: list[AuditEvent] = Field(default_factory=list)
    path: str | None = None


class QueuedChatResponse(BaseModel):
    job_id: str
    session_id: str
    status: str


class AuditRecord(BaseModel):
    """One audit-trail row as served by GET /v1/audit."""

    id: int
    session_id: str | None = None
    turn_id: str | None = None
    module: str
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: float


class AuditListResponse(BaseModel):
    events: list[AuditRecord]


class JobResponse(BaseModel):
    job_id: str
    status: str
    result: ChatResponse | None = None
    error: str | None = None


class TriageRequest(BaseModel):
    message: str = Field(min_length=1)
    image_b64: str | None = Field(default=None, min_length=1)
    image_mime: str | None = Field(default=None, min_length=1)


class ImageMeta(BaseModel):
    path: str
    sha256: str
    mime: str
    size_bytes: int


class TriageResponse(BaseModel):
    urgency: Urgency
    red_flags: list[str] = Field(default_factory=list)
    text_findings: list[str] = Field(default_factory=list)
    image_findings: list[str] = Field(default_factory=list)
    reasoning: str = ""
    body_part: str | None = None
    body_part_confidence: float | None = None
    limitations: list[str] = Field(default_factory=list)
    model: str
    source: str  # "rules" | "text" | "vision"
    image: ImageMeta | None = None

    @classmethod
    def from_result(
        cls,
        result: TriageResult,
        *,
        model: str,
        source: str,
        image: ImageMeta | None = None,
    ) -> "TriageResponse":
        return cls(
            **result.to_dict(),
            model=model,
            source=source,
            image=image,
        )


class AppConfigResponse(BaseModel):
    """Public client configuration: upload limits the UI pre-checks against.

    Mirrors what the backend enforces on every upload regardless; served so
    the frontend never hardcodes backend policy.
    """

    image_max_bytes: int
    image_allowed_mime: list[str]


class AddonInfo(BaseModel):
    name: str
    description: str
    enabled: bool
    disclaimer_level: str


class AddonListResponse(BaseModel):
    addons: list[AddonInfo]


class AddonToggleRequest(BaseModel):
    enabled: bool


class SessionMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str
    # Pipeline turn that produced this message (None for legacy rows).
    turn_id: str | None = None


class SessionHistoryResponse(BaseModel):
    session_id: str
    created_at: float
    last_activity: float
    messages: list[SessionMessage]


class RecentChat(BaseModel):
    """One conversation in the most-recent-activity listing."""

    session_id: str
    created_at: float
    last_activity: float
    message_count: int
    preview: str | None = None


class RecentChatsResponse(BaseModel):
    chats: list[RecentChat]
