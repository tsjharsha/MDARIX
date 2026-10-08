import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.dialects.postgresql.base import ischema_names

from backend.app.db.base import Base
from backend.app.db.models.foundation import Vector
from backend.app.db.session import database_url
from backend.app.db.tls import connect_args
from infrastructure.database.migrations.drift_policy import include_name, include_object

# The application deliberately uses a small local pgvector type wrapper.  Register it
# for PostgreSQL reflection so Alembic compares vector dimensions instead of treating
# the columns as unknown/NullType and silently skipping their type checks.
ischema_names.setdefault("vector", Vector)

config = context.config
# The control database by default; scripts/migrate_data_planes.py points the same migrations at a dedicated customer
# database (data plane) with MDARIX_MIGRATION_DATABASE_URL, so every plane has the identical, versioned schema.
_target = os.getenv("MDARIX_MIGRATION_DATABASE_URL", "").strip() or database_url().render_as_string(hide_password=False)
config.set_main_option("sqlalchemy.url", _target.replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        include_schemas=True,
        include_name=include_name,
        include_object=include_object,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=connect_args(),
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            include_name=include_name,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
