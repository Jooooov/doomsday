"""
Alembic environment configuration for Doomsday platform.
"""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Import ALL models so that Base.metadata is fully populated.
# Any model not imported here will be invisible to Alembic autogenerate.
from app.models.base import Base  # noqa: F401 — registers Base.metadata
from app.models.doomsday_clock import (  # noqa: F401
    DoomsdayScore,
    GlobalClockState,
    NewsEvent,
    RegionConfig,
    ScoreHistory,
)
from app.db.models import (  # noqa: F401 — registers profiles + checklist_cache
    StoredProfile,
    ChecklistCache,
)

# Alembic Config object
config = context.config

# Override sqlalchemy.url from environment variable if set
database_url = os.getenv("DATABASE_URL")
if database_url:
    # Alembic uses synchronous psycopg2 for migrations; strip async driver prefix
    sync_url = database_url.replace("+asyncpg", "+psycopg2")
    config.set_main_option("sqlalchemy.url", sync_url)

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (no live DB connection required)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (requires live DB connection)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
