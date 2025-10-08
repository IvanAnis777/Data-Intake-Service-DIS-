from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional
from app.database.connection import Base


class Item(Base):
    """SQLAlchemy модель для Item"""
    __tablename__ = "items"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    sku = Column(String(100), unique=True, index=True, nullable=False)
    title = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ItemCreate(BaseModel):
    """Pydantic модель для создания Item"""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "sku": "ITEM-001",
                "title": "Sample Item"
            }
        }
    )
    
    sku: str
    title: str


class ItemResponse(BaseModel):
    """Pydantic модель для ответа с Item"""
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 1,
                "sku": "ITEM-001",
                "title": "Sample Item",
                "created_at": "2024-01-01T12:00:00Z"
            }
        }
    )
    
    id: int
    sku: str
    title: str
    created_at: datetime
