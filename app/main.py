from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database.connection import create_tables
from app.middleware.logging import LoggingMiddleware
from app.middleware.idempotency import IdempotencyMiddleware
from app.api import health, items, bulk
from app.tasks.cleanup import cleanup_task_loop
# Импортируем модели для создания таблиц
from app.models import item, idempotency
import structlog
import asyncio

# Настройка логирования
logger = structlog.get_logger()

# Создание FastAPI приложения
app = FastAPI(
    title="Data Intake Service",
    description="Сервис для приёма и каталога записей",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене нужно ограничить
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Идемпотентность middleware (должен быть первым, чтобы обрабатывать запросы до логирования)
app.add_middleware(IdempotencyMiddleware)

# Логирование middleware
app.add_middleware(LoggingMiddleware)

# Подключение роутеров
app.include_router(health.router, tags=["health"])
app.include_router(items.router, prefix="/api/v1", tags=["items"])
app.include_router(bulk.router, prefix="/api/v1", tags=["bulk"])


@app.on_event("startup")
async def startup_event():
    """Инициализация при запуске"""
    logger.info("Starting Data Intake Service")
    create_tables()
    logger.info("Database tables created")
    
    # Запуск фоновой задачи очистки идемпотентности
    asyncio.create_task(cleanup_task_loop(interval_minutes=10))
    logger.info("Idempotency cleanup task started")


@app.on_event("shutdown")
async def shutdown_event():
    """Очистка при завершении"""
    logger.info("Shutting down Data Intake Service")


@app.get("/")
async def root():
    """Корневой эндпоинт"""
    return {
        "message": "Data Intake Service",
        "version": "1.0.0",
        "docs": "/docs"
    }











