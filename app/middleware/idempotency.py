from typing import Callable
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response as StarletteResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.database.connection import SessionLocal
from app.models.idempotency import IdempotencyKey
from app.utils.idempotency import (
    compute_request_hash,
    validate_idempotency_key,
    generate_idempotency_response,
    create_conflict_response,
    create_processing_conflict_response,
    create_invalid_key_response,
    IDEMPOTENCY_KEY_HEADER,
    DEFAULT_TTL_SECONDS
)
import structlog
import json


logger = structlog.get_logger()


# Упрощённый подход - сохраняем только статус код


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """
    Middleware для обработки идемпотентности POST запросов
    
    Обрабатывает заголовок Idempotency-Key и обеспечивает идемпотентность операций
    """
    
    def __init__(self, app, ttl_seconds: int = DEFAULT_TTL_SECONDS):
        super().__init__(app)
        self.ttl_seconds = ttl_seconds
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Основная логика middleware для обработки идемпотентности
        """
        logger.debug("IdempotencyMiddleware called", method=request.method, path=request.url.path)
        
        # Проверяем, что это POST запрос
        if request.method != "POST":
            logger.debug("Not a POST request, skipping idempotency")
            return await call_next(request)
        
        # Читаем заголовок Idempotency-Key
        idempotency_key = request.headers.get(IDEMPOTENCY_KEY_HEADER)
        
        # Если заголовка нет - пропускаем идемпотентность
        if idempotency_key is None:
            logger.debug("No idempotency key provided, skipping idempotency")
            return await call_next(request)
        
        # Валидируем ключ
        if not validate_idempotency_key(idempotency_key):
            logger.warning(
                "Invalid idempotency key format",
                key=idempotency_key,
                path=request.url.path
            )
            return create_invalid_key_response(idempotency_key)
        
        # Читаем тело запроса
        body = await request.body()
        request_hash = compute_request_hash(body)
        
        logger.info(
            "Processing idempotency request",
            key=idempotency_key,
            request_hash=request_hash,
            path=request.url.path
        )
        
        # Обрабатываем идемпотентность
        db = SessionLocal()
        try:
            # Проверяем существование ключа
            existing_key = db.query(IdempotencyKey).filter(
                IdempotencyKey.key == idempotency_key
            ).first()
            
            if existing_key:
                # Проверяем, не истёк ли ключ
                if existing_key.is_expired():
                    logger.info(
                        "Idempotency key expired, allowing new request",
                        key=idempotency_key,
                        expired_at=existing_key.expires_at
                    )
                    # Удаляем истёкший ключ
                    db.delete(existing_key)
                    db.commit()
                    # Продолжаем как новый ключ
                    return await self._handle_new_key(
                        idempotency_key, request_hash, request, call_next, db
                    )
                else:
                    # Обрабатываем существующий ключ
                    return await self._handle_existing_key(
                        existing_key, request_hash, idempotency_key, db
                    )
            else:
                return await self._handle_new_key(
                    idempotency_key, request_hash, request, call_next, db
                )
        
        except Exception as e:
            logger.error(
                "Error in idempotency middleware",
                key=idempotency_key,
                error=str(e),
                path=request.url.path
            )
            db.rollback()
            # В случае ошибки пропускаем идемпотентность
            return await call_next(request)
        
        finally:
            db.close()
    
    async def _handle_existing_key(
        self, 
        existing_key: IdempotencyKey, 
        request_hash: str, 
        idempotency_key: str,
        db: Session
    ) -> Response:
        """
        Обрабатывает существующий ключ идемпотентности
        """
        
        # Проверяем статус ключа
        if existing_key.status == "processing":
            logger.warning(
                "Idempotency key already in processing state",
                key=idempotency_key,
                created_at=existing_key.created_at
            )
            return create_processing_conflict_response(idempotency_key)
        
        # Ключ в состоянии completed
        if existing_key.status == "completed":
            # Проверяем хеш запроса
            if existing_key.request_hash == request_hash:
                logger.info(
                    "Idempotency hit - returning cached response",
                    key=idempotency_key,
                    status_code=existing_key.response_status_code
                )
                return generate_idempotency_response(existing_key)
            else:
                logger.warning(
                    "Idempotency key conflict - different request body",
                    key=idempotency_key,
                    existing_hash=existing_key.request_hash,
                    new_hash=request_hash
                )
                return create_conflict_response(idempotency_key)
        
        # Неизвестный статус
        logger.error(
            "Unknown idempotency key status",
            key=idempotency_key,
            status=existing_key.status
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"}
        )
    
    async def _handle_new_key(
        self,
        idempotency_key: str,
        request_hash: str,
        request: Request,
        call_next: Callable,
        db: Session
    ) -> Response:
        """
        Обрабатывает новый ключ идемпотентности
        """
        try:
            # Создаём новую запись
            new_key = IdempotencyKey.create_with_ttl(
                key=idempotency_key,
                request_hash=request_hash,
                ttl_seconds=self.ttl_seconds
            )
            db.add(new_key)
            db.commit()
            
            logger.info(
                "Created new idempotency key",
                key=idempotency_key,
                expires_at=new_key.expires_at
            )
            
            # Обрабатываем запрос
            response = await call_next(request)
            
            # Сохраняем полный ответ для идемпотентности
            response_body = await self._capture_response_body(response)
            
            # Проверяем, что body успешно захвачен
            if not response_body:
                logger.error(
                    "Failed to capture response body, rolling back transaction",
                    key=idempotency_key,
                    status_code=response.status_code
                )
                db.rollback()
                db.delete(new_key)
                db.commit()
                return response
            
            # Сохраняем ответ и логируем
            new_key.mark_completed(
                status_code=response.status_code,
                response_body=response_body
            )
            db.commit()
            
            logger.info(
                "Saved idempotency response",
                key=new_key.key,
                status_code=response.status_code,
                body_length=len(response_body)
            )
            
            return response
            
        except IntegrityError:
            # Ключ уже существует (race condition)
            db.rollback()
            logger.warning(
                "Race condition detected - key already exists",
                key=idempotency_key
            )
            
            # Получаем существующий ключ
            existing_key = db.query(IdempotencyKey).filter(
                IdempotencyKey.key == idempotency_key
            ).first()
            
            if existing_key:
                return await self._handle_existing_key(
                    existing_key, request_hash, idempotency_key, db
                )
            else:
                # Неожиданная ситуация
                return JSONResponse(
                    status_code=500,
                    content={"detail": "Internal server error"}
                )
        
        except Exception as e:
            db.rollback()
            logger.error(
                "Error creating idempotency key",
                key=idempotency_key,
                error=str(e)
            )
            # В случае ошибки продолжаем без идемпотентности
            return await call_next(request)
    
    async def _capture_response_body(self, response: Response) -> str:
        """
        Захватывает тело ответа для сохранения в идемпотентности
        """
        try:
            # Проверяем наличие body_iterator
            if not hasattr(response, 'body_iterator'):
                logger.error(
                    "Response has no body_iterator",
                    response_type=type(response).__name__,
                    status_code=getattr(response, 'status_code', None)
                )
                return ""
            
            # Пытаемся получить body через итератор
            response_chunks = []
            try:
                async for chunk in response.body_iterator:
                    if isinstance(chunk, bytes):
                        response_chunks.append(chunk)
                    else:
                        response_chunks.append(chunk.encode('utf-8'))
            except Exception as e:
                logger.error(
                    "Error iterating over response body",
                    error=str(e),
                    error_type=type(e).__name__
                )
                return ""
            
            # Собираем все чанки в один body
            response_bytes = b"".join(response_chunks)
            
            # Декодируем в UTF-8
            try:
                response_text = response_bytes.decode('utf-8')
            except UnicodeDecodeError as e:
                logger.error(
                    "Error decoding response body as UTF-8",
                    error=str(e),
                    body_length=len(response_bytes)
                )
                return ""
            
            # Важно: пересоздаём итератор для дальнейшего использования
            async def new_body_iterator():
                yield response_bytes
            
            response.body_iterator = new_body_iterator()
            
            logger.debug(
                "Captured response body via iterator",
                body_length=len(response_text),
                body_preview=response_text[:100] if response_text else ""
            )
            
            return response_text
            
        except Exception as e:
            logger.error(
                "Unexpected error capturing response body",
                error=str(e),
                error_type=type(e).__name__,
                status_code=getattr(response, 'status_code', None),
                response_type=type(response).__name__
            )
            return ""
