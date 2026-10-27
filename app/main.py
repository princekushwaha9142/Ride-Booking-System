import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import health
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import engine

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("startup", extra={"environment": settings.environment})
    yield
    engine.dispose()  
    logger.info("shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.project_name, version="0.1.0", lifespan=lifespan)
    app.include_router(health.router)  # ops endpoints live outside /api/v1
    return app


app = create_app()