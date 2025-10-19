import time
from typing import List, Tuple, Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.models.item import Item, ItemCreate, ItemResponse
from app.models.bulk import (
    BulkImportResponse, 
    BulkItemResult, 
    BulkItemStatus, 
    BulkErrorCode,
    BULK_MAX_ITEMS,
    BULK_MAX_SIZE_BYTES,
    BULK_MAX_SIZE_MB
)
import structlog

logger = structlog.get_logger()


class BulkService:
    """Сервис для обработки массовых операций с items"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def process_bulk_import(self, items: List[ItemCreate]) -> BulkImportResponse:
        """
        Обрабатывает массовый импорт items
        
        Args:
            items: Список items для создания
            
        Returns:
            BulkImportResponse с результатами обработки
        """
        start_time = time.time()
        results = []
        
        logger.info(
            "Starting bulk import",
            total_items=len(items)
        )
        
        for index, item_data in enumerate(items):
            try:
                result = self._process_single_item(index, item_data)
                results.append(result)
                
            except Exception as e:
                logger.error(
                    "Unexpected error processing item",
                    index=index,
                    sku=getattr(item_data, 'sku', 'unknown'),
                    error=str(e)
                )
                results.append(self._create_error_result(
                    index=index,
                    status_code=500,
                    error_code=BulkErrorCode.INTERNAL_ERROR,
                    error_message=f"Internal server error: {str(e)}",
                    hint="Please try again or contact support"
                ))
        
        processing_time = time.time() - start_time
        
        # Подсчитываем статистику
        successful = sum(1 for r in results if r.status == BulkItemStatus.SUCCESS)
        failed = len(results) - successful
        
        logger.info(
            "Bulk import completed",
            total_items=len(items),
            successful=successful,
            failed=failed,
            processing_time_ms=int(processing_time * 1000)
        )
        
        return BulkImportResponse(
            total=len(items),
            successful=successful,
            failed=failed,
            results=results
        )
    
    def _process_single_item(self, index: int, item_data: ItemCreate) -> BulkItemResult:
        """
        Обрабатывает один item в отдельной транзакции
        
        Args:
            index: Индекс item в исходном массиве
            item_data: Данные item для создания
            
        Returns:
            BulkItemResult с результатом обработки
        """
        try:
            # Валидация данных
            self._validate_item_data(item_data)
            
            # Проверка на дубликат SKU
            existing_item = self.db.query(Item).filter(Item.sku == item_data.sku).first()
            if existing_item:
                return self._create_error_result(
                    index=index,
                    status_code=409,
                    error_code=BulkErrorCode.DUPLICATE_SKU,
                    error_message=f"Item with SKU '{item_data.sku}' already exists",
                    hint="Use different SKU or update existing item"
                )
            
            # Создание item в отдельной транзакции
            db_item = Item(
                sku=item_data.sku,
                title=item_data.title,
                status=item_data.status,
                brand=item_data.brand,
                category=item_data.category
            )
            
            self.db.add(db_item)
            self.db.commit()
            self.db.refresh(db_item)
            
            logger.debug(
                "Item created successfully",
                index=index,
                sku=item_data.sku,
                item_id=db_item.id
            )
            
            return self._create_success_result(index, db_item)
            
        except IntegrityError as e:
            self.db.rollback()
            logger.warning(
                "Integrity error creating item",
                index=index,
                sku=item_data.sku,
                error=str(e)
            )
            return self._create_error_result(
                index=index,
                status_code=409,
                error_code=BulkErrorCode.DUPLICATE_SKU,
                error_message=f"Item with SKU '{item_data.sku}' already exists",
                hint="Use different SKU or update existing item"
            )
        except Exception as e:
            self.db.rollback()
            logger.error(
                "Error creating item",
                index=index,
                sku=item_data.sku,
                error=str(e)
            )
            return self._create_error_result(
                index=index,
                status_code=500,
                error_code=BulkErrorCode.INTERNAL_ERROR,
                error_message=f"Failed to create item: {str(e)}",
                hint="Please check your data and try again"
            )
    
    def _validate_item_data(self, item_data: ItemCreate) -> None:
        """
        Валидирует данные item
        
        Args:
            item_data: Данные item для валидации
            
        Raises:
            ValueError: При ошибках валидации
        """
        # Проверка обязательных полей
        if not item_data.sku or not item_data.sku.strip():
            raise ValueError("SKU is required")
        
        if not item_data.title or not item_data.title.strip():
            raise ValueError("Title is required")
        
        # Проверка длины SKU
        if len(item_data.sku) > 100:
            raise ValueError(f"SKU too long: {len(item_data.sku)} characters (max 100)")
        
        # Проверка длины title
        if len(item_data.title) > 255:
            raise ValueError(f"Title too long: {len(item_data.title)} characters (max 255)")
        
        # Проверка статуса
        valid_statuses = ['active', 'inactive', 'archived']
        if item_data.status and item_data.status not in valid_statuses:
            raise ValueError(f"Invalid status: '{item_data.status}'. Valid values: {valid_statuses}")
        
        # Проверка длины brand
        if item_data.brand and len(item_data.brand) > 100:
            raise ValueError(f"Brand too long: {len(item_data.brand)} characters (max 100)")
        
        # Проверка длины category
        if item_data.category and len(item_data.category) > 100:
            raise ValueError(f"Category too long: {len(item_data.category)} characters (max 100)")
    
    def _create_success_result(self, index: int, item: Item) -> BulkItemResult:
        """Создаёт результат успешной обработки"""
        return BulkItemResult(
            index=index,
            status=BulkItemStatus.SUCCESS,
            status_code=201,
            data=ItemResponse.model_validate(item)
        )
    
    def _create_error_result(
        self, 
        index: int, 
        status_code: int, 
        error_code: BulkErrorCode, 
        error_message: str, 
        hint: Optional[str] = None
    ) -> BulkItemResult:
        """Создаёт результат ошибки"""
        return BulkItemResult(
            index=index,
            status=BulkItemStatus.ERROR,
            status_code=status_code,
            error_code=error_code,
            error_message=error_message,
            hint=hint
        )


def validate_bulk_request_size(request_size_bytes: int) -> Tuple[bool, str]:
    """
    Валидирует размер запроса
    
    Args:
        request_size_bytes: Размер запроса в байтах
        
    Returns:
        Tuple[bool, str]: (is_valid, error_message)
    """
    if request_size_bytes > BULK_MAX_SIZE_BYTES:
        return False, f"Request too large: {request_size_bytes / (1024*1024):.1f}MB (max {BULK_MAX_SIZE_MB}MB)"
    
    return True, ""


def validate_bulk_request_items_count(items_count: int) -> Tuple[bool, str]:
    """
    Валидирует количество items в запросе
    
    Args:
        items_count: Количество items
        
    Returns:
        Tuple[bool, str]: (is_valid, error_message)
    """
    if items_count > BULK_MAX_ITEMS:
        return False, f"Too many items: {items_count} (max {BULK_MAX_ITEMS})"
    
    if items_count == 0:
        return False, "Items array cannot be empty"
    
    return True, ""
