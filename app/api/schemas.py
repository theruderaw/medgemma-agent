from typing import Any

from pydantic import BaseModel, Field

from ..triage import TriageResult, Urgency


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


class QueuedChatResponse(BaseModel):
    job_id: str
    session_id: str
    status: str


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
