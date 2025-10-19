import asyncio
from datetime import datetime
from app.database.connection import SessionLocal
from app.models.idempotency import IdempotencyKey
import structlog

logger = structlog.get_logger()


async def cleanup_expired_idempotency_keys() -> int:
    """
    Удаляет истёкшие ключи идемпотентности
    
    Returns:
        Количество удалённых записей
    """
    db = SessionLocal()
    try:
        # Находим истёкшие ключи
        expired_keys = db.query(IdempotencyKey).filter(
            IdempotencyKey.expires_at < datetime.utcnow()
        ).all()
        
        count = len(expired_keys)
        
        if count > 0:
            # Удаляем истёкшие ключи
            for key in expired_keys:
                db.delete(key)
            
            db.commit()
            
            logger.info(
                "Cleaned up expired idempotency keys",
                count=count,
                cleanup_time=datetime.utcnow()
            )
        else:
            logger.debug("No expired idempotency keys to clean up")
        
        return count
        
    except Exception as e:
        db.rollback()
        logger.error(
            "Error during idempotency keys cleanup",
            error=str(e)
        )
        return 0
    
    finally:
        db.close()


async def cleanup_task_loop(interval_minutes: int = 10):
    """
    Фоновая задача для периодической очистки истёкших ключей
    
    Args:
        interval_minutes: Интервал очистки в минутах
    """
    logger.info(
        "Starting idempotency cleanup task",
        interval_minutes=interval_minutes
    )
    
    while True:
        try:
            await asyncio.sleep(interval_minutes * 60)
            await cleanup_expired_idempotency_keys()
        except Exception as e:
            logger.error(
                "Error in cleanup task loop",
                error=str(e)
            )
            # Продолжаем работу даже при ошибке
            await asyncio.sleep(60)  # Ждём минуту перед следующей попыткой


def get_cleanup_stats() -> dict:
    """
    Получает статистику по ключам идемпотентности
    
    Returns:
        Словарь со статистикой
    """
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        
        # Общее количество ключей
        total_keys = db.query(IdempotencyKey).count()
        
        # Количество истёкших ключей
        expired_keys = db.query(IdempotencyKey).filter(
            IdempotencyKey.expires_at < now
        ).count()
        
        # Количество ключей в processing
        processing_keys = db.query(IdempotencyKey).filter(
            IdempotencyKey.status == 'processing'
        ).count()
        
        # Количество ключей в completed
        completed_keys = db.query(IdempotencyKey).filter(
            IdempotencyKey.status == 'completed'
        ).count()
        
        return {
            "total_keys": total_keys,
            "expired_keys": expired_keys,
            "processing_keys": processing_keys,
            "completed_keys": completed_keys,
            "cleanup_needed": expired_keys > 0
        }
        
    except Exception as e:
        logger.error(
            "Error getting cleanup stats",
            error=str(e)
        )
        return {
            "total_keys": 0,
            "expired_keys": 0,
            "processing_keys": 0,
            "completed_keys": 0,
            "cleanup_needed": False,
            "error": str(e)
        }
    
    finally:
        db.close()
