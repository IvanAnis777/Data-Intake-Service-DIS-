import hashlib
import json
from fastapi import Response
from fastapi.responses import JSONResponse
import structlog

logger = structlog.get_logger()

# Константы
DEFAULT_TTL_SECONDS = 3600  # 1 час
IDEMPOTENCY_KEY_HEADER = "Idempotency-Key"
IDEMPOTENCY_KEY_MAX_LENGTH = 255
IDEMPOTENCY_KEY_MIN_LENGTH = 1


def compute_request_hash(body: bytes) -> str:
    """
    Вычисляет SHA-256 хеш тела запроса
    
    Args:
        body: Тело запроса в байтах
        
    Returns:
        SHA-256 хеш в виде hex строки
    """
    if not body:
        body = b""
    
    hash_obj = hashlib.sha256()
    hash_obj.update(body)
    return hash_obj.hexdigest()


def validate_idempotency_key(key: str) -> bool:
    """
    Валидирует формат ключа идемпотентности
    
    Args:
        key: Ключ идемпотентности
        
    Returns:
        True если ключ валидный, False иначе
    """
    if not key:
        return False
    
    if len(key) < IDEMPOTENCY_KEY_MIN_LENGTH or len(key) > IDEMPOTENCY_KEY_MAX_LENGTH:
        return False
    
    # Разрешены буквы, цифры, дефис, подчёркивание
    allowed_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
    if not all(c in allowed_chars for c in key):
        return False
    
    return True


def generate_idempotency_response(key_record) -> Response:
    """
    Генерирует ответ из сохранённого ключа идемпотентности
    
    Args:
        key_record: Запись IdempotencyKey из БД
        
    Returns:
        FastAPI Response с сохранёнными данными
    """
    try:
        # Проверяем, что response_body существует
        if not key_record.response_body:
            logger.error(
                "Empty response_body in idempotency key",
                idempotency_key=key_record.key
            )
            return JSONResponse(
                content={"detail": "Internal server error"},
                status_code=500
            )
        
        # Пытаемся распарсить как JSON
        try:
            response_data = json.loads(key_record.response_body)
            return JSONResponse(
                content=response_data,
                status_code=key_record.response_status_code or 200
            )
        except json.JSONDecodeError as e:
            logger.error(
                "Failed to parse cached response as JSON",
                idempotency_key=key_record.key,
                error=str(e),
                response_body_preview=key_record.response_body[:100]
            )
            # Если не JSON, возвращаем как текст
            from fastapi.responses import PlainTextResponse
            return PlainTextResponse(
                content=key_record.response_body,
                status_code=key_record.response_status_code or 200
            )
        
        # Логирование для JSON ответа
        logger.info(
            "Returning cached idempotency response",
            idempotency_key=key_record.key,
            status_code=key_record.response_status_code,
            cached_at=key_record.completed_at,
            response_size=len(key_record.response_body)
        )
        
    except Exception as e:
        logger.error(
            "Failed to generate idempotency response",
            idempotency_key=key_record.key,
            error=str(e)
        )
        return JSONResponse(
            content={"detail": "Internal server error"},
            status_code=500
        )


def create_conflict_response(key: str) -> JSONResponse:
    """
    Создаёт ответ при конфликте идемпотентности
    
    Args:
        key: Ключ идемпотентности
        
    Returns:
        JSONResponse с кодом 409
    """
    return JSONResponse(
        status_code=409,
        content={
            "detail": "Idempotency key already used with different request body",
            "error_code": "IDEMPOTENCY_KEY_CONFLICT",
            "idempotency_key": key
        }
    )


def create_processing_conflict_response(key: str) -> JSONResponse:
    """
    Создаёт ответ при конфликте processing состояния
    
    Args:
        key: Ключ идемпотентности
        
    Returns:
        JSONResponse с кодом 409
    """
    return JSONResponse(
        status_code=409,
        content={
            "detail": "Request with this idempotency key is already being processed",
            "error_code": "IDEMPOTENCY_KEY_PROCESSING",
            "idempotency_key": key
        }
    )


def create_invalid_key_response(key: str) -> JSONResponse:
    """
    Создаёт ответ при невалидном ключе идемпотентности
    
    Args:
        key: Ключ идемпотентности
        
    Returns:
        JSONResponse с кодом 400
    """
    return JSONResponse(
        status_code=400,
        content={
            "detail": f"Invalid idempotency key format. Key must be {IDEMPOTENCY_KEY_MIN_LENGTH}-{IDEMPOTENCY_KEY_MAX_LENGTH} characters long and contain only letters, numbers, hyphens, and underscores",
            "error_code": "INVALID_IDEMPOTENCY_KEY",
            "idempotency_key": key
        }
    )
