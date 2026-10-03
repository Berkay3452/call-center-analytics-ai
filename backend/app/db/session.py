"""Async veritabanı motoru ve oturum yönetimi.

- API süreci: uygulama açılışında tek motor + bağlantı havuzu (lifespan'de kurulur).
- Celery işçileri: her görev kendi `asyncio.run()` döngüsünde çalışır; döngüler arası
  bağlantı paylaşımı hata verir. Bu yüzden işçilerde `null_pool=True` ile havuzsuz motor kullanılır.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import Settings


def create_engine(settings: Settings, *, null_pool: bool = False) -> AsyncEngine:
    connect_args = {"statement_cache_size": settings.db_statement_cache_size}
    if null_pool:
        return create_async_engine(
            settings.database_url,
            poolclass=NullPool,
            echo=settings.db_echo,
            connect_args=connect_args,
        )
    return create_async_engine(
        settings.database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,  # kopmuş bağlantıyı kullanmadan önce yakalar
        echo=settings.db_echo,
        connect_args=connect_args,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    # expire_on_commit=False: commit sonrası nesneler yanıtta kullanılabilir kalır.
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


@asynccontextmanager
async def worker_session(settings: Settings) -> AsyncIterator[AsyncSession]:
    """Celery görevleri için tek kullanımlık oturum (havuzsuz motor, iş bitince kapanır)."""
    engine = create_engine(settings, null_pool=True)
    try:
        async with create_session_factory(engine)() as session:
            yield session
    finally:
        await engine.dispose()
