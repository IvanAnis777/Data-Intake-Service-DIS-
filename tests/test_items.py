import pytest
import uuid
from fastapi.testclient import TestClient
from app.main import app
from app.database.connection import get_db, engine
from app.models.item import Base

# Создаем тестовую базу данных в памяти
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
test_engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

# Создаем таблицы для тестов
Base.metadata.create_all(bind=test_engine)

client = TestClient(app)

def get_unique_sku():
    """Генерирует уникальный SKU для тестов"""
    return f"TEST-{uuid.uuid4().hex[:8].upper()}"


def test_create_item():
    """Тест создания Item"""
    item_data = {
        "sku": get_unique_sku(),
        "title": "Test Item"
    }
    
    response = client.post("/api/v1/items", json=item_data)
    assert response.status_code == 201
    
    data = response.json()
    assert data["sku"] == item_data["sku"]
    assert data["title"] == item_data["title"]
    assert "id" in data
    assert "created_at" in data


def test_create_duplicate_item():
    """Тест создания дублирующегося Item"""
    unique_sku = get_unique_sku()
    item_data = {
        "sku": unique_sku,
        "title": "Duplicate Item"
    }
    
    # Создаем первый Item
    response1 = client.post("/api/v1/items", json=item_data)
    assert response1.status_code == 201
    
    # Пытаемся создать дубликат
    response2 = client.post("/api/v1/items", json=item_data)
    assert response2.status_code == 409
    assert "already exists" in response2.json()["detail"]


def test_get_item():
    """Тест получения Item по ID"""
    # Сначала создаем Item
    item_data = {
        "sku": get_unique_sku(),
        "title": "Get Test Item"
    }
    create_response = client.post("/api/v1/items", json=item_data)
    item_id = create_response.json()["id"]
    
    # Получаем Item
    response = client.get(f"/api/v1/items/{item_id}")
    assert response.status_code == 200
    
    data = response.json()
    assert data["id"] == item_id
    assert data["sku"] == item_data["sku"]
    assert data["title"] == item_data["title"]


def test_get_nonexistent_item():
    """Тест получения несуществующего Item"""
    response = client.get("/api/v1/items/99999")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


def test_list_items():
    """Тест получения списка Items"""
    response = client.get("/api/v1/items")
    assert response.status_code == 200
    
    data = response.json()
    assert isinstance(data, list)
