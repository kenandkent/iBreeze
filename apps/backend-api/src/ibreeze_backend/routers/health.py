"""Health check router."""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ibreeze_backend.db.session import get_db_session
from ibreeze_backend.observability.logging_config import get_logger

logger = get_logger("ibreeze.health")
router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict:
    logger.debug("health_check")
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness_check(
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    logger.debug("readiness_check_start")
    try:
        await db.execute(text("SELECT 1"))
        logger.debug("readiness_check_success")
        return {"status": "ready", "database": "connected"}
    except Exception as e:
        logger.warning("readiness_check_failed", extra={"reason": str(e)})
        return {"status": "not ready", "database": str(e)}
