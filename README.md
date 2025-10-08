# Data Intake Service (DIS)

Сервис на FastAPI для приёма и каталога записей с курсорной пагинацией, идемпотентными POST, bulk-загрузкой, валидацией потоков, версиями API, защитой и наблюдаемостью.

## Цели проекта

- Изучение современных подходов к разработке микросервисов
- Практика работы с FastAPI, SQLAlchemy, структурированным логированием
- Реализация паттернов: курсорная пагинация, идемпотентность, bulk-операции
- Настройка наблюдаемости и мониторинга

## Как запускать

### Требования
- Python 3.8+
- pip

### Установка зависимостей
```bash
pip install -r requirements.txt
```

### Запуск сервиса
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Проверка работы
- API документация: http://localhost:8000/docs
- Health check: http://localhost:8000/healthz
- Readiness check: http://localhost:8000/readyz

## Структура проекта

```
app/
├── api/           # API эндпоинты
│   ├── health.py  # Health checks
│   └── items.py   # CRUD операции для Items
├── models/        # Модели данных
│   └── item.py    # Item модель (SQLAlchemy + Pydantic)
├── database/      # Конфигурация БД
│   └── connection.py
├── middleware/    # Middleware компоненты
│   └── logging.py # Логирование с correlation-id
└── main.py        # Точка входа FastAPI

docs/              # Документация
├── ADR-001-architecture.md
└── DoD-checklist.md

tests/             # Тесты
```

## API Endpoints

### Health
- `GET /healthz` - Liveness probe
- `GET /readyz` - Readiness probe

### Items
- `POST /api/v1/items` - Создание Item
- `GET /api/v1/items/{id}` - Получение Item по ID
- `GET /api/v1/items` - Список Items (с пагинацией)

## Модель данных

### Item
- `id` (Integer) - Автоинкрементный идентификатор
- `sku` (String) - Уникальный артикул товара
- `title` (String) - Название товара
- `created_at` (DateTime) - Время создания

## Логирование

Сервис использует структурированное JSON логирование с:
- `correlation_id` - для трейсинга запросов
- `request_id` - уникальный ID запроса
- Временными метками в ISO формате
- Уровнями логирования

## Разработка

### Создание виртуального окружения
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate     # Windows
```

### Установка зависимостей для разработки
```bash
pip install -r requirements.txt
```

### Запуск в режиме разработки
```bash
uvicorn app.main:app --reload
```

## Следующие шаги

1. ✅ Каркас сервиса (скелет)
2. 🔄 Курсорная пагинация
3. 🔄 Идемпотентные POST запросы
4. 🔄 Bulk-загрузка
5. 🔄 Версионирование API
6. 🔄 Защита и безопасность
7. 🔄 Наблюдаемость и метрики
A microservice for receiving, validating, and storing reference data about products (for example, pharmaceutical SKUs, nomenclature, or any catalog with the fields sku, name, price, brand).
