import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import get_db

logger = logging.getLogger(__name__)
router = APIRouter(tags=["ops"])


@router.get("/health")
def health() -> dict[str, str]:
    
    return {"status": "ok"}


@router.get("/ready", response_model=None)
def ready(db: Session = Depends(get_db)) -> dict[str, str] | JSONResponse:
    
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.exception("readiness check failed")  # details go to logs only
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    return {"status": "ready"}