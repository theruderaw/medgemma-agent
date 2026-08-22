import asyncio
import json
import threading
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from ..core.config import settings
from ..core.db import SessionLocal
from ..core.logging import get_logger
from ..core.models import AuditEventRow

logger = get_logger("app.audit")


def trim_llm_payload(payload: dict[str, Any], cap: int) -> dict[str, Any]:
    """Deep-trim long string values (raw LLM output) in an audit payload.

    LLM-generated content — triage raw output, routing reasoning, specialist
    notes, tool-call arguments, and final replies — is capped at ``cap`` chars
    before it is persisted, keeping the audit trail compact while preserving
    the beginning of the content plus the truncation length.
    """

    def trim_value(value: Any) -> Any:
        if isinstance(value, str):
            return _trim_text(value, cap)
        if isinstance(value, list):
            return [trim_value(item) for item in value]
        if isinstance(value, dict):
            return {key: trim_value(item) for key, item in value.items()}
        return value

    return trim_value(payload)


def _trim_text(text: str, cap: int) -> str:
    if len(text) <= cap:
        return text
    return f"{text[:cap]}…[+{len(text) - cap} chars trimmed]"


class AuditLogger(ABC):
    """Append-only audit sink. Implementations must never update or delete rows."""

    @abstractmethod
    async def append(
        self,
        *,
        module: str,
        event_type: str,
        payload: dict[str, Any],
        session_id: str | None = None,
        turn_id: str | None = None,
    ) -> None:
        """Record one immutable audit event."""


class JsonFileAuditLogger(AuditLogger):
    """Append-only JSONL audit trail.

    Every event is appended as a single JSON object on its own line. Writes use
    a thread lock plus O_APPEND semantics so concurrent tasks (and the worker
    process) cannot interleave lines. Records are never updated or deleted.
    """

    def __init__(self, path: str | Path, *, trim_llm_chars: int = 0) -> None:
        self.path = Path(path)
        self.trim_llm_chars = trim_llm_chars
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    async def append(
        self,
        *,
        module: str,
        event_type: str,
        payload: dict[str, Any],
        session_id: str | None = None,
        turn_id: str | None = None,
    ) -> None:
        record = {
            "timestamp": time.time(),
            "module": module,
            "event_type": event_type,
            "payload": trim_llm_payload(payload, self.trim_llm_chars) if self.trim_llm_chars else payload,
            "session_id": session_id,
            "turn_id": turn_id,
        }
        await asyncio.to_thread(self._write_line, json.dumps(record, ensure_ascii=False))

    def _write_line(self, line: str) -> None:
        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
                handle.flush()


class PostgresAuditLogger(AuditLogger):
    """Persists audit events to the append-only audit_events table.

    Only INSERT statements are issued; there is no update or delete path. Rows
    are never modified after insertion, giving an immutable audit trail.
    """

    def __init__(self, url: str) -> None:
        self.url = url

    async def append(
        self,
        *,
        module: str,
        event_type: str,
        payload: dict[str, Any],
        session_id: str | None = None,
        turn_id: str | None = None,
    ) -> None:
        async with SessionLocal() as db:
            db.add(
                AuditEventRow(
                    session_id=session_id,
                    turn_id=turn_id,
                    module=module,
                    event_type=event_type,
                    payload=payload,
                    created_at=time.time(),
                )
            )
            await db.commit()


class CompositeAuditLogger(AuditLogger):
    """Fans every event out to multiple sinks. Sink failures are logged, never propagated."""

    def __init__(self, sinks: list[AuditLogger]) -> None:
        self.sinks = sinks

    async def append(
        self,
        *,
        module: str,
        event_type: str,
        payload: dict[str, Any],
        session_id: str | None = None,
        turn_id: str | None = None,
    ) -> None:
        for sink in self.sinks:
            try:
                await sink.append(
                    module=module,
                    event_type=event_type,
                    payload=payload,
                    session_id=session_id,
                    turn_id=turn_id,
                )
            except Exception as exc:  # noqa: BLE001 - a sink must never break a transaction
                logger.error(
                    "audit.sink_failed",
                    sink=type(sink).__name__,
                    module=module,
                    event_type=event_type,
                    error=repr(exc),
                )


def build_audit_logger() -> AuditLogger:
    """Every event lands in the JSONL file and is mirrored to Postgres.

    Both sinks are unconditional: no transaction can run without a durable,
    queryable audit record.
    """
    return CompositeAuditLogger(
        [
            JsonFileAuditLogger(settings.audit_file, trim_llm_chars=settings.audit_llm_cap_chars),
            PostgresAuditLogger(settings.database_url),
        ]
    )


audit = build_audit_logger()