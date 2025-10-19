"""
Integration тесты для курсорной пагинации Items.
"""
import pytest
import uuid
import time
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from app.main import app
from app.database.connection import get_db, engine
from app.models.item import Base, Item
from app.utils.cursor import encode_cursor, decode_cursor

# Создаем тестовую базу данных в памяти
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_pagination.db"
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

def create_test_items(count: int, base_time: datetime = None, **kwargs):
    """Создает тестовые items в базе данных"""
    if base_time is None:
        base_time = datetime.now(timezone.utc)
    
    db = TestingSessionLocal()
    try:
        items = []
        for i in range(count):
            created_at = base_time + timedelta(seconds=i)
            item = Item(
                sku=get_unique_sku(),
                title=f"Test Item {i}",
                status=kwargs.get('status', 'active'),
                brand=kwargs.get('brand', f'Brand {i % 3}'),
                category=kwargs.get('category', f'Category {i % 2}'),
                created_at=created_at
            )
            db.add(item)
            items.append(item)
        
        db.commit()
        for item in items:
            db.refresh(item)
        return items
    finally:
        db.close()


class TestCursorPaginationBasic:
    """Базовые тесты курсорной пагинации"""
    
    def test_first_page_without_cursor(self):
        """Тест первой страницы без курсора"""
        # Создаем 5 тестовых items
        items = create_test_items(5)
        
        response = client.get("/api/v1/items?limit=3")
        assert response.status_code == 200
        
        data = response.json()
        assert len(data["items"]) == 3
        assert data["has_more"] is True
        assert data["next_cursor"] is not None
        
        # Проверяем порядок (должен быть по created_at DESC, id DESC)
        item_ids = [item["id"] for item in data["items"]]
        assert item_ids == sorted(item_ids, reverse=True)
    
    def test_second_page_with_cursor(self):
        """Тест второй страницы с курсором"""
        # Создаем 5 тестовых items
        items = create_test_items(5)
        
        # Получаем первую страницу
        response1 = client.get("/api/v1/items?limit=3")
        assert response1.status_code == 200
        data1 = response1.json()
        
        # Получаем вторую страницу
        response2 = client.get(f"/api/v1/items?limit=3&cursor={data1['next_cursor']}")
        assert response2.status_code == 200
        data2 = response2.json()
        
        # Проверяем, что нет пересечений
        page1_ids = {item["id"] for item in data1["items"]}
        page2_ids = {item["id"] for item in data2["items"]}
        assert len(page1_ids & page2_ids) == 0
        
        # Проверяем порядок
        all_ids = [item["id"] for item in data1["items"]] + [item["id"] for item in data2["items"]]
        assert all_ids == sorted(all_ids, reverse=True)
    
    def test_last_page_has_more_false(self):
        """Тест последней страницы (has_more = false)"""
        # Создаем ровно 3 items
        items = create_test_items(3)
        
        response = client.get("/api/v1/items?limit=3")
        assert response.status_code == 200
        
        data = response.json()
        assert len(data["items"]) == 3
        assert data["has_more"] is False
        assert data["next_cursor"] is None
    
    def test_empty_result_with_cursor(self):
        """Тест пустого результата с курсором за пределами данных"""
        # Создаем 3 items
        items = create_test_items(3)
        
        # Создаем курсор для несуществующего элемента
        future_time = datetime.now(timezone.utc) + timedelta(days=1)
        fake_cursor = encode_cursor(future_time, 99999)
        
        response = client.get(f"/api/v1/items?limit=10&cursor={fake_cursor}")
        assert response.status_code == 200
        
        data = response.json()
        assert len(data["items"]) == 0
        assert data["has_more"] is False
        assert data["next_cursor"] is None


class TestCursorPaginationStability:
    """Тесты стабильности курсорной пагинации"""
    
    def test_stable_order_across_pages(self):
        """Тест стабильного порядка между страницами"""
        # Создаем 300 items для тестирования стабильности
        items = create_test_items(300)
        
        all_items = []
        cursor = None
        page_count = 0
        
        while page_count < 5:  # Ограничиваем количество страниц для теста
            params = {"limit": 100}
            if cursor:
                params["cursor"] = cursor
            
            response = client.get("/api/v1/items", params=params)
            assert response.status_code == 200
            
            data = response.json()
            all_items.extend(data["items"])
            
            if not data["has_more"]:
                break
                
            cursor = data["next_cursor"]
            page_count += 1
        
        # Проверяем отсутствие дубликатов
        item_ids = [item["id"] for item in all_items]
        assert len(item_ids) == len(set(item_ids))
        
        # Проверяем стабильный порядок
        assert item_ids == sorted(item_ids, reverse=True)
    
    def test_no_drift_on_insertions(self):
        """Тест отсутствия дрейфа при вставках во время пагинации"""
        # Создаем 100 items
        items = create_test_items(100)
        
        # Получаем первую страницу
        response1 = client.get("/api/v1/items?limit=50")
        assert response1.status_code == 200
        data1 = response1.json()
        cursor = data1["next_cursor"]
        
        # Добавляем 50 новых items
        new_items = create_test_items(50)
        
        # Получаем вторую страницу с тем же курсором
        response2 = client.get(f"/api/v1/items?limit=50&cursor={cursor}")
        assert response2.status_code == 200
        data2 = response2.json()
        
        # Проверяем, что новые items не попали на вторую страницу
        page1_ids = {item["id"] for item in data1["items"]}
        page2_ids = {item["id"] for item in data2["items"]}
        new_item_ids = {item.id for item in new_items}
        
        assert len(page2_ids & new_item_ids) == 0
        assert len(page1_ids & page2_ids) == 0


class TestCursorPaginationFiltering:
    """Тесты фильтрации с курсорной пагинацией"""
    
    def test_filter_by_status(self):
        """Тест фильтрации по статусу"""
        # Создаем items с разными статусами
        active_items = create_test_items(5, status='active')
        inactive_items = create_test_items(3, status='inactive')
        
        response = client.get("/api/v1/items?status=active&limit=10")
        assert response.status_code == 200
        
        data = response.json()
        assert len(data["items"]) == 5
        assert all(item["status"] == "active" for item in data["items"])
    
    def test_filter_by_brand(self):
        """Тест фильтрации по бренду"""
        # Создаем items с разными брендами
        brand_a_items = create_test_items(3, brand='Brand A')
        brand_b_items = create_test_items(2, brand='Brand B')
        
        response = client.get("/api/v1/items?brand=Brand A&limit=10")
        assert response.status_code == 200
        
        data = response.json()
        assert len(data["items"]) == 3
        assert all(item["brand"] == "Brand A" for item in data["items"])
    
    def test_filter_by_category(self):
        """Тест фильтрации по категории"""
        # Создаем items с разными категориями
        electronics_items = create_test_items(4, category='Electronics')
        clothing_items = create_test_items(2, category='Clothing')
        
        response = client.get("/api/v1/items?category=Electronics&limit=10")
        assert response.status_code == 200
        
        data = response.json()
        assert len(data["items"]) == 4
        assert all(item["category"] == "Electronics" for item in data["items"])
    
    def test_multiple_filters(self):
        """Тест множественных фильтров"""
        # Создаем items с разными комбинациями
        target_items = create_test_items(3, status='active', brand='Brand A', category='Electronics')
        other_items = create_test_items(5, status='inactive', brand='Brand B', category='Clothing')
        
        response = client.get("/api/v1/items?status=active&brand=Brand A&category=Electronics&limit=10")
        assert response.status_code == 200
        
        data = response.json()
        assert len(data["items"]) == 3
        for item in data["items"]:
            assert item["status"] == "active"
            assert item["brand"] == "Brand A"
            assert item["category"] == "Electronics"


class TestCursorPaginationErrors:
    """Тесты обработки ошибок курсорной пагинации"""
    
    def test_invalid_cursor_format(self):
        """Тест невалидного формата курсора"""
        response = client.get("/api/v1/items?cursor=invalid-cursor")
        assert response.status_code == 400
        assert "Invalid cursor format" in response.json()["detail"]
    
    def test_invalid_cursor_base64(self):
        """Тест невалидного base64 в курсоре"""
        response = client.get("/api/v1/items?cursor=invalid-base64!")
        assert response.status_code == 400
        assert "Invalid cursor format" in response.json()["detail"]
    
    def test_invalid_cursor_json(self):
        """Тест невалидного JSON в курсоре"""
        import base64
        invalid_json = base64.b64encode("invalid json".encode('utf-8')).decode('utf-8')
        
        response = client.get(f"/api/v1/items?cursor={invalid_json}")
        assert response.status_code == 400
        assert "Invalid cursor format" in response.json()["detail"]
    
    def test_limit_too_large(self):
        """Тест превышения максимального лимита"""
        response = client.get("/api/v1/items?limit=2000")
        assert response.status_code == 422  # Validation error
    
    def test_limit_zero(self):
        """Тест нулевого лимита"""
        response = client.get("/api/v1/items?limit=0")
        assert response.status_code == 422  # Validation error
    
    def test_limit_negative(self):
        """Тест отрицательного лимита"""
        response = client.get("/api/v1/items?limit=-1")
        assert response.status_code == 422  # Validation error


class TestCursorPaginationPerformance:
    """Тесты производительности курсорной пагинации"""
    
    def test_deep_pagination_performance(self):
        """Тест производительности глубокой пагинации"""
        # Создаем 1000+ items для тестирования производительности
        items = create_test_items(1000)
        
        cursor = None
        page_count = 0
        start_time = time.time()
        
        # Проходим 10+ страниц
        while page_count < 12:
            params = {"limit": 100}
            if cursor:
                params["cursor"] = cursor
            
            response = client.get("/api/v1/items", params=params)
            assert response.status_code == 200
            
            data = response.json()
            
            if not data["has_more"]:
                break
                
            cursor = data["next_cursor"]
            page_count += 1
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # Проверяем, что время ответа приемлемое (< 1 секунды для 10+ страниц)
        assert total_time < 1.0
        assert page_count >= 10
    
    def test_single_page_performance(self):
        """Тест производительности одной страницы"""
        # Создаем 1000 items
        items = create_test_items(1000)
        
        start_time = time.time()
        response = client.get("/api/v1/items?limit=100")
        end_time = time.time()
        
        assert response.status_code == 200
        assert (end_time - start_time) < 0.1  # Менее 100ms для одной страницы
        
        data = response.json()
        assert len(data["items"]) == 100
        assert data["has_more"] is True


class TestCursorPaginationEdgeCases:
    """Тесты граничных случаев курсорной пагинации"""
    
    def test_single_item(self):
        """Тест пагинации с одним элементом"""
        items = create_test_items(1)
        
        response = client.get("/api/v1/items?limit=10")
        assert response.status_code == 200
        
        data = response.json()
        assert len(data["items"]) == 1
        assert data["has_more"] is False
        assert data["next_cursor"] is None
    
    def test_exact_limit_items(self):
        """Тест пагинации с точным количеством элементов по лимиту"""
        items = create_test_items(100)
        
        response = client.get("/api/v1/items?limit=100")
        assert response.status_code == 200
        
        data = response.json()
        assert len(data["items"]) == 100
        assert data["has_more"] is False
        assert data["next_cursor"] is None
    
    def test_limit_plus_one_items(self):
        """Тест пагинации с лимит+1 элементами"""
        items = create_test_items(101)
        
        response = client.get("/api/v1/items?limit=100")
        assert response.status_code == 200
        
        data = response.json()
        assert len(data["items"]) == 100
        assert data["has_more"] is True
        assert data["next_cursor"] is not None
    
    def test_cursor_with_same_created_at(self):
        """Тест курсора с одинаковым created_at (должен использовать id для сортировки)"""
        base_time = datetime.now(timezone.utc)
        
        # Создаем items с одинаковым created_at
        db = TestingSessionLocal()
        try:
            items = []
            for i in range(5):
                item = Item(
                    sku=get_unique_sku(),
                    title=f"Same Time Item {i}",
                    created_at=base_time
                )
                db.add(item)
                items.append(item)
            
            db.commit()
            for item in items:
                db.refresh(item)
        finally:
            db.close()
        
        response = client.get("/api/v1/items?limit=3")
        assert response.status_code == 200
        
        data = response.json()
        assert len(data["items"]) == 3
        
        # Проверяем, что сортировка по id работает
        item_ids = [item["id"] for item in data["items"]]
        assert item_ids == sorted(item_ids, reverse=True)
