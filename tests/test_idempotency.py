import pytest
import json
import time
import asyncio
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.main import app
from app.database.connection import SessionLocal
from app.models.idempotency import IdempotencyKey
from app.models.item import Item

client = TestClient(app)


class TestIdempotencyBasic:
    """Базовые тесты идемпотентности"""
    
    def setup_method(self):
        """Очистка БД перед каждым тестом"""
        db = SessionLocal()
        try:
            # Очищаем таблицы
            db.query(IdempotencyKey).delete()
            db.query(Item).delete()
            db.commit()
        finally:
            db.close()
    
    def test_create_item_without_idempotency_key(self):
        """Тест создания item без ключа идемпотентности"""
        item_data = {
            "sku": "TEST-001",
            "title": "Test Item",
            "status": "active",
            "brand": "Test Brand",
            "category": "Test Category"
        }
        
        response = client.post("/api/v1/items", json=item_data)
        
        assert response.status_code == 201
        data = response.json()
        assert data["sku"] == "TEST-001"
        assert data["title"] == "Test Item"
        
        # Проверяем, что item создался в БД
        db = SessionLocal()
        try:
            item = db.query(Item).filter(Item.sku == "TEST-001").first()
            assert item is not None
            assert item.title == "Test Item"
        finally:
            db.close()
    
    def test_create_item_with_new_key(self):
        """Тест создания item с новым ключом идемпотентности"""
        item_data = {
            "sku": "TEST-002",
            "title": "Test Item 2",
            "status": "active"
        }
        
        headers = {"Idempotency-Key": "test-key-001"}
        response = client.post("/api/v1/items", json=item_data, headers=headers)
        
        assert response.status_code == 201
        data = response.json()
        assert data["sku"] == "TEST-002"
        
        # Проверяем, что ключ идемпотентности создался
        db = SessionLocal()
        try:
            key = db.query(IdempotencyKey).filter(IdempotencyKey.key == "test-key-001").first()
            assert key is not None
            assert key.status == "completed"
            assert key.response_status_code == 201
        finally:
            db.close()
    
    def test_repeat_request_same_key_same_body(self):
        """Тест повторного запроса с тем же ключом и телом"""
        item_data = {
            "sku": "TEST-003",
            "title": "Test Item 3",
            "status": "active"
        }
        
        headers = {"Idempotency-Key": "test-key-002"}
        
        # Первый запрос
        response1 = client.post("/api/v1/items", json=item_data, headers=headers)
        assert response1.status_code == 201
        data1 = response1.json()
        
        # Второй запрос с тем же ключом и телом
        response2 = client.post("/api/v1/items", json=item_data, headers=headers)
        assert response2.status_code == 201
        data2 = response2.json()
        
        # Проверяем байтовую идентичность ответов
        assert data2 == data1, "Responses should be byte-identical"
        assert data2["id"] == data1["id"]
        assert data2["sku"] == data1["sku"]
        assert data2["title"] == data1["title"]
        assert data2["status"] == data1["status"]
        assert data2["created_at"] == data1["created_at"]
        
        # В БД должен быть только один item
        db = SessionLocal()
        try:
            items = db.query(Item).filter(Item.sku == "TEST-003").all()
            assert len(items) == 1
        finally:
            db.close()
    
    def test_repeat_request_same_key_different_body(self):
        """Тест повторного запроса с тем же ключом, но другим телом"""
        item_data1 = {
            "sku": "TEST-004",
            "title": "Test Item 4",
            "status": "active"
        }
        
        item_data2 = {
            "sku": "TEST-005",
            "title": "Test Item 5",
            "status": "active"
        }
        
        headers = {"Idempotency-Key": "test-key-003"}
        
        # Первый запрос
        response1 = client.post("/api/v1/items", json=item_data1, headers=headers)
        assert response1.status_code == 201
        
        # Второй запрос с другим телом
        response2 = client.post("/api/v1/items", json=item_data2, headers=headers)
        assert response2.status_code == 409
        
        error_data = response2.json()
        assert error_data["error_code"] == "IDEMPOTENCY_KEY_CONFLICT"
        assert error_data["idempotency_key"] == "test-key-003"
    
    def test_invalid_idempotency_key_format(self):
        """Тест невалидного формата ключа идемпотентности"""
        item_data = {
            "sku": "TEST-006",
            "title": "Test Item 6",
            "status": "active"
        }
        
        # Ключ с недопустимыми символами
        headers = {"Idempotency-Key": "test@key#001"}
        response = client.post("/api/v1/items", json=item_data, headers=headers)
        
        assert response.status_code == 400
        error_data = response.json()
        assert error_data["error_code"] == "INVALID_IDEMPOTENCY_KEY"
    
    def test_empty_idempotency_key(self):
        """Тест пустого ключа идемпотентности"""
        item_data = {
            "sku": "TEST-007",
            "title": "Test Item 7",
            "status": "active"
        }
        
        headers = {"Idempotency-Key": ""}
        response = client.post("/api/v1/items", json=item_data, headers=headers)
        
        # Пустой ключ должен возвращать ошибку валидации
        assert response.status_code == 400
        error_data = response.json()
        assert error_data["error_code"] == "INVALID_IDEMPOTENCY_KEY"
    
    def test_too_long_idempotency_key(self):
        """Тест слишком длинного ключа идемпотентности"""
        item_data = {
            "sku": "TEST-008",
            "title": "Test Item 8",
            "status": "active"
        }
        
        # Ключ длиннее 255 символов
        long_key = "a" * 256
        headers = {"Idempotency-Key": long_key}
        response = client.post("/api/v1/items", json=item_data, headers=headers)
        
        assert response.status_code == 400
        error_data = response.json()
        assert error_data["error_code"] == "INVALID_IDEMPOTENCY_KEY"


class TestIdempotencyRaceConditions:
    """Тесты race conditions"""
    
    def setup_method(self):
        """Очистка БД перед каждым тестом"""
        db = SessionLocal()
        try:
            db.query(IdempotencyKey).delete()
            db.query(Item).delete()
            db.commit()
        finally:
            db.close()
    
    def test_concurrent_requests_same_key(self):
        """Тест параллельных запросов с одним ключом"""
        item_data = {
            "sku": "TEST-009",
            "title": "Test Item 9",
            "status": "active"
        }
        
        headers = {"Idempotency-Key": "concurrent-test-key"}
        
        # Симулируем параллельные запросы
        responses = []
        
        def make_request():
            response = client.post("/api/v1/items", json=item_data, headers=headers)
            responses.append(response)
        
        # Создаём несколько потоков
        threads = []
        for _ in range(3):
            import threading
            thread = threading.Thread(target=make_request)
            threads.append(thread)
            thread.start()
        
        # Ждём завершения всех потоков
        for thread in threads:
            thread.join()
        
        # Проверяем результаты
        assert len(responses) == 3
        
        # Один запрос должен быть успешным (201), остальные - конфликт (409)
        success_count = sum(1 for r in responses if r.status_code == 201)
        conflict_count = sum(1 for r in responses if r.status_code == 409)
        
        assert success_count == 1
        assert conflict_count == 2
        
        # В БД должен быть только один item
        db = SessionLocal()
        try:
            items = db.query(Item).filter(Item.sku == "TEST-009").all()
            assert len(items) == 1
        finally:
            db.close()


class TestIdempotencyTTL:
    """Тесты TTL и временных интервалов"""
    
    def setup_method(self):
        """Очистка БД перед каждым тестом"""
        db = SessionLocal()
        try:
            db.query(IdempotencyKey).delete()
            db.query(Item).delete()
            db.commit()
        finally:
            db.close()
    
    def test_idempotency_after_1_minute(self):
        """Тест идемпотентности через 1 минуту (должна работать)"""
        item_data = {
            "sku": "TEST-010",
            "title": "Test Item 10",
            "status": "active"
        }
        
        headers = {"Idempotency-Key": "ttl-test-key-001"}
        
        # Первый запрос
        response1 = client.post("/api/v1/items", json=item_data, headers=headers)
        assert response1.status_code == 201
        data1 = response1.json()
        
        # Симулируем прошествие 1 минуты, изменив expires_at в БД
        db = SessionLocal()
        try:
            key = db.query(IdempotencyKey).filter(IdempotencyKey.key == "ttl-test-key-001").first()
            # Устанавливаем expires_at на 1 минуту в будущем
            key.expires_at = datetime.utcnow() + timedelta(minutes=1)
            db.commit()
        finally:
            db.close()
        
        # Второй запрос должен вернуть кэшированный ответ
        response2 = client.post("/api/v1/items", json=item_data, headers=headers)
        assert response2.status_code == 201
        
        data2 = response2.json()
        # Проверяем байтовую идентичность ответов
        assert data2 == data1, "TTL cached responses should be byte-identical"
        assert data2["id"] == data1["id"]
        assert data2["sku"] == data1["sku"]
        assert data2["title"] == data1["title"]
    
    def test_expired_key_can_be_reused(self):
        """Тест что истёкший ключ можно использовать повторно"""
        item_data1 = {
            "sku": "TEST-011",
            "title": "Test Item 11",
            "status": "active"
        }
        
        item_data2 = {
            "sku": "TEST-012",
            "title": "Test Item 12",
            "status": "active"
        }
        
        headers = {"Idempotency-Key": "expired-test-key"}
        
        # Первый запрос
        response1 = client.post("/api/v1/items", json=item_data1, headers=headers)
        assert response1.status_code == 201
        
        # Симулируем истечение ключа
        db = SessionLocal()
        try:
            key = db.query(IdempotencyKey).filter(IdempotencyKey.key == "expired-test-key").first()
            # Устанавливаем expires_at в прошлое
            key.expires_at = datetime.utcnow() - timedelta(minutes=1)
            db.commit()
        finally:
            db.close()
        
        # Второй запрос с другим телом должен пройти
        response2 = client.post("/api/v1/items", json=item_data2, headers=headers)
        assert response2.status_code == 201
        
        # В БД должно быть два item
        db = SessionLocal()
        try:
            items = db.query(Item).filter(Item.sku.in_(["TEST-011", "TEST-012"])).all()
            assert len(items) == 2
        finally:
            db.close()
    
    def test_cleanup_expired_keys(self):
        """Тест очистки истёкших ключей"""
        from app.tasks.cleanup import cleanup_expired_idempotency_keys
        
        # Создаём истёкший ключ
        db = SessionLocal()
        try:
            expired_key = IdempotencyKey(
                key="expired-cleanup-test",
                request_hash="test-hash",
                status="completed",
                expires_at=datetime.utcnow() - timedelta(hours=1)
            )
            db.add(expired_key)
            db.commit()
            
            # Проверяем, что ключ создался
            key = db.query(IdempotencyKey).filter(IdempotencyKey.key == "expired-cleanup-test").first()
            assert key is not None
            
        finally:
            db.close()
        
        # Запускаем очистку
        import asyncio
        cleaned_count = asyncio.run(cleanup_expired_idempotency_keys())
        
        assert cleaned_count == 1
        
        # Проверяем, что ключ удалился
        db = SessionLocal()
        try:
            key = db.query(IdempotencyKey).filter(IdempotencyKey.key == "expired-cleanup-test").first()
            assert key is None
        finally:
            db.close()
