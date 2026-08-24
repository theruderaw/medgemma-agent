from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api.routes import router
from .bootstrap import bootstrap_addons
from .core.logging import setup_logging
from .sessions import sessions


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    bootstrap_addons()
    yield
    await sessions.close()


def create_app() -> FastAPI:
    setup_logging()
    return FastAPI(title="MedGemma Agent", version="0.4.0", lifespan=lifespan)


app = create_app()
app.include_router(router)
