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

## Мониторинг и метрики

### Ключевые метрики
- Время выполнения запросов
- Использование индексов
- Количество блокировок
- Размер таблиц и индексов
- Статистика по операциям

### Алерты
- Время выполнения запроса > 1 секунды
- Отсутствие использования индекса
- Высокий уровень блокировок
- Быстрый рост размера таблиц

### Логирование
- Все DDL операции
- Медленные запросы (> 100ms)
- Ошибки уникальности
- Откаты транзакций

