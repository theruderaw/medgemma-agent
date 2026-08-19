from dataclasses import dataclass

from ..config import settings
from ..llm import llm
from ..prompts import (
    SPECIALIST_CONTEXT,
    SPECIALIST_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    TRIAGE_CONTEXT,
)
from ..routes import should_route_to_specialist
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
    floor, then the soft triage + specialist signals, and finally synthesize
    the assistant reply with the main model.
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

        specialist_context = None
        if should_route_to_specialist(message):
            specialist_note = await llm.chat(
                [
                    {"role": "system", "content": SPECIALIST_SYSTEM_PROMPT},
                    {"role": "user", "content": message},
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
        await sessions.append(session, "assistant", text)
        await sessions.save(session)

    return TurnResult(session_id=session.session_id, response=text)