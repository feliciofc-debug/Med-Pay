"""Configuração do Alembic.

- Lê `DATABASE_URL` da configuração da aplicação (variável de ambiente)
- Converte de asyncpg → psycopg2 para o Alembic (que é síncrono por padrão)
- Importa Base + todos os models para o autogenerate funcionar
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.core.database import Base

# Importa TODOS os models para que o Alembic descubra todas as tabelas.
# (o app.models.__init__ já importa todos)
import app.models  # noqa: F401

# Configuração do Alembic (alembic.ini)
config = context.config

# Logging do alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _get_sync_database_url() -> str:
    """Converte URL asyncpg para psycopg2 (Alembic não usa asyncpg)."""
    url = settings.DATABASE_URL
    return url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")


# Sobrescreve a URL do alembic.ini com a do .env
config.set_main_option("sqlalchemy.url", _get_sync_database_url())

# Metadata-alvo para autogenerate
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Roda migrations sem conexão (gera SQL bruto).

    Útil para revisar antes de aplicar em produção.
    """
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
    """Roda migrations conectado ao banco."""
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
