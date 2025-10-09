# Модель данных Data Intake Service

## Обзор

Сервис Data Intake Service (DIS) предназначен для приёма, валидации и хранения справочных данных о продуктах. Основные сущности включают товары (items), ключи идемпотентности, массовые операции и их результаты.

## Таблицы

### 1. items - Основная таблица товаров

**Назначение**: Хранение справочной информации о товарах/продуктах.

**Поля**:
- `id` (BIGINT, PRIMARY KEY, AUTO_INCREMENT) - Уникальный идентификатор записи
- `sku` (VARCHAR(100), UNIQUE, NOT NULL) - Артикул товара (доменный ключ)
- `title` (VARCHAR(255), NOT NULL) - Название товара
- `description` (TEXT, NULLABLE) - Описание товара
- `price` (DECIMAL(10,2), NULLABLE) - Цена товара
- `brand` (VARCHAR(100), NULLABLE) - Бренд товара
- `category` (VARCHAR(100), NULLABLE) - Категория товара
- `status` (ENUM('active', 'inactive', 'archived'), DEFAULT 'active') - Статус товара
- `created_at` (TIMESTAMP WITH TIME ZONE, NOT NULL) - Время создания записи
- `updated_at` (TIMESTAMP WITH TIME ZONE, NOT NULL) - Время последнего обновления
- `version` (INTEGER, DEFAULT 1) - Версия записи для оптимистичной блокировки

**Индексы**:
- PRIMARY KEY на `id`
- UNIQUE INDEX на `sku` (доменный ключ)
- COMPOSITE INDEX на `(created_at, id)` для курсорной пагинации
- INDEX на `status` для фильтрации активных товаров
- INDEX на `brand` для поиска по бренду
- INDEX на `category` для фильтрации по категории

### 2. idempotency_keys - Ключи идемпотентности

**Назначение**: Обеспечение идемпотентности операций через уникальные ключи запросов.

**Поля**:
- `id` (BIGINT, PRIMARY KEY, AUTO_INCREMENT) - Уникальный идентификатор
- `key` (VARCHAR(255), UNIQUE, NOT NULL) - Ключ идемпотентности
- `request_hash` (VARCHAR(64), NOT NULL) - SHA-256 хеш тела запроса
- `response_data` (JSON, NULLABLE) - Кэшированный ответ
- `status` (ENUM('processing', 'completed', 'failed'), NOT NULL) - Статус обработки
- `created_at` (TIMESTAMP WITH TIME ZONE, NOT NULL) - Время создания
- `expires_at` (TIMESTAMP WITH TIME ZONE, NOT NULL) - Время истечения (TTL)
- `client_ip` (INET, NULLABLE) - IP адрес клиента
- `user_agent` (TEXT, NULLABLE) - User-Agent клиента

**Индексы**:
- PRIMARY KEY на `id`
- UNIQUE INDEX на `key`
- INDEX на `expires_at` для очистки истёкших ключей
- INDEX на `status` для мониторинга

### 3. bulk_jobs - Массовые операции

**Назначение**: Управление массовыми операциями загрузки данных.

**Поля**:
- `id` (BIGINT, PRIMARY KEY, AUTO_INCREMENT) - Уникальный идентификатор
- `job_id` (UUID, UNIQUE, NOT NULL) - Публичный идентификатор задачи
- `type` (ENUM('import', 'export', 'update'), NOT NULL) - Тип операции
- `status` (ENUM('pending', 'processing', 'completed', 'failed', 'cancelled'), NOT NULL) - Статус
- `total_records` (INTEGER, DEFAULT 0) - Общее количество записей
- `processed_records` (INTEGER, DEFAULT 0) - Обработанных записей
- `failed_records` (INTEGER, DEFAULT 0) - Записей с ошибками
- `progress_percentage` (DECIMAL(5,2), DEFAULT 0.00) - Процент выполнения
- `file_path` (VARCHAR(500), NULLABLE) - Путь к файлу данных
- `file_size` (BIGINT, NULLABLE) - Размер файла в байтах
- `error_message` (TEXT, NULLABLE) - Сообщение об ошибке
- `created_by` (VARCHAR(100), NULLABLE) - Пользователь, создавший задачу
- `created_at` (TIMESTAMP WITH TIME ZONE, NOT NULL) - Время создания
- `started_at` (TIMESTAMP WITH TIME ZONE, NULLABLE) - Время начала обработки
- `completed_at` (TIMESTAMP WITH TIME ZONE, NULLABLE) - Время завершения
- `metadata` (JSON, NULLABLE) - Дополнительные метаданные

**Индексы**:
- PRIMARY KEY на `id`
- UNIQUE INDEX на `job_id`
- INDEX на `status` для фильтрации по статусу
- INDEX на `created_at` для сортировки по времени
- INDEX на `created_by` для фильтрации по пользователю

### 4. bulk_job_results - Результаты массовых операций

**Назначение**: Детальные результаты обработки каждой записи в массовой операции.

**Поля**:
- `id` (BIGINT, PRIMARY KEY, AUTO_INCREMENT) - Уникальный идентификатор
- `bulk_job_id` (BIGINT, NOT NULL, FOREIGN KEY) - Ссылка на bulk_jobs.id
- `record_index` (INTEGER, NOT NULL) - Порядковый номер записи в файле
- `record_data` (JSON, NULLABLE) - Исходные данные записи
- `status` (ENUM('success', 'error', 'warning'), NOT NULL) - Статус обработки
- `error_code` (VARCHAR(50), NULLABLE) - Код ошибки
- `error_message` (TEXT, NULLABLE) - Сообщение об ошибке
- `item_id` (BIGINT, NULLABLE, FOREIGN KEY) - Ссылка на созданный/обновлённый item
- `processing_time_ms` (INTEGER, NULLABLE) - Время обработки в миллисекундах
- `created_at` (TIMESTAMP WITH TIME ZONE, NOT NULL) - Время создания записи

**Индексы**:
- PRIMARY KEY на `id`
- FOREIGN KEY на `bulk_job_id` → `bulk_jobs.id`
- FOREIGN KEY на `item_id` → `items.id`
- COMPOSITE INDEX на `(bulk_job_id, record_index)` для быстрого поиска
- INDEX на `status` для фильтрации результатов
- INDEX на `error_code` для анализа ошибок

## Правила индексов

### Составной индекс для курсорной пагинации
```sql
CREATE INDEX idx_items_cursor_pagination ON items (created_at, id);
```
- Позволяет эффективно реализовать курсорную пагинацию
- Обеспечивает стабильную сортировку при одинаковых `created_at`
- Поддерживает фильтрацию по временному диапазону

### Уникальность доменного ключа
```sql
CREATE UNIQUE INDEX idx_items_sku_unique ON items (sku);
```
- Гарантирует уникальность артикула товара
- Обеспечивает быстрый поиск по SKU
- Предотвращает дублирование товаров

### Дополнительные индексы для производительности
- `idx_items_status` - для фильтрации активных товаров
- `idx_items_brand` - для поиска по бренду
- `idx_items_category` - для фильтрации по категории
- `idx_idempotency_expires` - для очистки истёкших ключей
- `idx_bulk_jobs_status` - для мониторинга задач

## Ограничения и связи

### Внешние ключи
- `bulk_job_results.bulk_job_id` → `bulk_jobs.id` (CASCADE DELETE)
- `bulk_job_results.item_id` → `items.id` (SET NULL)

### Проверочные ограничения
- `items.price >= 0` - цена не может быть отрицательной
- `bulk_jobs.progress_percentage BETWEEN 0 AND 100` - процент в допустимом диапазоне
- `bulk_job_results.record_index >= 0` - индекс записи неотрицательный

### Триггеры
- Автоматическое обновление `updated_at` при изменении записей
- Автоматическое увеличение `version` при обновлении items
- Очистка истёкших ключей идемпотентности по расписанию

## Масштабирование

### Партиционирование
- `items` по `created_at` (месячные партиции)
- `bulk_job_results` по `bulk_job_id` (хеш-партиционирование)

### Архивация
- Перемещение старых записей в архивные таблицы
- Сжатие исторических данных
- Периодическая очистка временных данных

