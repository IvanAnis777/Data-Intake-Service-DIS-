from sqlalchemy import Column, Integer, String, DateTime, Index
from sqlalchemy.sql import func
from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import Optional, List
from app.database.connection import Base


class Item(Base):
    """SQLAlchemy модель для Item"""
    __tablename__ = "items"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    sku = Column(String(100), unique=True, index=True, nullable=False)
    title = Column(String(255), nullable=False)
    status = Column(String(20), default='active', nullable=False)
    brand = Column(String(100), nullable=True)
    category = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Составной индекс для курсорной пагинации
    __table_args__ = (
        Index('idx_items_cursor_pagination', 'created_at', 'id'),
    )


class ItemCreate(BaseModel):
    """Pydantic модель для создания Item"""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "sku": "ITEM-001",
                "title": "Sample Item",
                "status": "active",
                "brand": "Brand A",
                "category": "Electronics"
            }
        }
    )
    
    sku: str
    title: str
    status: str = "active"
    brand: Optional[str] = None
    category: Optional[str] = None


class ItemResponse(BaseModel):
    """Pydantic модель для ответа с Item"""
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 1,
                "sku": "ITEM-001",
                "title": "Sample Item",
                "status": "active",
                "brand": "Brand A",
                "category": "Electronics",
                "created_at": "2024-01-01T12:00:00Z"
            }
        }
    )
    
    id: int
    sku: str
    title: str
    status: str
    brand: Optional[str] = None
    category: Optional[str] = None
    created_at: datetime


class ItemListRequest(BaseModel):
    """Pydantic модель для запроса списка Items с курсорной пагинацией"""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "limit": 100,
                "cursor": "eyJjcmVhdGVkX2F0IjogIjIwMjQtMDEtMTVUMTA6MzA6MDBaIiwgImlkIjogMTIzfQ==",
                "status": "active",
                "brand": "Brand A",
                "category": "Electronics"
            }
        }
    )
    
    limit: int = Field(default=100, ge=1, le=1000, description="Количество элементов на странице")
    cursor: Optional[str] = Field(default=None, description="Курсор для пагинации")
    status: Optional[str] = Field(default=None, description="Фильтр по статусу")
    brand: Optional[str] = Field(default=None, description="Фильтр по бренду")
    category: Optional[str] = Field(default=None, description="Фильтр по категории")


class ItemListResponse(BaseModel):
    """Pydantic модель для ответа со списком Items"""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "items": [
                    {
                        "id": 1,
                        "sku": "ITEM-001",
                        "title": "Sample Item",
                        "created_at": "2024-01-01T12:00:00Z"
                    }
                ],
                "next_cursor": "eyJjcmVhdGVkX2F0IjogIjIwMjQtMDEtMTVUMTA6MzA6MDBaIiwgImlkIjogMTIzfQ==",
                "has_more": True
            }
        }
    )
    
    items: List[ItemResponse]
    next_cursor: Optional[str] = Field(default=None, description="Курсор для следующей страницы")
    has_more: bool = Field(description="Есть ли еще страницы")
