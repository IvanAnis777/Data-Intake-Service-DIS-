from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from app.database.connection import get_db
from app.models.bulk import (
    BulkImportRequest, 
    BulkImportResponse, 
    BulkErrorResponse,
    BULK_MAX_ITEMS,
    BULK_MAX_SIZE_MB
)
from app.services.bulk_service import (
    BulkService, 
    validate_bulk_request_size, 
    validate_bulk_request_items_count
)
import structlog

logger = structlog.get_logger()
router = APIRouter()


@router.post(
    "/items:bulk", 
    response_model=BulkImportResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "All items processed successfully"},
        207: {"description": "Mixed success/errors - some items failed"},
        400: {"description": "Invalid request format or validation errors"},
        413: {"description": "Request too large"},
        422: {"description": "Validation errors"}
    }
)
async def bulk_import_items(
    request: BulkImportRequest,
    http_request: Request,
    db: Session = Depends(get_db)
):
    """
    Массовый импорт items с поддержкой частичной успешности
    
    Обрабатывает массив items и возвращает детальный отчёт о результатах.
    Каждый item обрабатывается в отдельной транзакции, поэтому ошибка одного
    item не влияет на обработку других.
    
    **Лимиты:**
    - Максимум 1000 items за запрос
    - Максимум 10MB размер запроса
    
    **Коды ответов:**
    - 200 OK: Все items обработаны успешно
    - 207 Multi-Status: Смешанные результаты (часть успешна, часть с ошибками)
    - 400 Bad Request: Неверный формат запроса или превышен лимит items
    - 413 Payload Too Large: Превышен лимит размера запроса
    
    **Примеры:**
    
    Успешный запрос:
    ```json
    {
        "items": [
            {"sku": "ITEM-001", "title": "Item 1", "status": "active"},
            {"sku": "ITEM-002", "title": "Item 2", "status": "active"}
        ]
    }
    ```
    
    Ответ с ошибками:
    ```json
    {
        "total": 2,
        "successful": 1,
        "failed": 1,
        "results": [
            {
                "index": 0,
                "status": "success",
                "status_code": 201,
                "data": {"id": 123, "sku": "ITEM-001", ...}
            },
            {
                "index": 1,
                "status": "error",
                "status_code": 409,
                "error_code": "DUPLICATE_SKU",
                "error_message": "Item with SKU 'ITEM-002' already exists"
            }
        ]
    }
    ```
    """
    # Получаем размер запроса
    request_size = len(await http_request.body())
    
    logger.info(
        "Bulk import request received",
        items_count=len(request.items),
        request_size_bytes=request_size
    )
    
    # Валидация размера запроса (якорная ошибка)
    is_valid_size, size_error = validate_bulk_request_size(request_size)
    if not is_valid_size:
        logger.warning(
            "Request too large",
            request_size_bytes=request_size,
            max_size_bytes=BULK_MAX_SIZE_MB * 1024 * 1024
        )
        raise HTTPException(
            status_code=status.HTTP_413_PAYLOAD_TOO_LARGE,
            detail=BulkErrorResponse(
                detail=size_error,
                error_code="REQUEST_TOO_LARGE",
                max_size_mb=BULK_MAX_SIZE_MB
            ).model_dump()
        )
    
    # Валидация количества items (якорная ошибка)
    is_valid_count, count_error = validate_bulk_request_items_count(len(request.items))
    if not is_valid_count:
        logger.warning(
            "Too many items in request",
            items_count=len(request.items),
            max_items=BULK_MAX_ITEMS
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=BulkErrorResponse(
                detail=count_error,
                error_code="TOO_MANY_ITEMS",
                max_items=BULK_MAX_ITEMS
            ).model_dump()
        )
    
    # Обработка bulk импорта
    bulk_service = BulkService(db)
    response = bulk_service.process_bulk_import(request.items)
    
    # Определяем статус код ответа
    if response.failed == 0:
        # Все успешно
        status_code = status.HTTP_200_OK
        logger.info(
            "Bulk import completed successfully",
            total_items=response.total,
            successful=response.successful
        )
    else:
        # Есть ошибки - возвращаем 207 Multi-Status
        status_code = status.HTTP_207_MULTI_STATUS
        logger.info(
            "Bulk import completed with errors",
            total_items=response.total,
            successful=response.successful,
            failed=response.failed
        )
    
    # Создаём ответ с правильным статус кодом
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=status_code,
        content=response.model_dump(mode='json')
    )


@router.get("/items:bulk/limits")
async def get_bulk_limits():
    """
    Получить лимиты для bulk операций
    
    Returns:
        Информация о лимитах bulk API
    """
    return {
        "max_items": BULK_MAX_ITEMS,
        "max_size_mb": BULK_MAX_SIZE_MB,
        "max_size_bytes": BULK_MAX_SIZE_MB * 1024 * 1024,
        "description": "Limits for bulk import operations"
    }
