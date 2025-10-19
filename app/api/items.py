from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from app.database.connection import get_db
from app.models.item import Item, ItemCreate, ItemResponse, ItemListResponse
from app.utils.cursor import encode_cursor, validate_cursor
from typing import Optional
import structlog

logger = structlog.get_logger()
router = APIRouter()


@router.post("/items", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
async def create_item(item: ItemCreate, db: Session = Depends(get_db)):
    """
    Создание нового Item
    
    Поддерживает идемпотентность через заголовок Idempotency-Key.
    При повторном запросе с тем же ключом и телом возвращает тот же результат.
    
    Headers:
        Idempotency-Key (optional): Уникальный ключ для обеспечения идемпотентности.
                                   Должен быть 1-255 символов, содержать только буквы,
                                   цифры, дефисы и подчёркивания.
    
    Examples:
        POST /api/v1/items
        Idempotency-Key: client-request-123
        Content-Type: application/json
        
        {
            "sku": "ITEM-001",
            "title": "Sample Item",
            "status": "active",
            "brand": "Brand A",
            "category": "Electronics"
        }
    """
    logger.info("Creating new item", sku=item.sku, title=item.title)
    
    # Проверяем, что SKU уникален
    existing_item = db.query(Item).filter(Item.sku == item.sku).first()
    if existing_item:
        logger.warning("Item with SKU already exists", sku=item.sku)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Item with SKU '{item.sku}' already exists"
        )
    
    # Создаем новый Item
    db_item = Item(
        sku=item.sku, 
        title=item.title,
        status=item.status,
        brand=item.brand,
        category=item.category
    )
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    
    logger.info("Item created successfully", item_id=db_item.id, sku=db_item.sku)
    return db_item


@router.get("/items/{item_id}", response_model=ItemResponse)
async def get_item(item_id: int, db: Session = Depends(get_db)):
    """
    Получение Item по ID
    """
    logger.info("Getting item", item_id=item_id)
    
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        logger.warning("Item not found", item_id=item_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item with ID {item_id} not found"
        )
    
    return item


@router.get("/items", response_model=ItemListResponse)
async def list_items(
    limit: int = Query(default=100, ge=1, le=1000, description="Количество элементов на странице"),
    cursor: Optional[str] = Query(default=None, description="Курсор для пагинации"),
    status: Optional[str] = Query(default=None, description="Фильтр по статусу"),
    brand: Optional[str] = Query(default=None, description="Фильтр по бренду"),
    category: Optional[str] = Query(default=None, description="Фильтр по категории"),
    db: Session = Depends(get_db)
):
    """
    Получение списка Items с курсорной пагинацией
    
    Использует keyset pagination на паре (created_at, id) для стабильной и производительной пагинации.
    Поддерживает фильтрацию по статусу, бренду и категории.
    """
    logger.info("Listing items with cursor pagination", 
                limit=limit, cursor=cursor, status=status, brand=brand, category=category)
    
    # Валидируем курсор
    cursor_data = validate_cursor(cursor)
    
    # Строим базовый запрос
    query = db.query(Item)
    
    # Применяем фильтры
    filters = []
    if status:
        filters.append(Item.status == status)
    if brand:
        filters.append(Item.brand == brand)
    if category:
        filters.append(Item.category == category)
    
    if filters:
        query = query.filter(and_(*filters))
    
    # Применяем курсорную пагинацию
    if cursor_data:
        cursor_created_at, cursor_id = cursor_data
        # Для SQLite используем составное условие
        query = query.filter(
            or_(
                Item.created_at < cursor_created_at,
                and_(Item.created_at == cursor_created_at, Item.id < cursor_id)
            )
        )
    
    # Сортируем по created_at DESC, id DESC для стабильного порядка
    query = query.order_by(Item.created_at.desc(), Item.id.desc())
    
    # Берем на один элемент больше для проверки has_more
    items = query.limit(limit + 1).all()
    
    # Определяем has_more и обрезаем лишний элемент
    has_more = len(items) > limit
    if has_more:
        items = items[:limit]
    
    # Генерируем next_cursor из последнего элемента
    next_cursor = None
    if has_more and items:
        last_item = items[-1]
        # Получаем фактические значения из SQLAlchemy объекта
        # last_item.created_at и last_item.id уже содержат фактические значения
        next_cursor = encode_cursor(last_item.created_at, last_item.id)  # type: ignore
    
    logger.info("Items listed successfully", 
                items_count=len(items), has_more=has_more, next_cursor=next_cursor)
    
    return ItemListResponse(
        items=[ItemResponse.model_validate(item) for item in items],
        next_cursor=next_cursor,
        has_more=has_more
    )
