from dataclasses import dataclass

from ..config import settings
from ..llm import extract_answer, llm
from ..prompts import (
    ROUTING_SYSTEM_PROMPT,
    SPECIALIST_CONTEXT,
    SPECIALIST_SYSTEM_PROMPT,
    SPECIALIST_TOOL,
    SYSTEM_PROMPT,
    TRIAGE_CONTEXT,
)
from ..routes import RouteCategory, parse_tool_calls
from ..safety import EMERGENCY_RESPONSE, detect_emergency
from ..sessions import sessions
from ..triage import parse_triage_urgency


@dataclass
class TurnResult:
    session_id: str
    response: str


async def run_chat_turn(
    message: str,
    *,
    session_id: str | None = None,
    temperature: float = 0.7,
) -> TurnResult:
    """Execute one full chat turn.

    Lock the session, append the user message, run the deterministic safety
    floor (independent — always first), then a soft triage signal, then let Qwen
    route contextually via function calling: it either requests the clinical
    specialist or answers directly. Symptom-related turns get a MedGemma note
    injected before the final Qwen synthesis.
    """
    provided_session_id = session_id is not None
    resolved_id = session_id or sessions.new_id()

    async with await sessions.lock(resolved_id):
        session = await sessions.load_or_create(resolved_id, must_exist=provided_session_id)
        await sessions.append(session, "user", message)

        if settings.triage_enabled:
            emergency = detect_emergency(message)
            if emergency is not None:
                response_text = EMERGENCY_RESPONSE.format(category=emergency)
                await sessions.append(session, "assistant", response_text)
                await sessions.save(session)
                return TurnResult(session_id=session.session_id, response=response_text)

        history = sessions.build_messages(session)

        triage_context = None
        if settings.triage_enabled:
            raw_triage = await llm.triage(message)
            urgency = parse_triage_urgency(raw_triage)
            triage_context = TRIAGE_CONTEXT.format(urgency=urgency)

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

        if decision.category is RouteCategory.SYMPTOM_RELATED:
            reason = decision.reason or message
            specialist_note = await llm.chat(
                [
                    {"role": "system", "content": SPECIALIST_SYSTEM_PROMPT},
                    {"role": "user", "content": reason},
                ],
                model=settings.specialist_model_name,
            )
            specialist_context = SPECIALIST_CONTEXT.format(note=specialist_note)

            messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            if triage_context:
                messages.append({"role": "system", "content": triage_context})
            if specialist_context:
                messages.append({"role": "system", "content": specialist_context})
            messages += history
            text = await llm.chat(messages, temperature=temperature, model=settings.model_name)
        else:
            text = extract_answer(routing.content)

        text = extract_answer(text)
        await sessions.append(session, "assistant", text)
        await sessions.save(session)

    return TurnResult(session_id=session.session_id, response=text)