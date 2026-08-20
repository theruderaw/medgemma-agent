import httpx
from alembic import command
from alembic.config import Config
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api import ChatRequest, ChatResponse
from .core.config import settings
from .services.chat import run_chat_turn
from .sessions import SessionExpiredError, sessions


def _run_migrations() -> None:
    cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    command.upgrade(cfg, "head")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.session_store_type == "postgres" or settings.audit_enabled:
        _run_migrations()
    yield
    await sessions.close()


app = FastAPI(title="MedGemma Agent", version="0.2.0", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=Path(__file__).resolve().parent.parent / "static"), name="static")


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(Path(__file__).resolve().parent.parent / "static" / "index.html")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    try:
        result = await run_chat_turn(
            request.message,
            session_id=request.session_id,
            temperature=request.temperature,
        )
    except SessionExpiredError:
        raise HTTPException(
            status_code=410,
            detail="Session expired or not found. Start a new session.",
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Model server error: {exc.response.status_code}")
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail=f"Model server unreachable: {exc}")
    return ChatResponse(
        session_id=result.session_id,
        response=result.response,
        urgency=result.urgency,
        events=result.events or [],
    )


@app.delete("/sessions/{session_id}", status_code=204)
async def reset_session(session_id: str) -> None:
    removed = await sessions.reset(session_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Session not found")