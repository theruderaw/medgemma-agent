import httpx
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .config import settings
from .llm import llm
from .prompts import SPECIALIST_CONTEXT, SPECIALIST_SYSTEM_PROMPT, SYSTEM_PROMPT
from .router import should_route_to_specialist
from .sessions import SessionExpiredError, sessions


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await sessions.close()


app = FastAPI(title="MedGemma Agent", version="0.2.0", lifespan=lifespan)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    session_id: str | None = Field(default=None, min_length=1)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)


class ChatResponse(BaseModel):
    session_id: str
    response: str


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    provided_session_id = request.session_id is not None
    session_id = request.session_id or sessions.new_id()
    try:
        async with await sessions.lock(session_id):
            session = await sessions.load_or_create(session_id, must_exist=provided_session_id)
            await sessions.append(session, "user", request.message)
            history = sessions.build_messages(session)

            specialist_note = None
            if should_route_to_specialist(request.message):
                specialist_note = await llm.chat(
                    [
                        {"role": "system", "content": SPECIALIST_SYSTEM_PROMPT},
                        {"role": "user", "content": request.message},
                    ],
                    model=settings.specialist_model_name,
                )

            messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            if specialist_note:
                messages.append(
                    {"role": "system", "content": SPECIALIST_CONTEXT.format(note=specialist_note)}
                )
            messages += history
            text = await llm.chat(messages, temperature=request.temperature, model=settings.model_name)
            await sessions.append(session, "assistant", text)
            await sessions.save(session)
    except SessionExpiredError:
        raise HTTPException(
            status_code=410,
            detail="Session expired or not found. Start a new session.",
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Model server error: {exc.response.status_code}")
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail=f"Model server unreachable: {exc}")
    return ChatResponse(session_id=session.session_id, response=text)


@app.delete("/sessions/{session_id}", status_code=204)
async def reset_session(session_id: str) -> None:
    removed = await sessions.reset(session_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Session not found")