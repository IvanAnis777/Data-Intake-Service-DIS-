from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field
from app.models.item import ItemCreate, ItemResponse


class BulkItemStatus(str, Enum):
    """Статусы обработки отдельного item в bulk операции"""
    SUCCESS = "success"
    ERROR = "error"
    WARNING = "warning"


class BulkErrorCode(str, Enum):
    """Коды ошибок для bulk операций"""
    DUPLICATE_SKU = "DUPLICATE_SKU"
    INVALID_DATA = "INVALID_DATA"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    SKU_TOO_LONG = "SKU_TOO_LONG"
    TITLE_REQUIRED = "TITLE_REQUIRED"
    INVALID_STATUS = "INVALID_STATUS"


class BulkItemResult(BaseModel):
    """Результат обработки одного item в bulk операции"""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "index": 0,
                "status": "success",
                "status_code": 201,
                "data": {
                    "id": 123,
                    "sku": "ITEM-001",
                    "title": "Sample Item",
                    "status": "active",
                    "created_at": "2024-01-15T10:30:00Z"
                }
            }
        }
    )
    
    index: int = Field(description="Индекс item в исходном массиве")
    status: BulkItemStatus = Field(description="Статус обработки")
    status_code: int = Field(description="HTTP статус код")
    
    # Данные для успешного результата
    data: Optional[ItemResponse] = Field(default=None, description="Созданный item")
    
    # Данные для ошибки
    error_code: Optional[BulkErrorCode] = Field(default=None, description="Код ошибки")
    error_message: Optional[str] = Field(default=None, description="Сообщение об ошибке")
    hint: Optional[str] = Field(default=None, description="Подсказка для исправления")


class BulkImportRequest(BaseModel):
    """Запрос на массовый импорт items"""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "items": [
                    {
                        "sku": "ITEM-001",
                        "title": "Sample Item 1",
                        "status": "active",
                        "brand": "Brand A",
                        "category": "Electronics"
                    },
                    {
                        "sku": "ITEM-002", 
                        "title": "Sample Item 2",
                        "status": "active"
                    }
                ]
            }
        }
    )
    
    items: List[ItemCreate] = Field(
        description="Массив items для создания",
        min_length=1,
        max_length=1000
    )


class BulkImportResponse(BaseModel):
    """Ответ на массовый импорт items"""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total": 100,
                "successful": 95,
                "failed": 5,
                "results": [
                    {
                        "index": 0,
                        "status": "success",
                        "status_code": 201,
                        "data": {
                            "id": 123,
                            "sku": "ITEM-001",
                            "title": "Sample Item",
                            "status": "active",
                            "created_at": "2024-01-15T10:30:00Z"
                        }
                    },
                    {
                        "index": 1,
                        "status": "error",
                        "status_code": 409,
                        "error_code": "DUPLICATE_SKU",
                        "error_message": "Item with SKU 'ITEM-002' already exists",
                        "hint": "Use different SKU or update existing item"
                    }
                ]
            }
        }
    )
    
    total: int = Field(description="Общее количество items в запросе")
    successful: int = Field(description="Количество успешно обработанных items")
    failed: int = Field(description="Количество items с ошибками")
    results: List[BulkItemResult] = Field(description="Детальные результаты по каждому item")


class BulkErrorResponse(BaseModel):
    """Ответ при ошибке bulk операции (якорные ошибки)"""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "detail": "Request too large",
                "error_code": "REQUEST_TOO_LARGE",
                "max_items": 1000,
                "max_size_mb": 10
            }
        }
    )
    
    detail: str = Field(description="Описание ошибки")
    error_code: str = Field(description="Код ошибки")
    max_items: Optional[int] = Field(default=None, description="Максимальное количество items")
    max_size_mb: Optional[int] = Field(default=None, description="Максимальный размер в MB")


# Константы для лимитов
BULK_MAX_ITEMS = 1000
BULK_MAX_SIZE_MB = 10
BULK_MAX_SIZE_BYTES = BULK_MAX_SIZE_MB * 1024 * 1024
