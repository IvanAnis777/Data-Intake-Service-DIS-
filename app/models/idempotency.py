from sqlalchemy import Column, Integer, String, Text, DateTime, Index
from sqlalchemy.sql import func
from datetime import datetime, timedelta
from app.database.connection import Base


class IdempotencyKey(Base):
    """SQLAlchemy модель для ключей идемпотентности"""
    __tablename__ = "idempotency_keys"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    key = Column(String(255), unique=True, index=True, nullable=False)
    request_hash = Column(String(64), nullable=False)  # SHA-256 hash
    status = Column(String(20), nullable=False, default='processing')  # processing, completed
    response_status_code = Column(Integer, nullable=True)
    response_body = Column(Text, nullable=True)  # JSON response
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    
    # Индексы для производительности
    __table_args__ = (
        Index('idx_idempotency_key_unique', 'key', unique=True),
        Index('idx_idempotency_expires_at', 'expires_at'),
    )
    
    def __repr__(self):
        return f"<IdempotencyKey(key='{self.key}', status='{self.status}')>"
    
    @classmethod
    def create_with_ttl(cls, key: str, request_hash: str, ttl_seconds: int = 3600):
        """Создать ключ идемпотентности с TTL"""
        expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)
        return cls(
            key=key,
            request_hash=request_hash,
            status='processing',
            expires_at=expires_at
        )
    
    def mark_completed(self, status_code: int, response_body: str):
        """Отметить ключ как завершённый"""
        # Обновляем атрибуты напрямую
        object.__setattr__(self, 'status', 'completed')
        object.__setattr__(self, 'response_status_code', status_code)
        object.__setattr__(self, 'response_body', response_body)
        object.__setattr__(self, 'completed_at', datetime.utcnow())
    
    def is_expired(self) -> bool:
        """Проверить, истёк ли ключ"""
        return bool(datetime.utcnow() > self.expires_at)
