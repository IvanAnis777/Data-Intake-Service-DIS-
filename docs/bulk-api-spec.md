# Bulk API Specification

## Обзор

Bulk API позволяет массово создавать items с поддержкой частичной успешности. Каждый item обрабатывается в отдельной транзакции, поэтому ошибка одного item не влияет на обработку других.

## Endpoint

### `POST /api/v1/items:bulk`

Массовый импорт items с детальным отчётом о результатах.

## Лимиты и ограничения

- **Максимум items**: 1000 за запрос
- **Максимальный размер**: 10MB
- **Валидация**: Построчная с детальными ошибками
- **Транзакции**: Каждый item в отдельной транзакции

## Контракт API

### Request

```json
{
  "items": [
    {
      "sku": "ITEM-001",
      "title": "Sample Item 1",
      "status": "active",
      "brand": "Brand A",
      "category": "Electronics"
    },
    {
      "sku": "ITEM-002",
      "title": "Sample Item 2",
      "status": "active"
    }
  ]
}
```

**Поля items:**
- `sku` (string, required): Артикул товара (1-100 символов)
- `title` (string, required): Название товара (1-255 символов)
- `status` (string, optional): Статус товара (`active`, `inactive`, `archived`)
- `brand` (string, optional): Бренд товара (до 100 символов)
- `category` (string, optional): Категория товара (до 100 символов)

### Response

#### 200 OK - Все items успешно обработаны

```json
{
  "total": 2,
  "successful": 2,
  "failed": 0,
  "results": [
    {
      "index": 0,
      "status": "success",
      "status_code": 201,
      "data": {
        "id": 123,
        "sku": "ITEM-001",
        "title": "Sample Item 1",
        "status": "active",
        "brand": "Brand A",
        "category": "Electronics",
        "created_at": "2024-01-15T10:30:00Z"
      }
    },
    {
      "index": 1,
      "status": "success",
      "status_code": 201,
      "data": {
        "id": 124,
        "sku": "ITEM-002",
        "title": "Sample Item 2",
        "status": "active",
        "brand": null,
        "category": null,
        "created_at": "2024-01-15T10:30:01Z"
      }
    }
  ]
}
```

#### 207 Multi-Status - Смешанные результаты

```json
{
  "total": 3,
  "successful": 2,
  "failed": 1,
  "results": [
    {
      "index": 0,
      "status": "success",
      "status_code": 201,
      "data": {
        "id": 123,
        "sku": "ITEM-001",
        "title": "Sample Item 1",
        "status": "active",
        "created_at": "2024-01-15T10:30:00Z"
      }
    },
    {
      "index": 1,
      "status": "error",
      "status_code": 409,
      "error_code": "DUPLICATE_SKU",
      "error_message": "Item with SKU 'ITEM-002' already exists",
      "hint": "Use different SKU or update existing item"
    },
    {
      "index": 2,
      "status": "success",
      "status_code": 201,
      "data": {
        "id": 125,
        "sku": "ITEM-003",
        "title": "Sample Item 3",
        "status": "active",
        "created_at": "2024-01-15T10:30:02Z"
      }
    }
  ]
}
```

#### 400 Bad Request - Превышен лимит items

```json
{
  "detail": {
    "detail": "Too many items: 1001 (max 1000)",
    "error_code": "TOO_MANY_ITEMS",
    "max_items": 1000
  }
}
```

#### 413 Payload Too Large - Превышен лимит размера

```json
{
  "detail": {
    "detail": "Request too large: 12.5MB (max 10MB)",
    "error_code": "REQUEST_TOO_LARGE",
    "max_size_mb": 10
  }
}
```

## Коды ошибок

### Коды ошибок для отдельных items

| Код | Описание | HTTP Status |
|-----|----------|-------------|
| `DUPLICATE_SKU` | SKU уже существует | 409 |
| `INVALID_DATA` | Неверные данные | 400 |
| `VALIDATION_ERROR` | Ошибка валидации | 400 |
| `INTERNAL_ERROR` | Внутренняя ошибка сервера | 500 |
| `SKU_TOO_LONG` | SKU слишком длинный | 400 |
| `TITLE_REQUIRED` | Title обязателен | 400 |
| `INVALID_STATUS` | Неверный статус | 400 |

### Якорные ошибки (останавливают обработку)

| HTTP Status | Описание | Условие |
|-------------|----------|---------|
| 400 | Too Many Items | > 1000 items |
| 400 | Empty Items Array | Пустой массив items |
| 413 | Request Too Large | > 10MB размер запроса |
| 422 | Validation Error | Неверный формат JSON |

## Примеры использования

### Успешный bulk импорт

```bash
curl -X POST "http://localhost:8000/api/v1/items:bulk" \
  -H "Content-Type: application/json" \
  -d '{
    "items": [
      {"sku": "ITEM-001", "title": "Item 1", "status": "active"},
      {"sku": "ITEM-002", "title": "Item 2", "status": "active"}
    ]
  }'
```

### Bulk импорт с ошибками

```bash
curl -X POST "http://localhost:8000/api/v1/items:bulk" \
  -H "Content-Type: application/json" \
  -d '{
    "items": [
      {"sku": "ITEM-001", "title": "Valid Item", "status": "active"},
      {"sku": "", "title": "Invalid Item", "status": "active"},
      {"sku": "ITEM-003", "title": "Another Valid Item", "status": "active"}
    ]
  }'
```

### Получение лимитов

```bash
curl -X GET "http://localhost:8000/api/v1/items:bulk/limits"
```

## Логика обработки

### Алгоритм обработки

1. **Валидация запроса**:
   - Проверка размера запроса (≤ 10MB)
   - Проверка количества items (≤ 1000)
   - Валидация JSON формата

2. **Построчная обработка**:
   - Каждый item обрабатывается в отдельной транзакции
   - Валидация данных item
   - Проверка на дубликат SKU
   - Создание item в БД
   - Сохранение результата

3. **Формирование ответа**:
   - Подсчёт успешных/неуспешных операций
   - Определение HTTP статус кода (200/207)
   - Возврат детального отчёта

### Обработка ошибок

- **Якорные ошибки**: Останавливают обработку, возвращают 400/413
- **Ошибки валидации**: Обрабатываются построчно, не останавливают общий процесс
- **Дубликаты SKU**: Обрабатываются построчно, возвращают 409
- **Внутренние ошибки**: Логируются, возвращают 500

## Best Practices

### Для клиентов

1. **Размер батчей**:
   - Рекомендуется 100-500 items за запрос
   - Избегайте максимального лимита (1000) для стабильности

2. **Обработка ответов**:
   - Всегда проверяйте HTTP статус код
   - 200 = все успешно, 207 = есть ошибки
   - Анализируйте поле `failed` для понимания проблем

3. **Retry логика**:
   - При 200/207: не повторяйте запрос
   - При 400/413: исправьте данные и повторите
   - При 5xx: повторите через некоторое время

4. **Валидация данных**:
   - Проверяйте SKU на уникальность перед отправкой
   - Валидируйте обязательные поля
   - Используйте корректные статусы

### Для разработчиков

1. **Мониторинг**:
   - Отслеживайте метрики `bulk.total_items`, `bulk.successful_items`, `bulk.failed_items`
   - Мониторьте время обработки `bulk.processing_time_ms`
   - Алерты на высокий процент ошибок

2. **Логирование**:
   - Все операции логируются с correlation_id
   - Ошибки содержат детальную информацию
   - Производительность отслеживается

## Метрики и мониторинг

### Ключевые метрики

- `bulk.total_items` - общее количество items в запросе
- `bulk.successful_items` - успешно обработанных
- `bulk.failed_items` - с ошибками
- `bulk.processing_time_ms` - время обработки
- `bulk.validation_errors` - количество ошибок валидации

### Алерты

- Время обработки > 30 секунд
- Процент ошибок > 50%
- Количество запросов > 1000 items
- Размер запроса > 8MB

## Ограничения

1. **Производительность**:
   - Каждый item в отдельной транзакции
   - Время обработки растёт линейно с количеством items
   - Рекомендуется не более 500 items за запрос

2. **Память**:
   - Весь ответ загружается в память
   - Большие батчи могут потреблять много RAM

3. **Блокировки**:
   - Проверка дубликатов может создавать блокировки
   - При высокой нагрузке возможны задержки

## Версионирование

- Текущая версия: v1.0
- Обратная совместимость гарантируется
- Новые поля добавляются как optional
- Breaking changes требуют новой версии API
