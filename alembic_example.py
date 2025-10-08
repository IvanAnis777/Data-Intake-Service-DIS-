# Пример конфигурации Alembic для SQLite с batch mode

# alembic/env.py
from alembic import context
from sqlalchemy import engine_from_config, pool
from app.database.connection import Base
from app.models.item import Item  # Импортируем все модели

# Настройка для SQLite batch mode
def run_migrations_online():
    """Run migrations in 'online' mode."""
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = "sqlite:///./data_intake.db"
    
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=Base.metadata,
            # Включаем batch mode для SQLite
            render_as_batch=True,  # ← Ключевая настройка!
        )

        with context.begin_transaction():
            context.run_migrations()

# Пример миграции с batch mode
# revision = '001_add_description_to_items'
# down_revision = None

def upgrade():
    # ✅ Batch mode - работает в SQLite
    with op.batch_alter_table('items') as batch_op:
        batch_op.add_column(sa.Column('description', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('price', sa.Numeric(10, 2), nullable=True))

def downgrade():
    # ✅ Batch mode - работает в SQLite  
    with op.batch_alter_table('items') as batch_op:
        batch_op.drop_column('price')
        batch_op.drop_column('description')

# ❌ Обычная миграция - НЕ работает в SQLite
def upgrade_bad():
    op.add_column('items', sa.Column('description', sa.Text(), nullable=True))
    # SQLite не поддерживает ADD COLUMN с ограничениями

# ❌ Еще хуже - НЕ работает в SQLite
def upgrade_worse():
    op.drop_column('items', 'old_field')  # SQLite не поддерживает DROP COLUMN
