import uuid
from fastapi.testclient import TestClient
from app.main import app
from app.database.connection import get_db
from app.models.item import Base, Item
from app.models.bulk import BULK_MAX_ITEMS

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
    return f"BULK-{uuid.uuid4().hex[:8].upper()}"


class TestBulkImport:
    """Тесты bulk импорта items"""
    
    def setup_method(self):
        """Очистка БД перед каждым тестом"""
        db = TestingSessionLocal()
        try:
            db.query(Item).delete()
            db.commit()
        finally:
            db.close()
    
    def test_bulk_import_all_success(self):
        """Тест bulk импорта - все items валидны"""
        items_data = [
            {
                "sku": get_unique_sku(),
                "title": "Bulk Item 1",
                "status": "active"
            },
            {
                "sku": get_unique_sku(),
                "title": "Bulk Item 2",
                "status": "active",
                "brand": "Test Brand",
                "category": "Test Category"
            }
        ]
        
        request_data = {"items": items_data}
        
        response = client.post("/api/v1/items:bulk", json=request_data)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["total"] == 2
        assert data["successful"] == 2
        assert data["failed"] == 0
        assert len(data["results"]) == 2
        
        # Проверяем результаты
        for i, result in enumerate(data["results"]):
            assert result["index"] == i
            assert result["status"] == "success"
            assert result["status_code"] == 201
            assert "data" in result
            assert result["data"]["sku"] == items_data[i]["sku"]
            assert result["data"]["title"] == items_data[i]["title"]
    
    def test_bulk_import_mixed(self):
        """Тест bulk импорта - смешанные валидные/невалидные"""
        # Сначала создаём item с дублирующимся SKU
        existing_sku = get_unique_sku()
        existing_item = {
            "sku": existing_sku,
            "title": "Existing Item",
            "status": "active"
        }
        client.post("/api/v1/items", json=existing_item)
        
        items_data = [
            {
                "sku": get_unique_sku(),
                "title": "Valid Item",
                "status": "active"
            },
            {
                "sku": existing_sku,  # Дубликат
                "title": "Duplicate Item",
                "status": "active"
            },
            {
                "sku": get_unique_sku(),
                "title": "",  # Пустой title
                "status": "active"
            }
        ]
        
        request_data = {"items": items_data}
        
        response = client.post("/api/v1/items:bulk", json=request_data)
        
        assert response.status_code == 207  # Multi-Status
        data = response.json()
        
        assert data["total"] == 3
        assert data["successful"] == 1
        assert data["failed"] == 2
        assert len(data["results"]) == 3
        
        # Проверяем успешный результат
        success_result = data["results"][0]
        assert success_result["status"] == "success"
        assert success_result["status_code"] == 201
        
        # Проверяем дубликат
        duplicate_result = data["results"][1]
        assert duplicate_result["status"] == "error"
        assert duplicate_result["status_code"] == 409
        assert duplicate_result["error_code"] == "DUPLICATE_SKU"
        
        # Проверяем валидационную ошибку
        validation_result = data["results"][2]
        assert validation_result["status"] == "error"
        assert validation_result["status_code"] == 500  # Internal error from validation
    
    def test_bulk_import_all_errors(self):
        """Тест bulk импорта - все items невалидны"""
        items_data = [
            {
                "sku": "",  # Пустой SKU
                "title": "Item 1",
                "status": "active"
            },
            {
                "sku": "a" * 101,  # Слишком длинный SKU
                "title": "Item 2",
                "status": "active"
            }
        ]
        
        request_data = {"items": items_data}
        
        response = client.post("/api/v1/items:bulk", json=request_data)
        
        assert response.status_code == 207  # Multi-Status
        data = response.json()
        
        assert data["total"] == 2
        assert data["successful"] == 0
        assert data["failed"] == 2
        assert len(data["results"]) == 2
        
        # Все результаты должны быть ошибками
        for result in data["results"]:
            assert result["status"] == "error"
            assert result["status_code"] in [400, 500]
    
    def test_bulk_import_duplicate_skus(self):
        """Тест bulk импорта - дубликаты SKU в одном запросе"""
        duplicate_sku = get_unique_sku()
        items_data = [
            {
                "sku": duplicate_sku,
                "title": "Item 1",
                "status": "active"
            },
            {
                "sku": duplicate_sku,  # Дубликат в том же запросе
                "title": "Item 2",
                "status": "active"
            }
        ]
        
        request_data = {"items": items_data}
        
        response = client.post("/api/v1/items:bulk", json=request_data)
        
        assert response.status_code == 207  # Multi-Status
        data = response.json()
        
        assert data["total"] == 2
        assert data["successful"] == 1  # Первый создастся
        assert data["failed"] == 1      # Второй будет дубликатом
        
        # Первый должен быть успешным
        assert data["results"][0]["status"] == "success"
        
        # Второй должен быть ошибкой дубликата
        assert data["results"][1]["status"] == "error"
        assert data["results"][1]["error_code"] == "DUPLICATE_SKU"
    
    def test_bulk_import_at_limit(self):
        """Тест bulk импорта - ровно на лимите (1000 items)"""
        items_data = []
        for i in range(BULK_MAX_ITEMS):
            items_data.append({
                "sku": get_unique_sku(),
                "title": f"Bulk Item {i}",
                "status": "active"
            })
        
        request_data = {"items": items_data}
        
        response = client.post("/api/v1/items:bulk", json=request_data)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["total"] == BULK_MAX_ITEMS
        assert data["successful"] == BULK_MAX_ITEMS
        assert data["failed"] == 0
    
    def test_bulk_import_over_limit(self):
        """Тест bulk импорта - превышение лимита (> 1000 items)"""
        items_data = []
        for i in range(BULK_MAX_ITEMS + 1):  # На 1 больше лимита
            items_data.append({
                "sku": get_unique_sku(),
                "title": f"Bulk Item {i}",
                "status": "active"
            })
        
        request_data = {"items": items_data}
        
        response = client.post("/api/v1/items:bulk", json=request_data)
        
        assert response.status_code == 422
        data = response.json()
        
        # Pydantic validation error structure
        assert "detail" in data
        assert len(data["detail"]) > 0
        error_detail = data["detail"][0]
        assert "List should have at most 1000 items" in error_detail["msg"]
    
    def test_bulk_import_empty_array(self):
        """Тест bulk импорта - пустой массив"""
        request_data = {"items": []}
        
        response = client.post("/api/v1/items:bulk", json=request_data)
        
        assert response.status_code == 422
        data = response.json()
        
        # Pydantic validation error structure
        assert "detail" in data
        assert len(data["detail"]) > 0
        error_detail = data["detail"][0]
        assert "List should have at least 1 item" in error_detail["msg"]
    
    def test_bulk_import_validation_errors(self):
        """Тест bulk импорта - различные ошибки валидации"""
        items_data = [
            {
                "sku": "VALID-SKU",
                "title": "Valid Item",
                "status": "active"
            },
            {
                "sku": "",  # Пустой SKU
                "title": "Item with empty SKU",
                "status": "active"
            },
            {
                "sku": "VALID-SKU-2",
                "title": "",  # Пустой title
                "status": "active"
            },
            {
                "sku": "VALID-SKU-3",
                "title": "Item with invalid status",
                "status": "invalid_status"  # Невалидный статус
            }
        ]
        
        request_data = {"items": items_data}
        
        response = client.post("/api/v1/items:bulk", json=request_data)
        
        assert response.status_code == 207  # Multi-Status
        data = response.json()
        
        assert data["total"] == 4
        assert data["successful"] == 1  # Только первый валидный
        assert data["failed"] == 3      # Остальные с ошибками
        
        # Первый должен быть успешным
        assert data["results"][0]["status"] == "success"
        
        # Остальные должны быть ошибками
        for i in range(1, 4):
            assert data["results"][i]["status"] == "error"
    
    def test_bulk_import_partial_success(self):
        """Тест bulk импорта - частичная успешность"""
        # Создаём несколько валидных и невалидных items
        valid_skus = [get_unique_sku() for _ in range(3)]
        items_data = []
        
        # Валидные items
        for i, sku in enumerate(valid_skus):
            items_data.append({
                "sku": sku,
                "title": f"Valid Item {i}",
                "status": "active"
            })
        
        # Невалидные items
        items_data.extend([
            {
                "sku": "",  # Пустой SKU
                "title": "Invalid Item 1",
                "status": "active"
            },
            {
                "sku": "a" * 101,  # Слишком длинный SKU
                "title": "Invalid Item 2",
                "status": "active"
            }
        ])
        
        request_data = {"items": items_data}
        
        response = client.post("/api/v1/items:bulk", json=request_data)
        
        assert response.status_code == 207  # Multi-Status
        data = response.json()
        
        assert data["total"] == 5
        assert data["successful"] == 3  # Валидные items
        assert data["failed"] == 2      # Невалидные items
        
        # Проверяем, что валидные items создались в БД
        db = TestingSessionLocal()
        try:
            created_items = db.query(Item).filter(Item.sku.in_(valid_skus)).all()
            assert len(created_items) == 3
        finally:
            db.close()
    
    def test_bulk_limits_endpoint(self):
        """Тест endpoint для получения лимитов bulk API"""
        response = client.get("/api/v1/items:bulk/limits")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["max_items"] == BULK_MAX_ITEMS
        assert data["max_size_mb"] == 10
        assert data["max_size_bytes"] == 10 * 1024 * 1024
        assert "description" in data
