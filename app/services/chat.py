import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import uuid4

import structlog

from ..audit import audit, trim_llm_payload
from ..core.config import settings
from ..core.images import ProcessedImage, persist_image
from ..core.logging import get_logger
from ..llm import StreamExtractor, extract_answer, llm
from ..prompts import (
    ROUTING_SYSTEM_PROMPT,
    SPECIALIST_CONTEXT,
    SPECIALIST_SYSTEM_PROMPT,
    SPECIALIST_TOOL,
    SYSTEM_PROMPT,
    triage_context_for,
)
from ..routes import RouteCategory, RouteDecision, parse_tool_calls
from ..safety import EMERGENCY_RESPONSE, detect_emergency
from ..sessions import sessions
from ..triage import Urgency
from .triage import run_triage, triage_model_for

logger = get_logger("app.services.chat")


@dataclass
class TurnResult:
    session_id: str
    response: str
    urgency: Urgency | None = None
    events: list[dict] | None = None


async def run_emergency_turn(
    message: str,
    *,
    session_id: str | None = None,
    on_event: Callable[[dict], Awaitable[None]] | None = None,
) -> TurnResult:
    """Handle a hardcoded red-flag match as one turn.

    Shared by sync mode and the queued-mode API (which runs the safety floor
    synchronously before enqueueing), so the emergency short-circuit is
    identical regardless of processing mode: session append, save, and the
    `safety_override` audit event are all recorded here.
    """
    provided_session_id = session_id is not None
    resolved_id = session_id or sessions.new_id()
    turn_id = uuid4().hex
    events: list[dict] = []

    structlog.contextvars.bind_contextvars(session_id=resolved_id, turn_id=turn_id)
    logger.info("turn.started", mode="emergency")

    async with await sessions.lock(resolved_id):
        session = await sessions.load_or_create(resolved_id, must_exist=provided_session_id)
        await sessions.append(session, "user", message)

        category = detect_emergency(message)
        response_text = EMERGENCY_RESPONSE.format(category=category)
        await sessions.append(session, "assistant", response_text)
        await sessions.save(session)

        event = {
            "module": "safety",
            "event_type": "safety_override",
            "payload": trim_llm_payload(
                {"category": category, "message": message},
                settings.audit_llm_cap_chars,
            ),
            "turn_id": turn_id,
        }
        events.append(event)
        if on_event is not None:
            await on_event(event)
        await audit.append(
            module=event["module"],
            event_type=event["event_type"],
            payload=event["payload"],
            session_id=resolved_id,
            turn_id=turn_id,
        )

    logger.info("turn.completed", mode="emergency", events=len(events))
    structlog.contextvars.unbind_contextvars("session_id", "turn_id")

    return TurnResult(
        session_id=session.session_id,
        response=response_text,
        urgency=Urgency.EMERGENCY,
        events=events,
    )


async def run_chat_turn(
    message: str,
    *,
    session_id: str | None = None,
    temperature: float = 0.7,
    image: ProcessedImage | None = None,
    on_event: Callable[[dict], Awaitable[None]] | None = None,
    on_token: Callable[[str], Awaitable[None]] | None = None,
    on_specialist_token: Callable[[str], Awaitable[None]] | None = None,
) -> TurnResult:
    """Execute one full chat turn.

    Lock the session, append the user message, run the deterministic safety
    floor (independent — always first), then the extended triage signal, then
    let Qwen route contextually via function calling: it either requests the
    clinical specialist or answers directly. Symptom-related turns get a
    MedGemma note injected before the final Qwen synthesis.

    When ``image`` is supplied (a sanitized upload), it is persisted and
    audited, triage dispatches to the multimodal vision tier, and an attached
    image can never be dropped by routing: if the router does not request the
    specialist, the decision is deterministically overridden so the image
    always reaches MedGemma.

    When ``on_event`` is supplied, every audit event is forwarded through it
    as it happens (live pipeline visibility). When ``on_token`` is supplied,
    the final reply is streamed token-by-token. When ``on_specialist_token``
    is supplied, the MedGemma note is likewise streamed while it is generated
    (the longest stage) instead of blocking silently.
    """
    provided_session_id = session_id is not None
    resolved_id = session_id or sessions.new_id()
    turn_id = uuid4().hex
    events: list[dict] = []
    turn_urgency: Urgency | None = None

    structlog.contextvars.bind_contextvars(session_id=resolved_id, turn_id=turn_id)
    logger.info("turn.started", mode="chat", has_image=image is not None)

    async def record(module: str, event_type: str, payload: dict) -> None:
        payload = trim_llm_payload(payload, settings.audit_llm_cap_chars)
        event = {"module": module, "event_type": event_type, "payload": payload, "turn_id": turn_id}
        events.append(event)
        if on_event is not None:
            await on_event(event)
        await audit.append(
            module=module,
            event_type=event_type,
            payload=payload,
            session_id=session_id or resolved_id,
            turn_id=turn_id,
        )
        logger.info("event.recorded", event_type=event_type, module=module)

    async with await sessions.lock(resolved_id):
        session = await sessions.load_or_create(resolved_id, must_exist=provided_session_id)

        stored_message = message
        if image is not None:
            image_path = persist_image(image, turn_id)
            stored_message = f"{message}\n\n[image attached: {image_path}]"
        await sessions.append(session, "user", stored_message)
        if image is not None:
            await record(
                "image",
                "image_received",
                {
                    "path": image.path,
                    "sha256": image.sha256,
                    "mime": image.mime,
                    "size_bytes": image.size_bytes,
                },
            )

        if settings.triage_enabled:
            emergency = detect_emergency(message)
            if emergency is not None:
                response_text = EMERGENCY_RESPONSE.format(category=emergency)
                await sessions.append(session, "assistant", response_text)
                await sessions.save(session)
                await record(
                    "safety",
                    "safety_override",
                    {"category": emergency, "message": message},
                )
                logger.info("turn.completed", mode="chat", result="emergency", events=len(events))
                structlog.contextvars.unbind_contextvars("session_id", "turn_id")
                return TurnResult(
                    session_id=session.session_id,
                    response=response_text,
                    urgency=Urgency.EMERGENCY,
                    events=events,
                )

        history = sessions.build_messages(session)

        triage_context = None
        if settings.triage_enabled:
            triage_result = await run_triage(message, image_b64=image.b64 if image else None)
            turn_urgency = triage_result.urgency
            triage_context = triage_context_for(triage_result)
            await record(
                "triage",
                "triage_result",
                {
                    **triage_result.to_dict(),
                    "model": triage_model_for(image is not None),
                },
            )

        routing_messages = [{"role": "system", "content": ROUTING_SYSTEM_PROMPT}]
        if triage_context:
            routing_messages.append({"role": "system", "content": triage_context})
        routing_messages += history

        routing = await llm.chat_with_tools(
            routing_messages,
            tools=[SPECIALIST_TOOL],
            temperature=temperature,
            model=settings.model_name,
        )
        decision = parse_tool_calls(routing.tool_calls)
        image_override = False
        if image is not None and decision.category is not RouteCategory.SYMPTOM_RELATED:
            # An attached image is clinical evidence: it must never be dropped
            # because the text router did not request the specialist.
            decision = RouteDecision(RouteCategory.SYMPTOM_RELATED, "image attached")
            image_override = True
        await record(
            "router",
            "routing_decision",
            {
                "category": decision.category.value,
                "reason": decision.reason,
                "raw_content": routing.content,
                "tool_calls": routing.tool_calls,
                "image_override": image_override,
            },
        )

        if decision.category is RouteCategory.SYMPTOM_RELATED:
            reason = decision.reason or message
            specialist_messages = [
                {"role": "system", "content": SPECIALIST_SYSTEM_PROMPT},
                {"role": "user", "content": reason},
            ]
            if on_specialist_token is not None:
                cleaner = StreamExtractor()
                if image is not None:
                    deltas = llm.chat_with_images_stream(
                        specialist_messages,
                        images=[image.b64],
                        model=settings.specialist_model_name,
                        temperature=temperature,
                    )
                else:
                    deltas = llm.chat_stream(
                        specialist_messages,
                        model=settings.specialist_model_name,
                        temperature=temperature,
                    )
                async for delta in deltas:
                    chunk = cleaner.feed(delta)
                    if chunk:
                        await on_specialist_token(chunk)
                specialist_note = cleaner.finish()
                if specialist_note:
                    await on_specialist_token(specialist_note)
            elif image is not None:
                specialist_note = await llm.chat_with_images(
                    specialist_messages,
                    images=[image.b64],
                    model=settings.specialist_model_name,
                    temperature=temperature,
                )
            else:
                specialist_note = await llm.chat(
                    specialist_messages,
                    model=settings.specialist_model_name,
                )
            await record(
                "specialist",
                "specialist_output",
                {
                    "reason": reason,
                    "note": specialist_note,
                    "model": settings.specialist_model_name,
                    "with_image": image is not None,
                },
            )
            specialist_context = SPECIALIST_CONTEXT.format(note=specialist_note)

            messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            if triage_context:
                messages.append({"role": "system", "content": triage_context})
            if specialist_context:
                messages.append({"role": "system", "content": specialist_context})
            messages += history
            if on_token is not None:
                cleaner = StreamExtractor()
                parts: list[str] = []
                async for delta in llm.chat_stream(
                    messages, temperature=temperature, model=settings.model_name
                ):
                    chunk = cleaner.feed(delta)
                    if chunk:
                        parts.append(chunk)
                        await on_token(chunk)
                tail = cleaner.finish()
                if tail:
                    parts.append(tail)
                text = "".join(parts)
            else:
                text = await llm.chat(messages, temperature=temperature, model=settings.model_name)
        else:
            text = extract_answer(routing.content)
            if on_token is not None:
                for i in range(0, len(text), 3):
                    await on_token(text[i : i + 3])

        text = extract_answer(text)
        await sessions.append(session, "assistant", text)
        await sessions.save(session)
        await record(
            "chat",
            "turn_completed",
            {"response": text, "temperature": temperature, "model": settings.model_name},
        )

    logger.info("turn.completed", mode="chat", result="ok", events=len(events))
    structlog.contextvars.unbind_contextvars("session_id", "turn_id")

    return TurnResult(
        session_id=session.session_id,
        response=text,
        urgency=turn_urgency,
        events=events,
    )


_STREAM_HEARTBEAT_SECONDS = 2.0


async def run_chat_turn_stream(
    message: str,
    *,
    session_id: str | None = None,
    temperature: float = 0.7,
    image: ProcessedImage | None = None,
):
    """Stream one chat turn to an SSE client — never silent.

    Runs the same pipeline as :func:`run_chat_turn` on a background task and
    yields event dicts continuously:

    - ``{"type": "start", "session_id": ...}`` immediately on connect
    - ``{"type": "pipeline", "event": <audit event>}`` as each pipeline stage
      completes (image_received, triage_result, routing_decision,
      specialist_output, safety_override)
    - ``{"type": "specialist_token", "content": ...}`` while MedGemma writes
      its note (the longest stage)
    - ``{"type": "token", "content": ...}`` for the final reply — empty-string
      heartbeats are emitted whenever nothing else is ready, so the token
      channel flows 100% of the time
    - ``{"type": "done", "session_id", "response", "urgency", "events"}`` once
      the turn completes

    Errors from the pipeline are re-raised for the transport layer to map.
    """
    queue: asyncio.Queue[tuple[str, object]] = asyncio.Queue()

    async def on_token(chunk: str) -> None:
        await queue.put(("token", chunk))

    async def on_specialist_token(chunk: str) -> None:
        await queue.put(("specialist_token", chunk))

    async def on_event(event: dict) -> None:
        await queue.put(("pipeline", event))

    async def runner() -> None:
        try:
            result = await run_chat_turn(
                message,
                session_id=session_id,
                temperature=temperature,
                image=image,
                on_event=on_event,
                on_token=on_token,
                on_specialist_token=on_specialist_token,
            )
            queue.put_nowait(("result", result))
        except BaseException as exc:  # noqa: BLE001 - forwarded to the caller
            queue.put_nowait(("error", exc))

    task = asyncio.create_task(runner())
    try:
        yield {"type": "start", "session_id": session_id}
        while True:
            try:
                kind, payload = await asyncio.wait_for(
                    queue.get(), timeout=_STREAM_HEARTBEAT_SECONDS
                )
            except asyncio.TimeoutError:
                yield {"type": "token", "content": ""}
                continue
            if kind == "token":
                yield {"type": "token", "content": payload}
            elif kind == "specialist_token":
                yield {"type": "specialist_token", "content": payload}
            elif kind == "pipeline":
                yield {"type": "pipeline", "event": payload}
            elif kind == "error":
                raise payload
            else:
                result = payload
                break
    finally:
        if not task.done():
            task.cancel()

    yield {
        "type": "done",
        "session_id": result.session_id,
        "response": result.response,
        "urgency": result.urgency.value if result.urgency is not None else None,
        "events": result.events or [],
    }