# Тестовые сценарии для модели данных

## Обзор

Документ описывает ключевые тестовые сценарии для проверки производительности, целостности и корректности работы модели данных Data Intake Service.

## Сценарий 1: Выборка по индексу (10 млн строк)

### Описание
Тестирование производительности курсорной пагинации на большой таблице items с 10 миллионами записей.

### Подготовка данных
```sql
-- Создание тестовых данных (10 млн записей)
INSERT INTO items (sku, title, description, price, brand, category, status, created_at)
SELECT 
    'SKU-' || LPAD(generate_series(1, 10000000)::text, 8, '0'),
    'Test Item ' || generate_series(1, 10000000),
    'Test description for item ' || generate_series(1, 10000000),
    (random() * 1000)::decimal(10,2),
    CASE (random() * 10)::int
        WHEN 0 THEN 'Brand A'
        WHEN 1 THEN 'Brand B'
        WHEN 2 THEN 'Brand C'
        ELSE 'Brand ' || chr(65 + (random() * 20)::int)
    END,
    CASE (random() * 5)::int
        WHEN 0 THEN 'Electronics'
        WHEN 1 THEN 'Clothing'
        WHEN 2 THEN 'Books'
        WHEN 3 THEN 'Home'
        ELSE 'Sports'
    END,
    CASE (random() * 10)::int
        WHEN 0 THEN 'inactive'
        WHEN 1 THEN 'archived'
        ELSE 'active'
    END,
    NOW() - (random() * interval '365 days')
FROM generate_series(1, 10000000);
```

### Тестовые запросы

#### 1.1 Курсорная пагинация (первая страница)
```sql
-- Время выполнения: < 50ms
EXPLAIN (ANALYZE, BUFFERS) 
SELECT id, sku, title, created_at
FROM items 
WHERE status = 'active'
ORDER BY created_at DESC, id DESC
LIMIT 100;
```

**Ожидаемый результат**:
- Использование индекса `idx_items_cursor_pagination`
- Время выполнения < 50ms
- Количество прочитанных страниц < 10

#### 1.2 Курсорная пагинация (средняя страница)
```sql
-- Время выполнения: < 50ms
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, sku, title, created_at
FROM items 
WHERE status = 'active'
    AND (created_at < '2024-06-15 10:30:00' OR 
         (created_at = '2024-06-15 10:30:00' AND id < 5000000))
ORDER BY created_at DESC, id DESC
LIMIT 100;
```

#### 1.3 Поиск по SKU
```sql
-- Время выполнения: < 5ms
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, sku, title, price, brand
FROM items 
WHERE sku = 'SKU-05000000';
```

**Ожидаемый результат**:
- Использование уникального индекса `idx_items_sku_unique`
- Время выполнения < 5ms
- Index Scan, не Seq Scan

#### 1.4 Фильтрация по бренду
```sql
-- Время выполнения: < 200ms
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, sku, title, price
FROM items 
WHERE brand = 'Brand A'
    AND status = 'active'
ORDER BY created_at DESC, id DESC
LIMIT 1000;
```

### Критерии успеха
- [ ] Все запросы выполняются быстрее указанных лимитов
- [ ] Используются правильные индексы
- [ ] Нет последовательного сканирования (Seq Scan)
- [ ] Память используется эффективно

## Сценарий 2: Конфликт уникальности

### Описание
Тестирование обработки конфликтов уникальности при вставке дублирующихся SKU.

### Подготовка
```sql
-- Создание тестовых данных
INSERT INTO items (sku, title, status) VALUES 
('CONFLICT-TEST-001', 'Original Item', 'active');
```

### Тестовые случаи

#### 2.1 Попытка вставки дублирующегося SKU
```sql
-- Ожидается ошибка уникальности
INSERT INTO items (sku, title, status) VALUES 
('CONFLICT-TEST-001', 'Duplicate Item', 'active');
```

**Ожидаемый результат**:
- Ошибка: `duplicate key value violates unique constraint "idx_items_sku_unique"`
- Код ошибки: `23505` (PostgreSQL)
- Транзакция откатывается

#### 2.2 UPSERT операция (ON CONFLICT)
```sql
-- Успешное обновление существующей записи
INSERT INTO items (sku, title, status, updated_at) 
VALUES ('CONFLICT-TEST-001', 'Updated Item', 'active', NOW())
ON CONFLICT (sku) 
DO UPDATE SET 
    title = EXCLUDED.title,
    status = EXCLUDED.status,
    updated_at = EXCLUDED.updated_at,
    version = items.version + 1;
```

**Ожидаемый результат**:
- Запись обновляется
- `version` увеличивается на 1
- `updated_at` обновляется
- Возвращается обновленная запись

#### 2.3 Массовая вставка с конфликтами
```sql
-- Тест массовой вставки с дубликатами
INSERT INTO items (sku, title, status) VALUES 
('BULK-TEST-001', 'Bulk Item 1', 'active'),
('BULK-TEST-002', 'Bulk Item 2', 'active'),
('CONFLICT-TEST-001', 'Duplicate in Bulk', 'active'),  -- Конфликт
('BULK-TEST-003', 'Bulk Item 3', 'active')
ON CONFLICT (sku) 
DO UPDATE SET 
    title = EXCLUDED.title,
    updated_at = NOW(),
    version = items.version + 1;
```

**Ожидаемый результат**:
- 3 новые записи создаются
- 1 запись обновляется
- Все операции в одной транзакции

### Критерии успеха
- [ ] Конфликты обрабатываются корректно
- [ ] UPSERT работает как ожидается
- [ ] Версионирование работает правильно
- [ ] Транзакции атомарны

## Сценарий 3: Идемпотентность операций

### Описание
Тестирование системы идемпотентности через таблицу `idempotency_keys`.

### Подготовка
```sql
-- Очистка старых ключей
DELETE FROM idempotency_keys WHERE expires_at < NOW();
```

### Тестовые случаи

#### 3.1 Первый запрос с новым ключом
```sql
-- Создание ключа идемпотентности
INSERT INTO idempotency_keys (key, request_hash, status, expires_at)
VALUES (
    'test-key-001',
    'sha256-hash-of-request-body',
    'processing',
    NOW() + INTERVAL '1 hour'
);

-- Симуляция обработки запроса
UPDATE idempotency_keys 
SET status = 'completed',
    response_data = '{"id": 123, "sku": "TEST-001", "status": "created"}'
WHERE key = 'test-key-001';
```

#### 3.2 Повторный запрос с тем же ключом
```sql
-- Попытка создать дублирующийся ключ
INSERT INTO idempotency_keys (key, request_hash, status, expires_at)
VALUES (
    'test-key-001',
    'sha256-hash-of-request-body',
    'processing',
    NOW() + INTERVAL '1 hour'
);
```

**Ожидаемый результат**:
- Ошибка уникальности
- Возврат кэшированного ответа из первого запроса

#### 3.3 Проверка TTL (Time To Live)
```sql
-- Создание ключа с истёкшим TTL
INSERT INTO idempotency_keys (key, request_hash, status, expires_at)
VALUES (
    'expired-key-001',
    'sha256-hash-of-request-body',
    'completed',
    NOW() - INTERVAL '1 hour'
);

-- Очистка истёкших ключей
DELETE FROM idempotency_keys WHERE expires_at < NOW();
```

### Критерии успеха
- [ ] Ключи идемпотентности работают корректно
- [ ] TTL механизм функционирует
- [ ] Кэширование ответов работает
- [ ] Очистка истёкших ключей выполняется

## Сценарий 4: Массовые операции

### Описание
Тестирование системы массовых операций (bulk jobs) с большими объёмами данных.

### Подготовка
```sql
-- Создание тестовой массовой операции
INSERT INTO bulk_jobs (job_id, type, status, total_records, created_by)
VALUES (
    gen_random_uuid(),
    'import',
    'pending',
    100000,
    'test-user'
);
```

### Тестовые случаи

#### 4.1 Создание массовой операции
```sql
-- Проверка создания задачи
SELECT 
    job_id,
    type,
    status,
    total_records,
    progress_percentage,
    created_at
FROM bulk_jobs 
WHERE created_by = 'test-user'
ORDER BY created_at DESC
LIMIT 1;
```

#### 4.2 Обработка записей массовой операции
```sql
-- Симуляция обработки записей
UPDATE bulk_jobs 
SET 
    status = 'processing',
    started_at = NOW(),
    processed_records = 50000,
    failed_records = 100,
    progress_percentage = 50.00
WHERE job_id = (SELECT job_id FROM bulk_jobs WHERE created_by = 'test-user' LIMIT 1);

-- Добавление результатов обработки
INSERT INTO bulk_job_results (bulk_job_id, record_index, record_data, status, processing_time_ms)
SELECT 
    (SELECT id FROM bulk_jobs WHERE created_by = 'test-user' LIMIT 1),
    generate_series(1, 1000),
    json_build_object('sku', 'BULK-' || generate_series(1, 1000)),
    CASE (random() * 10)::int
        WHEN 0 THEN 'error'
        WHEN 1 THEN 'warning'
        ELSE 'success'
    END,
    (random() * 100)::int;
```

#### 4.3 Завершение массовой операции
```sql
-- Завершение задачи
UPDATE bulk_jobs 
SET 
    status = 'completed',
    completed_at = NOW(),
    processed_records = 100000,
    progress_percentage = 100.00
WHERE job_id = (SELECT job_id FROM bulk_jobs WHERE created_by = 'test-user' LIMIT 1);
```

### Критерии успеха
- [ ] Массовые операции создаются корректно
- [ ] Прогресс отслеживается правильно
- [ ] Результаты сохраняются
- [ ] Статистика вычисляется верно

## Сценарий 5: Производительность при высокой нагрузке

### Описание
Тестирование системы под высокой нагрузкой с множественными одновременными операциями.

### Нагрузочные тесты

#### 5.1 Параллельные вставки
```sql
-- Симуляция 100 параллельных вставок
-- (выполняется в 100 параллельных сессиях)
INSERT INTO items (sku, title, status) VALUES 
('LOAD-TEST-' || extract(epoch from now())::bigint || '-' || random()::text,
 'Load Test Item', 'active');
```

#### 5.2 Параллельные чтения
```sql
-- Симуляция 1000 параллельных запросов на чтение
SELECT id, sku, title, created_at
FROM items 
WHERE status = 'active'
ORDER BY created_at DESC, id DESC
LIMIT 100;
```

#### 5.3 Смешанная нагрузка
- 70% операций чтения
- 20% операций записи
- 10% операций обновления

### Критерии успеха
- [ ] Система выдерживает нагрузку
- [ ] Время отклика остается приемлемым
- [ ] Нет блокировок и дедлоков
- [ ] Целостность данных сохраняется

## Сценарий 6: Курсорная пагинация

### Описание
Тестирование курсорной (keyset) пагинации для эндпоинта `/api/v1/items` с использованием пары `(created_at, id)`.

### Подготовка данных
```python
# Создание тестовых данных для пагинации
def create_test_items_for_pagination(count: int):
    """Создает тестовые items с разными временными метками"""
    items = []
    base_time = datetime.now(timezone.utc)
    
    for i in range(count):
        item = Item(
            sku=f"PAGINATION-{i:06d}",
            title=f"Pagination Test Item {i}",
            status="active" if i % 2 == 0 else "inactive",
            brand=f"Brand {i % 3}",
            category=f"Category {i % 2}",
            created_at=base_time + timedelta(seconds=i)
        )
        items.append(item)
    
    return items
```

### Тестовые случаи

#### 6.1 Стабильность порядка
```python
def test_pagination_stability():
    """Тест стабильного порядка между страницами"""
    # Создаем 300 items
    items = create_test_items_for_pagination(300)
    
    all_items = []
    cursor = None
    page_count = 0
    
    # Проходим несколько страниц
    while page_count < 5:
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
```

#### 6.2 Отсутствие дрейфа при вставках
```python
def test_no_drift_on_insertions():
    """Тест отсутствия дрейфа при вставках во время пагинации"""
    # Создаем 100 items
    items = create_test_items_for_pagination(100)
    
    # Получаем первую страницу
    response1 = client.get("/api/v1/items?limit=50")
    data1 = response1.json()
    cursor = data1["next_cursor"]
    
    # Добавляем 50 новых items
    new_items = create_test_items_for_pagination(50)
    
    # Получаем вторую страницу с тем же курсором
    response2 = client.get(f"/api/v1/items?limit=50&cursor={cursor}")
    data2 = response2.json()
    
    # Проверяем, что новые items не попали на вторую страницу
    page1_ids = {item["id"] for item in data1["items"]}
    page2_ids = {item["id"] for item in data2["items"]}
    new_item_ids = {item.id for item in new_items}
    
    assert len(page2_ids & new_item_ids) == 0
    assert len(page1_ids & page2_ids) == 0
```

#### 6.3 Фильтрация с пагинацией
```python
def test_pagination_with_filters():
    """Тест пагинации с фильтрами"""
    # Создаем items с разными статусами
    active_items = create_test_items_for_pagination(50, status="active")
    inactive_items = create_test_items_for_pagination(30, status="inactive")
    
    # Тестируем фильтрацию по статусу
    response = client.get("/api/v1/items?status=active&limit=20")
    assert response.status_code == 200
    
    data = response.json()
    assert all(item["status"] == "active" for item in data["items"])
    
    # Тестируем пагинацию с фильтром
    if data["has_more"]:
        response2 = client.get(f"/api/v1/items?status=active&limit=20&cursor={data['next_cursor']}")
        assert response2.status_code == 200
        data2 = response2.json()
        assert all(item["status"] == "active" for item in data2["items"])
```

#### 6.4 Обработка ошибок курсора
```python
def test_cursor_error_handling():
    """Тест обработки ошибок курсора"""
    # Невалидный base64
    response = client.get("/api/v1/items?cursor=invalid-base64!")
    assert response.status_code == 400
    assert "Invalid cursor format" in response.json()["detail"]
    
    # Невалидный JSON
    invalid_json = base64.b64encode("invalid json".encode('utf-8')).decode('utf-8')
    response = client.get(f"/api/v1/items?cursor={invalid_json}")
    assert response.status_code == 400
    
    # Отсутствующие поля
    cursor_data = {"created_at": "2024-01-15T10:30:00Z"}
    cursor = base64.b64encode(json.dumps(cursor_data).encode('utf-8')).decode('utf-8')
    response = client.get(f"/api/v1/items?cursor={cursor}")
    assert response.status_code == 400
```

#### 6.5 Производительность глубокой пагинации
```python
def test_deep_pagination_performance():
    """Тест производительности глубокой пагинации"""
    # Создаем 1000+ items
    items = create_test_items_for_pagination(1000)
    
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
    
    # Проверяем, что время ответа приемлемое
    assert total_time < 1.0  # Менее 1 секунды для 10+ страниц
    assert page_count >= 10
```

### Критерии успеха
- [ ] Порядок элементов стабилен между страницами
- [ ] Новые вставки не вызывают дрейф страниц
- [ ] Фильтрация работает корректно с пагинацией
- [ ] Ошибки курсора обрабатываются с HTTP 400
- [ ] Производительность остается стабильной на глубине 1000+ страниц
- [ ] P95 latency < 100ms для одной страницы

## Сценарий 7: Идемпотентность POST операций

### Описание
Тестирование системы идемпотентности для POST запросов с использованием заголовка `Idempotency-Key`.

### Подготовка
```python
# Очистка таблиц идемпотентности
def cleanup_idempotency_tables():
    db = SessionLocal()
    try:
        db.query(IdempotencyKey).delete()
        db.query(Item).delete()
        db.commit()
    finally:
        db.close()
```

### Тестовые случаи

#### 7.1 Базовые сценарии идемпотентности
```python
def test_basic_idempotency():
    """Тест базовой идемпотентности"""
    item_data = {
        "sku": "IDEMPOTENCY-001",
        "title": "Idempotency Test Item",
        "status": "active"
    }
    
    headers = {"Idempotency-Key": "test-key-001"}
    
    # Первый запрос
    response1 = client.post("/api/v1/items", json=item_data, headers=headers)
    assert response1.status_code == 201
    data1 = response1.json()
    
    # Повторный запрос с тем же ключом и телом
    response2 = client.post("/api/v1/items", json=item_data, headers=headers)
    assert response2.status_code == 201
    data2 = response2.json()
    
    # Ответы должны быть идентичными
    assert data1 == data2
    
    # В БД должен быть только один item
    items = db.query(Item).filter(Item.sku == "IDEMPOTENCY-001").all()
    assert len(items) == 1
```

#### 7.2 Конфликт идемпотентности
```python
def test_idempotency_conflict():
    """Тест конфликта при разных телах запроса"""
    item_data1 = {
        "sku": "IDEMPOTENCY-002",
        "title": "Item 1",
        "status": "active"
    }
    
    item_data2 = {
        "sku": "IDEMPOTENCY-003",
        "title": "Item 2",
        "status": "active"
    }
    
    headers = {"Idempotency-Key": "conflict-test-key"}
    
    # Первый запрос
    response1 = client.post("/api/v1/items", json=item_data1, headers=headers)
    assert response1.status_code == 201
    
    # Второй запрос с другим телом
    response2 = client.post("/api/v1/items", json=item_data2, headers=headers)
    assert response2.status_code == 409
    
    error_data = response2.json()
    assert error_data["error_code"] == "IDEMPOTENCY_KEY_CONFLICT"
```

#### 7.3 Race conditions
```python
def test_race_conditions():
    """Тест race conditions при параллельных запросах"""
    item_data = {
        "sku": "RACE-TEST-001",
        "title": "Race Test Item",
        "status": "active"
    }
    
    headers = {"Idempotency-Key": "race-test-key"}
    
    # Симулируем параллельные запросы
    responses = []
    
    def make_request():
        response = client.post("/api/v1/items", json=item_data, headers=headers)
        responses.append(response)
    
    # Создаём несколько потоков
    threads = []
    for _ in range(3):
        thread = threading.Thread(target=make_request)
        threads.append(thread)
        thread.start()
    
    # Ждём завершения
    for thread in threads:
        thread.join()
    
    # Проверяем результаты
    success_count = sum(1 for r in responses if r.status_code == 201)
    conflict_count = sum(1 for r in responses if r.status_code == 409)
    
    assert success_count == 1
    assert conflict_count == 2
```

#### 7.4 TTL и временные интервалы
```python
def test_ttl_mechanism():
    """Тест механизма TTL"""
    item_data = {
        "sku": "TTL-TEST-001",
        "title": "TTL Test Item",
        "status": "active"
    }
    
    headers = {"Idempotency-Key": "ttl-test-key"}
    
    # Первый запрос
    response1 = client.post("/api/v1/items", json=item_data, headers=headers)
    assert response1.status_code == 201
    
    # Симулируем истечение TTL
    db = SessionLocal()
    try:
        key = db.query(IdempotencyKey).filter(IdempotencyKey.key == "ttl-test-key").first()
        key.expires_at = datetime.utcnow() - timedelta(minutes=1)
        db.commit()
    finally:
        db.close()
    
    # Новый запрос должен пройти
    response2 = client.post("/api/v1/items", json=item_data, headers=headers)
    assert response2.status_code == 201
```

#### 7.5 Валидация ключей
```python
def test_key_validation():
    """Тест валидации ключей идемпотентности"""
    item_data = {"sku": "VALID-001", "title": "Test", "status": "active"}
    
    # Невалидные ключи
    invalid_keys = [
        "",  # Пустой
        "a" * 256,  # Слишком длинный
        "invalid@key#123",  # Специальные символы
        "key with spaces"  # Пробелы
    ]
    
    for invalid_key in invalid_keys:
        headers = {"Idempotency-Key": invalid_key}
        response = client.post("/api/v1/items", json=item_data, headers=headers)
        assert response.status_code == 400
        assert response.json()["error_code"] == "INVALID_IDEMPOTENCY_KEY"
```

### Критерии успеха
- [ ] Повторные запросы с тем же ключом возвращают тот же ответ
- [ ] Конфликты при разных телах обрабатываются корректно
- [ ] Race conditions не создают дублирующие записи
- [ ] TTL механизм работает правильно
- [ ] Валидация ключей отклоняет невалидные форматы
- [ ] Hit rate идемпотентности > 80% при нормальной работе
- [ ] Время ответа кэшированных запросов < 50ms

## Мониторинг и метрики

### Ключевые метрики
- Время выполнения запросов
- Использование индексов
- Количество блокировок
- Размер таблиц и индексов
- Статистика по операциям
- **api.items.list.latency_ms** - время ответа пагинации
- **api.items.list.pages_depth** - глубина пагинации
- **api.items.list.cursor_errors** - ошибки декодирования курсора
- **idempotency.hit** - попадания в кэш идемпотентности
- **idempotency.miss** - промахи кэша идемпотентности
- **idempotency.conflict** - конфликты идемпотентности
- **idempotency.cleanup.count** - количество очищенных ключей

### Алерты
- Время выполнения запроса > 1 секунды
- Отсутствие использования индекса
- Высокий уровень блокировок
- Быстрый рост размера таблиц
- **Время ответа пагинации > 100ms**
- **Высокий уровень ошибок курсора**
- **Hit rate идемпотентности < 50%**
- **Высокий уровень конфликтов идемпотентности**

### Логирование
- Все DDL операции
- Медленные запросы (> 100ms)
- Ошибки уникальности
- Откаты транзакций
- **Метрики курсорной пагинации**
- **Операции идемпотентности (hit/miss/conflict)**
- **Очистка истёкших ключей**

