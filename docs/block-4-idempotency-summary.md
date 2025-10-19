# Блок 4: Идемпотентный POST (Idempotency-Key)

## Цель
POST /items не создаёт дубликатов при ретраях.

## Контракт запроса/ответа

### Заголовок Idempotency-Key
- **Формат**: 1-255 символов
- **Допустимые символы**: буквы (a-z, A-Z), цифры (0-9), дефис (-), подчёркивание (_)
- **Обязательность**: Опциональная
- **Примеры**:
  ```
  Idempotency-Key: client-request-123
  Idempotency-Key: user-456-session-789
  Idempotency-Key: 2024-01-15-10-30-00-abc123
  ```

### HTTP коды состояния
- **201 Created**: Успешное создание (первый запрос или повтор с тем же телом)
- **409 Conflict**: Конфликт идемпотентности (тот же ключ, другое тело)
- **400 Bad Request**: Невалидный формат ключа

### Примеры запросов и ответов

#### Успешное создание (первый запрос)
```http
POST /api/v1/items
Idempotency-Key: test-key-001
Content-Type: application/json

{
    "sku": "ITEM-001",
    "title": "Sample Item",
    "status": "active"
}
```

**Ответ:**
```json
{
    "id": 123,
    "sku": "ITEM-001",
    "title": "Sample Item",
    "status": "active",
    "brand": null,
    "category": null,
    "created_at": "2024-01-15T10:30:00Z"
}
```

#### Повторный запрос (тот же ключ + то же тело)
```http
POST /api/v1/items
Idempotency-Key: test-key-001
Content-Type: application/json

{
    "sku": "ITEM-001",
    "title": "Sample Item",
    "status": "active"
}
```

**Ответ (байтово идентичный):**
```json
{
    "id": 123,
    "sku": "ITEM-001",
    "title": "Sample Item",
    "status": "active",
    "brand": null,
    "category": null,
    "created_at": "2024-01-15T10:30:00Z"
}
```

#### Конфликт (тот же ключ + другое тело)
```http
POST /api/v1/items
Idempotency-Key: test-key-001
Content-Type: application/json

{
    "sku": "ITEM-002",
    "title": "Different Item",
    "status": "active"
}
```

**Ответ:**
```json
{
    "detail": "Idempotency key already used with different request body",
    "error_code": "IDEMPOTENCY_KEY_CONFLICT",
    "idempotency_key": "test-key-001"
}
```

## Схема таблицы idempotency_keys

### DDL
```sql
CREATE TABLE idempotency_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key VARCHAR(255) UNIQUE NOT NULL,
    request_hash VARCHAR(64) NOT NULL,  -- SHA-256 hash
    status VARCHAR(20) NOT NULL DEFAULT 'processing',
    response_status_code INTEGER,
    response_body TEXT,  -- Полный JSON ответ
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL
);

-- Индексы
CREATE UNIQUE INDEX idx_idempotency_key_unique ON idempotency_keys (key);
CREATE INDEX idx_idempotency_expires_at ON idempotency_keys (expires_at);
```

### Описание полей
- **key**: Уникальный ключ от клиента
- **request_hash**: SHA-256 хеш тела запроса для проверки идентичности
- **status**: Состояние ключа (`processing` → `completed`)
- **response_status_code**: HTTP код ответа для воспроизведения
- **response_body**: Полный JSON ответ для байтовой идентичности
- **expires_at**: TTL (1 час по умолчанию)

## Сценарии гонок и повторов

### 1. Race condition (параллельные POST с одним ключом)
- **Проблема**: Два запроса с одним ключом приходят одновременно
- **Решение**: Уникальный индекс на `key` + IntegrityError
- **Результат**: Один запрос успешен (201), остальные получают 409

### 2. Повтор с тем же телом
- **Условие**: Тот же ключ + тот же SHA-256 хеш
- **Результат**: Возврат байтово идентичного кэшированного ответа
- **Время**: Мгновенно (без обращения к бизнес-логике)

### 3. Повтор с другим телом
- **Условие**: Тот же ключ + другой SHA-256 хеш
- **Результат**: HTTP 409 Conflict
- **Причина**: Нарушение идемпотентности

### 4. Повтор через TTL
- **Условие**: `expires_at < now()`
- **Результат**: Ключ удаляется, создаётся новый
- **Время**: 1 час по умолчанию

### 5. Network timeout
- **Проблема**: Клиент потерял ответ после успешного POST
- **Решение**: Повтор с тем же `Idempotency-Key`
- **Результат**: Возврат кэшированного ответа

### 6. Очистка истёкших ключей
- **Частота**: Каждые 10 минут
- **Условие**: `DELETE FROM idempotency_keys WHERE expires_at < NOW()`
- **Индекс**: `idx_idempotency_expires_at` для производительности

## Метрики и мониторинг

### Ключевые метрики
- **idempotency.hit_rate**: `(hits) / (hits + misses) * 100%`
  - Целевое значение: > 80%
  - < 50% требует анализа
- **idempotency.conflicts**: Количество конфликтов (тот же ключ, другое тело)
- **latency**: Время ответа
  - Кэшированные запросы: < 50ms
  - Новые запросы: < 200ms
- **cleanup.count**: Количество очищенных ключей за цикл

### Примеры логов
```json
{
    "event": "idempotency_hit",
    "idempotency_key": "client-request-123",
    "status_code": 201,
    "response_size": 156,
    "cached_at": "2024-01-15T10:30:00Z"
}
```

```json
{
    "event": "idempotency_conflict",
    "idempotency_key": "client-request-123",
    "existing_hash": "abc123...",
    "new_hash": "def456...",
    "error_code": "IDEMPOTENCY_KEY_CONFLICT"
}
```

## Автотесты

### Базовые тесты
- **test_create_item_without_idempotency_key**: POST без заголовка работает как обычно
- **test_create_item_with_new_key**: Создание с новым ключом
- **test_repeat_request_same_key_same_body**: Повтор с тем же ключом и телом → байтово идентичный ответ
- **test_repeat_request_same_key_different_body**: Повтор с другим телом → 409 Conflict

### Race conditions
- **test_concurrent_requests_same_key**: 3 параллельных POST с одним ключом
  - Ожидаемый результат: 1 успешный (201), 2 конфликта (409)
  - Использует threading для симуляции параллельности

### TTL и временные интервалы
- **test_idempotency_after_1_minute**: Повтор через 1 минуту → кэшированный ответ
- **test_expired_key_can_be_reused**: Истёкший ключ можно использовать повторно
- **test_cleanup_expired_keys**: Очистка истёкших ключей

### Валидация
- **test_invalid_idempotency_key_format**: Невалидные символы → 400
- **test_empty_idempotency_key**: Пустой ключ → 400
- **test_too_long_idempotency_key**: > 255 символов → 400

### Проверка байтовой идентичности
```python
# В test_repeat_request_same_key_same_body
assert data2 == data1, "Responses should be byte-identical"
assert data2["id"] == data1["id"]
assert data2["sku"] == data1["sku"]
assert data2["title"] == data1["title"]
assert data2["status"] == data1["status"]
assert data2["created_at"] == data1["created_at"]
```

## DoD (Definition of Done)

✅ **Таблица idempotency_keys с TTL**: Реализована с индексами и автоматической очисткой  
✅ **Повтор → байтово тот же ответ**: Полный response body сохраняется и воспроизводится  
✅ **Гонки закрыты**: Уникальный индекс + IntegrityError предотвращает race conditions  
✅ **Тесты**: Параллельные POST, повтор через TTL, несовпадающее тело  
✅ **Метрики**: hit_rate, conflicts, latency, cleanup.count  
✅ **Документация**: Контракт API, схема БД, сценарии, автотесты  

## Файлы реализации

- **Модель**: `app/models/idempotency.py`
- **Middleware**: `app/middleware/idempotency.py`
- **Утилиты**: `app/utils/idempotency.py`
- **Тесты**: `tests/test_idempotency.py`
- **Очистка**: `app/tasks/cleanup.py`
- **Спецификация**: `docs/idempotency-spec.md`
