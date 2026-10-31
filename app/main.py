import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import health
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.db.session import engine

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("startup environment=%s", settings.environment)
    yield
    engine.dispose()  # graceful shutdown: close pooled connections
    logger.info("shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.project_name, version="0.1.0", lifespan=lifespan)
    register_exception_handlers(app)
    app.include_router(health.router)  # ops endpoints live outside /api/v1
    app.include_router(api_router)
    return app


app = create_app()