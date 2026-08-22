import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import uuid4

import structlog

from ..audit import audit, trim_llm_payload
from ..core.config import settings
from ..core.images import ProcessedImage, persist_image
from ..core.logging import get_logger
from ..features import registry as feature_registry
from ..features.medication_interaction import MedicationPair
from ..llm import StreamExtractor, extract_answer, llm
from ..prompts import (
    ROUTING_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    triage_context_for,
)
from ..routes import RouteCategory, RouteDecision, parse_tool_calls
from ..safety import EMERGENCY_RESPONSE, detect_emergency, enforce_safety_invariants, run_output_guard
from ..sessions import sessions
from ..specialist import SpecialistResult
from ..triage import TriageResult, Urgency
from .triage import run_triage

logger = get_logger("app.services.chat")

# Pipeline path identifiers: every turn is traceable to exactly one.
PATH_EMERGENCY_OVERRIDE = "emergency_override"
PATH_MEDICAL_SPECIALIST = "medical_specialist"
PATH_QWEN_DIRECT = "qwen_direct"


@dataclass
class TurnResult:
    session_id: str
    response: str
    urgency: Urgency | None = None
    events: list[dict] | None = None
    path: str | None = None


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
        path=PATH_EMERGENCY_OVERRIDE,
    )


async def run_chat_turn(
    message: str,
    *,
    session_id: str | None = None,
    temperature: float = 0.7,
    image: ProcessedImage | None = None,
    triage: bool = False,
    on_event: Callable[[dict], Awaitable[None]] | None = None,
    on_token: Callable[[str], Awaitable[None]] | None = None,
    on_specialist_token: Callable[[str], Awaitable[None]] | None = None,
) -> TurnResult:
    """Execute one full chat turn.

    Lock the session, append the user message, run the deterministic safety
    floor (independent — always first, never skipped), then — only when
    ``triage`` is requested for this turn — the MedGemma text-triage signal.
    Qwen then routes contextually via function calling: it either requests the
    clinical specialist or answers directly. Symptom-related turns get a
    MedGemma structured assessment injected before the final Qwen synthesis.

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
    turn_path: str | None = None

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

        # Deterministic red-flag floor: application code, no model call, runs
        # on every turn regardless of the triage opt-in.
        emergency = detect_emergency(message)
        if emergency is not None:
            response_text = EMERGENCY_RESPONSE.format(category=emergency)
            await sessions.append(session, "assistant", response_text)
            await sessions.save(session)
            await record(
                "safety",
                "safety_override",
                {
                    "category": emergency,
                    "message": message,
                    "path": PATH_EMERGENCY_OVERRIDE,
                },
            )
            logger.info(
                "turn.completed",
                mode="chat",
                result="emergency",
                path=PATH_EMERGENCY_OVERRIDE,
                events=len(events),
            )
            structlog.contextvars.unbind_contextvars("session_id", "turn_id")
            return TurnResult(
                session_id=session.session_id,
                response=response_text,
                urgency=Urgency.EMERGENCY,
                events=events,
                path=PATH_EMERGENCY_OVERRIDE,
            )

        history = sessions.build_messages(session)

        triage_result = None
        triage_context = None
        if triage:
            started = time.monotonic()
            triage_result = await run_triage(message)
            triage_ms = int((time.monotonic() - started) * 1000)
            turn_urgency = triage_result.urgency
            triage_context = triage_context_for(triage_result)
            await record(
                "triage",
                "triage_result",
                {
                    **triage_result.to_dict(),
                    "model": settings.triage_model_name,
                    "duration_ms": triage_ms,
                },
            )

        routing_messages = [{"role": "system", "content": ROUTING_SYSTEM_PROMPT}]
        if triage_context:
            routing_messages.append({"role": "system", "content": triage_context})
        routing_messages += history

        started = time.monotonic()
        routing = await llm.chat_with_tools(
            routing_messages,
            tools=feature_registry.tool_schemas(),
            temperature=temperature,
            model=settings.model_name,
        )
        routing_ms = int((time.monotonic() - started) * 1000)
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
                "duration_ms": routing_ms,
            },
        )

        specialist: SpecialistResult | TriageResult | MedicationPair | None = None
        feature = None
        if decision.category is RouteCategory.SYMPTOM_RELATED:
            feature = feature_registry.get(decision.feature_name)
            if feature is None:
                raise ValueError(f"unknown feature '{decision.feature_name}'")
            reason = decision.reason or message
            specialist_messages = [
                {"role": "system", "content": feature.system_prompt},
                {"role": "user", "content": reason},
            ]
            # The selected feature always returns a complete structured
            # result (format-constrained JSON) — uncertainty survives as
            # data, not prose that a downstream model may reinterpret. The
            # JSON streams in live: each delta is forwarded as it is generated.
            started = time.monotonic()
            specialist_parts: list[str] = []
            stream_model = getattr(settings, feature.model_setting)
            async for delta in llm.specialist_stream(
                specialist_messages,
                images=[image.b64] if image is not None else None,
                model=stream_model,
                output_format=feature.format_schema,
            ):
                specialist_parts.append(delta)
                if on_specialist_token is not None:
                    await on_specialist_token(delta)
            raw_specialist = "".join(specialist_parts)
            specialist = feature.parse(raw_specialist)
            specialist_ms = int((time.monotonic() - started) * 1000)
            await record(
                "specialist",
                "specialist_output",
                {
                    "reason": reason,
                    "result": specialist.to_dict(),
                    "model": stream_model,
                    "with_image": image is not None,
                    "duration_ms": specialist_ms,
                },
            )
            specialist_context = feature.context_for(specialist, image_analyzed=image is not None)

            messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            if triage_context:
                messages.append({"role": "system", "content": triage_context})
            if specialist_context:
                messages.append({"role": "system", "content": specialist_context})
            messages += history
            started = time.monotonic()
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
                    await on_token(tail)
                text = "".join(parts)
            else:
                text = await llm.chat(messages, temperature=temperature, model=settings.model_name)
            synthesis_ms = int((time.monotonic() - started) * 1000)
            turn_path = PATH_MEDICAL_SPECIALIST
        else:
            text = extract_answer(routing.content)
            synthesis_ms = 0
            turn_path = PATH_QWEN_DIRECT
            if on_token is not None:
                for i in range(0, len(text), 3):
                    await on_token(text[i : i + 3])

        text = extract_answer(text)

        # Deterministic safety invariants — application code, never an LLM,
        # always on regardless of OUTPUT_GUARDRAILS. The emergency floor here
        # makes an emergency triage impossible to downgrade.
        limitations = list(triage_result.limitations) if triage_result else []
        # Not every feature result carries uncertainty/body-part signals;
        # absent signals degrade to False (never to an invented claim).
        specialist_uncertain = (
            bool(specialist.uncertain) if specialist and hasattr(specialist, "uncertain") else False
        )
        if specialist:
            extra_limitations = getattr(specialist, "limitations", None) or []
            limitations += [item for item in extra_limitations if item not in limitations]
        body_part_unknown = (
            image is not None
            and specialist is not None
            and bool(getattr(specialist, "body_part_unknown", False))
        )
        enforced = enforce_safety_invariants(
            text,
            urgency=turn_urgency,
            message=message,
            specialist_uncertain=specialist_uncertain,
            limitations=limitations,
            body_part_unknown=body_part_unknown,
            image_analyzed=image is not None,
            safety_profile=feature.safety_profile if feature else None,
        )
        safety_blocked = bool(enforced.violations)
        if safety_blocked:
            await record(
                "safety",
                "safety_invariant",
                {
                    "violations": enforced.violations,
                    "actions": enforced.actions,
                    "original": text,
                    "final": enforced.text,
                },
            )
            text = enforced.text

        # Output guardrails are always on: every reply is judged before it is
        # stored or returned.
        guarded = await run_output_guard(
            text,
            urgency=turn_urgency,
            message=message,
            safety_profile=feature.safety_profile if feature else None,
        )
        if guarded.violations:
            safety_blocked = True
            await record(
                "safety",
                "output_guardrail",
                {
                    "violations": guarded.violations,
                    "actions": guarded.actions,
                    "original": text,
                    "final": guarded.text,
                },
            )
            if on_token is not None and guarded.text != text:
                if guarded.text.startswith(text):
                    await on_token(guarded.text[len(text) :])
                else:
                    await on_token(f"\n\n{guarded.text}")
            text = guarded.text
        await sessions.append(session, "assistant", text)
        await sessions.save(session)
        await record(
            "chat",
            "turn_completed",
            {
                "response": text,
                "temperature": temperature,
                "model": settings.model_name,
                "path": turn_path,
                "duration_ms": synthesis_ms,
                "specialist_uncertain": specialist_uncertain,
                "image_uncertain": body_part_unknown,
                "safety_blocked": safety_blocked,
            },
        )

    logger.info(
        "turn.completed",
        mode="chat",
        result="ok",
        path=turn_path,
        events=len(events),
    )
    structlog.contextvars.unbind_contextvars("session_id", "turn_id")

    return TurnResult(
        session_id=session.session_id,
        response=text,
        urgency=turn_urgency,
        events=events,
        path=turn_path,
    )

