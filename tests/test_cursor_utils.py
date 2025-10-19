"""
Unit тесты для утилит курсорной пагинации.
"""
import pytest
import base64
import json
from datetime import datetime, timezone
from app.utils.cursor import encode_cursor, decode_cursor, validate_cursor, CursorDecodeError
from fastapi import HTTPException


class TestEncodeCursor:
    """Тесты кодирования курсора"""
    
    def test_encode_cursor_basic(self):
        """Тест базового кодирования курсора"""
        created_at = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        item_id = 123
        
        cursor = encode_cursor(created_at, item_id)
        
        # Декодируем для проверки
        decoded = base64.b64decode(cursor).decode('utf-8')
        data = json.loads(decoded)
        
        assert data["created_at"] == "2024-01-15T10:30:00+00:00"
        assert data["id"] == 123
    
    def test_encode_cursor_with_microseconds(self):
        """Тест кодирования курсора с микросекундами"""
        created_at = datetime(2024, 1, 15, 10, 30, 0, 123456, tzinfo=timezone.utc)
        item_id = 456
        
        cursor = encode_cursor(created_at, item_id)
        
        # Декодируем для проверки
        decoded = base64.b64decode(cursor).decode('utf-8')
        data = json.loads(decoded)
        
        assert data["created_at"] == "2024-01-15T10:30:00.123456+00:00"
        assert data["id"] == 456


class TestDecodeCursor:
    """Тесты декодирования курсора"""
    
    def test_decode_cursor_basic(self):
        """Тест базового декодирования курсора"""
        cursor_data = {
            "created_at": "2024-01-15T10:30:00+00:00",
            "id": 123
        }
        cursor = base64.b64encode(json.dumps(cursor_data).encode('utf-8')).decode('utf-8')
        
        created_at, item_id = decode_cursor(cursor)
        
        assert created_at == datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        assert item_id == 123
    
    def test_decode_cursor_with_z_suffix(self):
        """Тест декодирования курсора с Z суффиксом"""
        cursor_data = {
            "created_at": "2024-01-15T10:30:00Z",
            "id": 123
        }
        cursor = base64.b64encode(json.dumps(cursor_data).encode('utf-8')).decode('utf-8')
        
        created_at, item_id = decode_cursor(cursor)
        
        assert created_at == datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        assert item_id == 123
    
    def test_decode_cursor_empty_string(self):
        """Тест декодирования пустой строки"""
        with pytest.raises(CursorDecodeError, match="Cursor cannot be empty"):
            decode_cursor("")
    
    def test_decode_cursor_none(self):
        """Тест декодирования None"""
        with pytest.raises(CursorDecodeError, match="Cursor cannot be empty"):
            decode_cursor(None)
    
    def test_decode_cursor_invalid_base64(self):
        """Тест декодирования невалидного base64"""
        with pytest.raises(CursorDecodeError, match="Invalid base64 encoding"):
            decode_cursor("invalid-base64!")
    
    def test_decode_cursor_invalid_json(self):
        """Тест декодирования невалидного JSON"""
        invalid_json = base64.b64encode("invalid json".encode('utf-8')).decode('utf-8')
        
        with pytest.raises(CursorDecodeError, match="Invalid JSON format"):
            decode_cursor(invalid_json)
    
    def test_decode_cursor_missing_fields(self):
        """Тест декодирования курсора с отсутствующими полями"""
        cursor_data = {"created_at": "2024-01-15T10:30:00Z"}
        cursor = base64.b64encode(json.dumps(cursor_data).encode('utf-8')).decode('utf-8')
        
        with pytest.raises(CursorDecodeError, match="Cursor must contain 'created_at' and 'id' fields"):
            decode_cursor(cursor)
    
    def test_decode_cursor_invalid_created_at(self):
        """Тест декодирования курсора с невалидной датой"""
        cursor_data = {
            "created_at": "invalid-date",
            "id": 123
        }
        cursor = base64.b64encode(json.dumps(cursor_data).encode('utf-8')).decode('utf-8')
        
        with pytest.raises(CursorDecodeError, match="Invalid created_at format"):
            decode_cursor(cursor)
    
    def test_decode_cursor_invalid_id(self):
        """Тест декодирования курсора с невалидным ID"""
        cursor_data = {
            "created_at": "2024-01-15T10:30:00Z",
            "id": "not-a-number"
        }
        cursor = base64.b64encode(json.dumps(cursor_data).encode('utf-8')).decode('utf-8')
        
        with pytest.raises(CursorDecodeError, match="Invalid ID format"):
            decode_cursor(cursor)
    
    def test_decode_cursor_negative_id(self):
        """Тест декодирования курсора с отрицательным ID"""
        cursor_data = {
            "created_at": "2024-01-15T10:30:00Z",
            "id": -1
        }
        cursor = base64.b64encode(json.dumps(cursor_data).encode('utf-8')).decode('utf-8')
        
        with pytest.raises(CursorDecodeError, match="ID must be positive integer"):
            decode_cursor(cursor)
    
    def test_decode_cursor_zero_id(self):
        """Тест декодирования курсора с нулевым ID"""
        cursor_data = {
            "created_at": "2024-01-15T10:30:00Z",
            "id": 0
        }
        cursor = base64.b64encode(json.dumps(cursor_data).encode('utf-8')).decode('utf-8')
        
        with pytest.raises(CursorDecodeError, match="ID must be positive integer"):
            decode_cursor(cursor)
    
    def test_decode_cursor_not_dict(self):
        """Тест декодирования курсора с не-объектом JSON"""
        cursor = base64.b64encode(json.dumps("not-a-dict").encode('utf-8')).decode('utf-8')
        
        with pytest.raises(CursorDecodeError, match="Cursor must be a JSON object"):
            decode_cursor(cursor)


class TestValidateCursor:
    """Тесты валидации курсора"""
    
    def test_validate_cursor_none(self):
        """Тест валидации None курсора"""
        result = validate_cursor(None)
        assert result is None
    
    def test_validate_cursor_valid(self):
        """Тест валидации валидного курсора"""
        cursor_data = {
            "created_at": "2024-01-15T10:30:00Z",
            "id": 123
        }
        cursor = base64.b64encode(json.dumps(cursor_data).encode('utf-8')).decode('utf-8')
        
        result = validate_cursor(cursor)
        
        assert result is not None
        created_at, item_id = result
        assert created_at == datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        assert item_id == 123
    
    def test_validate_cursor_invalid(self):
        """Тест валидации невалидного курсора"""
        with pytest.raises(HTTPException) as exc_info:
            validate_cursor("invalid-cursor")
        
        assert exc_info.value.status_code == 400
        assert "Invalid cursor format" in exc_info.value.detail


class TestCursorRoundTrip:
    """Тесты полного цикла кодирование-декодирование"""
    
    def test_round_trip_basic(self):
        """Тест полного цикла с базовыми данными"""
        original_created_at = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        original_id = 123
        
        cursor = encode_cursor(original_created_at, original_id)
        decoded_created_at, decoded_id = decode_cursor(cursor)
        
        assert decoded_created_at == original_created_at
        assert decoded_id == original_id
    
    def test_round_trip_with_microseconds(self):
        """Тест полного цикла с микросекундами"""
        original_created_at = datetime(2024, 1, 15, 10, 30, 0, 123456, tzinfo=timezone.utc)
        original_id = 456
        
        cursor = encode_cursor(original_created_at, original_id)
        decoded_created_at, decoded_id = decode_cursor(cursor)
        
        assert decoded_created_at == original_created_at
        assert decoded_id == original_id
    
    def test_round_trip_large_id(self):
        """Тест полного цикла с большим ID"""
        original_created_at = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        original_id = 999999999
        
        cursor = encode_cursor(original_created_at, original_id)
        decoded_created_at, decoded_id = decode_cursor(cursor)
        
        assert decoded_created_at == original_created_at
        assert decoded_id == original_id
