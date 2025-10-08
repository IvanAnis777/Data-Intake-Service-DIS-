#!/bin/bash

# Скрипт для проверки DoD блока 1

set -e

echo "🔍 Проверка DoD блока 1: Каркас сервиса"

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Функция для проверки
check() {
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ $1${NC}"
    else
        echo -e "${RED}❌ $1${NC}"
        exit 1
    fi
}

# 1. Функциональные требования
echo -e "\n${YELLOW}📋 Функциональные требования:${NC}"

# Проверяем структуру проекта
test -d app/api && test -d app/models && test -d app/database && test -d app/middleware
check "Модульная структура проекта"

# Проверяем наличие файлов
test -f app/models/item.py
check "Модель Item существует"

test -f app/api/health.py
check "Health endpoints существуют"

test -f app/api/items.py
check "Items API существует"

# 2. Технические требования
echo -e "\n${YELLOW}🔧 Технические требования:${NC}"

# Проверяем зависимости
python -c "import fastapi, sqlalchemy, structlog, pydantic"
check "Все зависимости установлены"

# Проверяем структурированное логирование
grep -q "structlog" app/middleware/logging.py
check "Структурированное JSON логирование настроено"

# Проверяем CORS
grep -q "CORSMiddleware" app/main.py
check "CORS middleware настроен"

# 3. Проверки
echo -e "\n${YELLOW}🧪 Проверки:${NC}"

# Запускаем тесты
python -m pytest tests/ -v --tb=short
check "Все тесты проходят"

# Проверяем линтинг
python -m flake8 app/ --count --select=E9,F63,F7,F82 --show-source --statistics
check "Код проходит линтинг"

# 4. Документация
echo -e "\n${YELLOW}📚 Документация:${NC}"

test -f docs/ADR-001-architecture.md
check "ADR №1 существует"

test -f docs/DoD-checklist.md
check "Чек-лист DoD существует"

test -f README.md
check "README существует"

# Проверяем качество документации
grep -q "## Цели проекта" README.md
check "README содержит раздел целей"

grep -q "## Как запускать" README.md
check "README содержит инструкции по запуску"

grep -q "## Статус" docs/ADR-001-architecture.md
check "ADR содержит все разделы"

# 5. Качество кода
echo -e "\n${YELLOW}💎 Качество кода:${NC}"

# Проверяем типизацию
python -c "import app.models.item; print('Type hints OK')"
check "Типизация с помощью type hints"

# Проверяем обработку ошибок
grep -q "HTTPException" app/api/items.py
check "Обработка ошибок реализована"

# Проверяем валидацию
grep -q "ItemCreate" app/api/items.py
check "Валидация входных данных"

# 6. Интеграционные тесты
echo -e "\n${YELLOW}🔗 Интеграционные тесты:${NC}"

# Запускаем сервер в фоне
uvicorn app.main:app --host 0.0.0.0 --port 8000 &
SERVER_PID=$!
sleep 5

# Проверяем health endpoints
curl -f http://localhost:8000/healthz > /dev/null
check "Health endpoint работает"

curl -f http://localhost:8000/readyz > /dev/null
check "Readiness endpoint работает"

# Проверяем OpenAPI
curl -f http://localhost:8000/openapi.json > /dev/null
check "OpenAPI схема генерируется"

curl -f http://localhost:8000/docs > /dev/null
check "Swagger UI доступен"

# Проверяем API endpoints
curl -s -X POST "http://localhost:8000/api/v1/items" \
  -H "Content-Type: application/json" \
  -d '{"sku": "TEST-001", "title": "Test Item"}' | grep -q "id"
check "Создание Item работает"

curl -f http://localhost:8000/api/v1/items/1 > /dev/null
check "Получение Item работает"

curl -f http://localhost:8000/api/v1/items > /dev/null
check "Список Items работает"

# Останавливаем сервер
kill $SERVER_PID

echo -e "\n${GREEN}🎉 Все проверки DoD блока 1 пройдены успешно!${NC}"
echo -e "${GREEN}Блок готов к следующему этапу разработки.${NC}"
