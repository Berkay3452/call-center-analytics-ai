"""Alembic ortamı: async SQLAlchemy ile migration çalıştırır.

Bağlantı adresi öncelik sırasıyla: `-x url=...` komut satırı argümanı, yoksa .env'deki
DATABASE_URL (`app.core.config`). Şemanın kaynağı `app.db.models` paketindeki modellerdir.
"""

import asyncio
from logging.config import fileConfig
from typing import Any, Literal

from alembic import context
from alembic.autogenerate.api import AutogenContext
from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, pool
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.types import TypeEngine

from app.core.config import get_settings
from app.db.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def database_url() -> str:
    return context.get_x_argument(as_dictionary=True).get("url") or get_settings().database_url


def compare_type(
    ctx: Any,
    inspected_column: Column[Any],
    metadata_column: Column[Any],
    inspected_type: TypeEngine[Any],
    metadata_type: TypeEngine[Any],
) -> bool | None:
    """pgvector ve tsvector tipleri yansıtmada tam tanınmayabilir; yanlış 'fark' üretmesin."""
    if isinstance(metadata_type, Vector | TSVECTOR):
        return False
    return None  # diğer tiplerde Alembic'in varsayılan karşılaştırması


def render_item(type_: str, obj: Any, autogen_context: AutogenContext) -> str | Literal[False]:
    """Migration dosyasında pgvector tipini okunur ve içe aktarılmış biçimde yazar."""
    if type_ == "type" and isinstance(obj, Vector):
        autogen_context.imports.add("from pgvector.sqlalchemy import Vector")
        return f"Vector({obj.dim})"
    return False


def _configure(**kwargs: Any) -> None:
    context.configure(
        target_metadata=target_metadata,
        compare_type=compare_type,
        render_item=render_item,
        **kwargs,
    )


def run_migrations_offline() -> None:
    """Veritabanına bağlanmadan SQL üretir (`alembic upgrade head --sql`)."""
    _configure(url=database_url(), literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def _run(connection: Connection) -> None:
    _configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    settings = get_settings()
    engine = create_async_engine(
        database_url(),
        poolclass=pool.NullPool,
        # Supabase pooler arkasında hazır ifade önbelleği kapalı olmalı (bkz. session.py).
        connect_args={"statement_cache_size": settings.db_statement_cache_size},
    )
    async with engine.connect() as connection:
        await connection.run_sync(_run)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
