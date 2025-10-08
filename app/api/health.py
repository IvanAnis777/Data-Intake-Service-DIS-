from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.database.connection import get_db
import structlog

logger = structlog.get_logger()
router = APIRouter()


@router.get("/healthz")
async def health_check():
    """
    Health check endpoint для Kubernetes liveness probe
    Проверяет, что сервис запущен и отвечает
    """
    logger.info("Health check requested")
    return {"status": "healthy", "service": "data-intake-service"}


@router.get("/readyz")
async def readiness_check(db: Session = Depends(get_db)):
    """
    Readiness check endpoint для Kubernetes readiness probe
    Проверяет, что сервис готов принимать трафик (БД доступна)
    """
    try:
        # Простая проверка подключения к БД
        db.execute(text("SELECT 1"))
        logger.info("Readiness check passed")
        return {"status": "ready", "service": "data-intake-service"}
    except Exception as e:
        logger.error("Readiness check failed", error=str(e))
        return {"status": "not ready", "service": "data-intake-service", "error": str(e)}
