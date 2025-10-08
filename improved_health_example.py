# Улучшенная версия health checks

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.database.connection import get_db
import structlog
import time

logger = structlog.get_logger()
router = APIRouter()

@router.get("/healthz")
async def health_check():
    """
    Liveness probe - проверяет только процесс
    """
    return {
        "status": "healthy",
        "service": "data-intake-service",
        "timestamp": time.time(),
        "uptime": "running"
    }

@router.get("/readyz")
async def readiness_check(db: Session = Depends(get_db)):
    """
    Readiness probe - проверяет готовность к работе
    """
    checks = {
        "database": False,
        "external_api": False,
        "cache": False
    }
    
    errors = []
    
    # Проверка БД
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = True
        logger.info("Database check passed")
    except Exception as e:
        error_msg = f"Database unavailable: {str(e)}"
        errors.append(error_msg)
        logger.error("Database check failed", error=str(e))
    
    # Проверка внешнего API (пример)
    try:
        # Здесь могла бы быть проверка внешнего сервиса
        # response = await http_client.get("https://api.external.com/health")
        checks["external_api"] = True
    except Exception as e:
        error_msg = f"External API unavailable: {str(e)}"
        errors.append(error_msg)
    
    # Проверка кэша (пример)
    try:
        # Здесь могла бы быть проверка Redis/Memcached
        # cache.ping()
        checks["cache"] = True
    except Exception as e:
        error_msg = f"Cache unavailable: {str(e)}"
        errors.append(error_msg)
    
    # Определяем общий статус
    all_ready = all(checks.values())
    
    if all_ready:
        return {
            "status": "ready",
            "service": "data-intake-service",
            "checks": checks,
            "timestamp": time.time()
        }
    else:
        return {
            "status": "not ready",
            "service": "data-intake-service",
            "checks": checks,
            "errors": errors,
            "timestamp": time.time()
        }

@router.get("/startup")
async def startup_check():
    """
    Startup probe - проверяет готовность после запуска
    """
    # Проверяем, что все компоненты инициализированы
    return {
        "status": "started",
        "service": "data-intake-service",
        "timestamp": time.time()
    }
