import structlog
import uuid
import time
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Callable

# Настройка structlog для JSON логирования
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware для логирования запросов с correlation-id"""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Генерируем correlation-id если его нет
        correlation_id = request.headers.get("x-correlation-id", str(uuid.uuid4()))
        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        
        # Добавляем в контекст логирования
        log = logger.bind(
            correlation_id=correlation_id,
            request_id=request_id,
            method=request.method,
            url=str(request.url),
            client_ip=request.client.host if request.client else None
        )
        
        # Логируем начало запроса
        start_time = time.time()
        log.info("Request started")
        
        # Добавляем headers в response
        response = await call_next(request)
        response.headers["x-correlation-id"] = correlation_id
        response.headers["x-request-id"] = request_id
        
        # Логируем завершение запроса
        process_time = time.time() - start_time
        log.info(
            "Request completed",
            status_code=response.status_code,
            process_time=process_time
        )
        
        return response

