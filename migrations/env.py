"""Alembic environment for the application's configured SQLite database."""

from __future__ import annotations

from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import URL, engine_from_config, event, pool

from chore_tracker.config import get_settings

config = context.config
if config.config_file_name is not None and config.get_section("loggers") is not None:
    fileConfig(config.config_file_name)


def database_url() -> str:
    """Resolve the configured database path, creating its parent directory."""
    configured_path = config.attributes.get("database_path")
    path = Path(configured_path or get_settings().database_path).expanduser()
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return URL.create("sqlite", database=str(path)).render_as_string(
        hide_password=False
    )


config.set_main_option("sqlalchemy.url", database_url().replace("%", "%%"))

target_metadata = None


def run_migrations_offline() -> None:
    """Run migrations without creating an Engine."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        transactional_ddl=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations with SQLite foreign-key enforcement enabled."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    @event.listens_for(connectable, "connect")
    def enable_foreign_keys(
        dbapi_connection: object, _connection_record: object
    ) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            transactional_ddl=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
