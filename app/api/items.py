from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database.connection import get_db
from app.models.item import Item, ItemCreate, ItemResponse
from typing import List
import structlog

logger = structlog.get_logger()
router = APIRouter()


@router.post("/items", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
async def create_item(item: ItemCreate, db: Session = Depends(get_db)):
    """
    Создание нового Item
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
    db_item = Item(sku=item.sku, title=item.title)
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


@router.get("/items", response_model=list[ItemResponse])
async def list_items(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """
    Получение списка Items (простая пагинация, позже заменим на курсорную)
    """
    logger.info("Listing items", skip=skip, limit=limit)
    
    items = db.query(Item).offset(skip).limit(limit).all()
    return items
