# Конвенции именования и политика миграций

## Политика миграций

### Принципы

1. **Вперёд/назад совместимость** - все миграции должны быть обратимыми
2. **Версионирование схемы** - каждая миграция имеет уникальную версию
3. **Атомарность** - миграции выполняются в транзакциях
4. **Безопасность** - проверка совместимости перед применением
5. **Откат** - возможность отката к любой предыдущей версии

### Стратегия миграций

#### Forward Migrations (Вперёд)
- Добавление новых таблиц, колонок, индексов
- Изменение типов данных (только расширение)
- Добавление ограничений (с проверкой данных)
- Создание представлений и процедур

#### Backward Migrations (Назад)
- Удаление таблиц, колонок, индексов
- Изменение типов данных (только сужение с проверкой)
- Удаление ограничений
- Удаление представлений и процедур

#### Ограничения
- **НЕ ДОПУСКАЕТСЯ**: Изменение первичных ключей
- **НЕ ДОПУСКАЕТСЯ**: Переименование колонок (создать новую + миграция данных)
- **НЕ ДОПУСКАЕТСЯ**: Изменение NOT NULL без значения по умолчанию

### Версионирование схемы

#### Формат версии
```
YYYY.MM.DD.HHMMSS_description
```

Примеры:
- `2024.01.15.143022_add_bulk_jobs_table`
- `2024.01.15.150145_add_items_price_column`
- `2024.01.15.160230_create_cursor_pagination_index`

#### Структура миграций
```sql
-- Migration: 2024.01.15.143022_add_bulk_jobs_table
-- Description: Добавление таблицы для массовых операций
-- Author: Data Team
-- Created: 2024-01-15 14:30:22

-- Forward migration
BEGIN;

CREATE TABLE bulk_jobs (
    id BIGSERIAL PRIMARY KEY,
    job_id UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
    type VARCHAR(20) NOT NULL CHECK (type IN ('import', 'export', 'update')),
    status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'cancelled')),
    total_records INTEGER DEFAULT 0,
    processed_records INTEGER DEFAULT 0,
    failed_records INTEGER DEFAULT 0,
    progress_percentage DECIMAL(5,2) DEFAULT 0.00 CHECK (progress_percentage BETWEEN 0 AND 100),
    file_path VARCHAR(500),
    file_size BIGINT,
    error_message TEXT,
    created_by VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    metadata JSONB
);

CREATE INDEX idx_bulk_jobs_job_id ON bulk_jobs (job_id);
CREATE INDEX idx_bulk_jobs_status ON bulk_jobs (status);
CREATE INDEX idx_bulk_jobs_created_at ON bulk_jobs (created_at);

COMMIT;

-- Rollback migration
-- BEGIN;
-- DROP TABLE IF EXISTS bulk_jobs CASCADE;
-- COMMIT;
```

## Конвенции именования

### Таблицы
- **Формат**: `snake_case`, множественное число
- **Примеры**: `items`, `bulk_jobs`, `idempotency_keys`, `bulk_job_results`

### Колонки
- **Формат**: `snake_case`
- **Примеры**: `created_at`, `updated_at`, `job_id`, `record_index`

### Индексы
- **Формат**: `idx_{table}_{purpose}`
- **Примеры**: 
  - `idx_items_sku_unique` - уникальный индекс
  - `idx_items_cursor_pagination` - для курсорной пагинации
  - `idx_bulk_jobs_status` - для фильтрации по статусу

### Внешние ключи
- **Формат**: `fk_{table}_{referenced_table}`
- **Примеры**: `fk_bulk_job_results_bulk_jobs`, `fk_bulk_job_results_items`

### Ограничения
- **Формат**: `ck_{table}_{column}_{condition}`
- **Примеры**: 
  - `ck_items_price_positive` - цена положительная
  - `ck_bulk_jobs_progress_range` - процент в диапазоне 0-100

### Триггеры
- **Формат**: `tr_{table}_{action}_{purpose}`
- **Примеры**: 
  - `tr_items_update_timestamp` - обновление временной метки
  - `tr_items_increment_version` - увеличение версии

### Представления
- **Формат**: `v_{purpose}`
- **Примеры**: `v_active_items`, `v_bulk_job_summary`

### Процедуры/Функции
- **Формат**: `sp_{purpose}` (stored procedures), `fn_{purpose}` (functions)
- **Примеры**: `sp_cleanup_expired_keys`, `fn_calculate_progress`

## Типы данных

### Идентификаторы
- **Первичные ключи**: `BIGSERIAL` (PostgreSQL) / `BIGINT AUTO_INCREMENT` (MySQL)
- **Внешние ключи**: `BIGINT`
- **UUID**: `UUID` для публичных идентификаторов

### Строки
- **Короткие строки**: `VARCHAR(n)` с явным указанием длины
- **Длинные тексты**: `TEXT`
- **JSON**: `JSONB` (PostgreSQL) / `JSON` (MySQL)

### Числа
- **Целые**: `INTEGER` для счётчиков, `BIGINT` для больших чисел
- **Десятичные**: `DECIMAL(precision, scale)` для денежных сумм
- **Проценты**: `DECIMAL(5,2)` для процентов (0.00-100.00)

### Временные метки
- **Всегда**: `TIMESTAMP WITH TIME ZONE` (PostgreSQL) / `TIMESTAMP` (MySQL)
- **По умолчанию**: `DEFAULT NOW()` для `created_at`

### Перечисления
- **Формат**: `ENUM` с явным указанием значений
- **Примеры**: `status ENUM('active', 'inactive', 'archived')`

## Соглашения по коду

### SQL стиль
```sql
-- Используем UPPER CASE для ключевых слов
SELECT 
    i.id,
    i.sku,
    i.title,
    i.created_at
FROM items i
WHERE i.status = 'active'
    AND i.created_at >= '2024-01-01'
ORDER BY i.created_at DESC, i.id DESC
LIMIT 100;
```

### Именование в коде
```python
# Python/SQLAlchemy
class BulkJob(Base):
    __tablename__ = "bulk_jobs"
    
    id = Column(BigInteger, primary_key=True)
    job_id = Column(UUID, unique=True, nullable=False)
    status = Column(Enum(BulkJobStatus), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
```

## Процесс разработки миграций

### 1. Планирование
- [ ] Анализ влияния на существующие данные
- [ ] Оценка времени выполнения
- [ ] Планирование отката
- [ ] Тестирование на копии данных

### 2. Разработка
- [ ] Создание forward миграции
- [ ] Создание backward миграции
- [ ] Добавление проверок данных
- [ ] Документирование изменений

### 3. Тестирование
- [ ] Тест на пустой базе
- [ ] Тест на тестовых данных
- [ ] Тест отката
- [ ] Тест производительности

### 4. Развёртывание
- [ ] Бэкап продакшн базы
- [ ] Применение миграции
- [ ] Проверка целостности
- [ ] Мониторинг производительности

## Мониторинг миграций

### Метрики
- Время выполнения миграций
- Количество затронутых записей
- Ошибки при применении
- Производительность после миграции

### Логирование
- Детальные логи выполнения
- Откат изменений при ошибках
- Уведомления о завершении
- Аудит всех изменений схемы

## Инструменты

### Alembic (Python/SQLAlchemy)
```python
# alembic.ini
[alembic]
script_location = alembic
sqlalchemy.url = postgresql://user:pass@localhost/db

# Версионирование
alembic revision --autogenerate -m "add bulk jobs table"
alembic upgrade head
alembic downgrade -1
```

### Flyway (Java)
```sql
-- V20240115.143022__Add_bulk_jobs_table.sql
-- R20240115.143022__Rollback_bulk_jobs_table.sql
```

### Liquibase (Java)
```xml
<changeSet id="20240115-143022" author="data-team">
    <createTable tableName="bulk_jobs">
        <column name="id" type="BIGSERIAL">
            <constraints primaryKey="true"/>
        </column>
    </createTable>
</changeSet>
```

