"""
Утилиты для работы с курсорной пагинацией.

Реализует keyset pagination на паре (created_at, id) с сериализацией в base64.
"""
import base64
import binascii
import json
from datetime import datetime
from typing import Tuple, Optional
from fastapi import HTTPException, status
import structlog

logger = structlog.get_logger()


class CursorDecodeError(Exception):
    """Ошибка декодирования курсора"""
    pass


def encode_cursor(created_at: datetime, id: int) -> str:
    """
    Кодирует курсор в base64 строку.
    
    Args:
        created_at: Время создания записи
        id: ID записи
        
    Returns:
        Base64 закодированная строка курсора
    """
    cursor_data = {
        "created_at": created_at.isoformat(),
        "id": id
    }
    
    json_str = json.dumps(cursor_data, separators=(',', ':'))
    encoded = base64.b64encode(json_str.encode('utf-8')).decode('utf-8')
    
    logger.debug("Cursor encoded", cursor_data=cursor_data, encoded=encoded)
    return encoded


def decode_cursor(cursor: str) -> Tuple[datetime, int]:
    """
    Декодирует курсор из base64 строки.
    
    Args:
        cursor: Base64 закодированная строка курсора
        
    Returns:
        Кортеж (created_at, id)
        
    Raises:
        CursorDecodeError: При ошибке декодирования
    """
    if not cursor:
        raise CursorDecodeError("Cursor cannot be empty")
    
    try:
        # Декодируем base64
        json_str = base64.b64decode(cursor.encode('utf-8')).decode('utf-8')
        
        # Парсим JSON
        cursor_data = json.loads(json_str)
        
        # Валидируем структуру
        if not isinstance(cursor_data, dict):
            raise CursorDecodeError("Cursor must be a JSON object")
        
        if "created_at" not in cursor_data or "id" not in cursor_data:
            raise CursorDecodeError("Cursor must contain 'created_at' and 'id' fields")
        
        # Парсим дату
        try:
            created_at = datetime.fromisoformat(cursor_data["created_at"].replace('Z', '+00:00'))
        except (ValueError, AttributeError) as e:
            raise CursorDecodeError(f"Invalid created_at format: {e}")
        
        # Валидируем ID
        try:
            id_value = int(cursor_data["id"])
            if id_value <= 0:
                raise CursorDecodeError("ID must be positive integer")
        except (ValueError, TypeError) as e:
            raise CursorDecodeError(f"Invalid ID format: {e}")
        
        logger.debug("Cursor decoded", cursor_data=cursor_data, created_at=created_at, id=id_value)
        return created_at, id_value
        
    except binascii.Error as e:
        raise CursorDecodeError(f"Invalid base64 encoding: {e}")
    except json.JSONDecodeError as e:
        raise CursorDecodeError(f"Invalid JSON format: {e}")
    except Exception as e:
        raise CursorDecodeError(f"Unexpected error decoding cursor: {e}")


def validate_cursor(cursor: Optional[str]) -> Optional[Tuple[datetime, int]]:
    """
    Валидирует курсор и возвращает декодированные данные или None.
    
    Args:
        cursor: Курсор для валидации (может быть None)
        
    Returns:
        Декодированные данные курсора или None если курсор не передан
        
    Raises:
        HTTPException: При ошибке валидации курсора
    """
    if cursor is None:
        return None
    
    try:
        return decode_cursor(cursor)
    except CursorDecodeError as e:
        logger.warning("Invalid cursor provided", cursor=cursor, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid cursor format: {e}"
        )
