import structlog
import uuid
import time
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Callable, Any
from app.utils.cursor import decode_cursor

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
        
        # Дополнительные метрики для курсорной пагинации
        extra_metrics = {}
        if request.url.path == "/api/v1/items" and request.method == "GET":
            pagination_metrics = self._get_pagination_metrics(request, process_time)
            extra_metrics.update(pagination_metrics)
        
        log.info(
            "Request completed",
            status_code=response.status_code,
            process_time=process_time,
            **extra_metrics
        )
        
        return response
    
    def _get_pagination_metrics(self, request: Request, process_time: float) -> dict[str, Any]:
        """Извлекает метрики для курсорной пагинации"""
        metrics = {
            "api.items.list.latency_ms": round(process_time * 1000, 2)
        }
        
        # Извлекаем параметры запроса
        query_params = request.query_params
        limit = query_params.get("limit")
        cursor = query_params.get("cursor")
        
        if limit:
            try:
                metrics["api.items.list.limit"] = int(limit)
            except ValueError:
                pass
        
        # Вычисляем глубину пагинации из курсора
        if cursor:
            try:
                decode_cursor(cursor)  # Проверяем валидность курсора
                # Глубина пагинации - это примерное количество страниц
                # В реальном приложении можно использовать более точные метрики
                metrics["api.items.list.pages_depth"] = "deep"  # cursor present
            except Exception:
                metrics["api.items.list.cursor_errors"] = 1
        else:
            metrics["api.items.list.pages_depth"] = "first"  # no cursor
        
        return metrics











