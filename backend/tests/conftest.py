"""Ortak test fikstürleri.

Testler gerçek veritabanı/Redis gerektirmez: bağlantı adresleri bilerek ulaşılamaz bir porta
yönlendirilir, böylece hazır olma (readiness) testinin "degraded" durumu deterministik olur.
"""

from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from app.core.config import Settings
from app.main import create_app

UNREACHABLE_DB = "postgresql+asyncpg://postgres:postgres@127.0.0.1:1/test"
UNREACHABLE_REDIS = "redis://127.0.0.1:1/0"


def make_settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "app_env": "test",
        "database_url": UNREACHABLE_DB,
        "redis_url": UNREACHABLE_REDIS,
        "health_check_timeout_s": 1.0,
        "supabase_url": None,
        "auth_dev_bypass": False,
    }
    base.update(overrides)
    # _env_file=None: geliştiricinin yerel .env dosyası testleri etkilemesin.
    return Settings(_env_file=None, **base)


@pytest.fixture
def settings_factory() -> Callable[..., Settings]:
    return make_settings


async def _client_for(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    # ASGITransport lifespan'i çalıştırmaz; bu yüzden elle açıp kapatıyoruz.
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    async for c in _client_for(create_app(make_settings())):
        yield c


@pytest.fixture
async def dev_client() -> AsyncIterator[httpx.AsyncClient]:
    """Kimlik doğrulaması atlanmış (AUTH_DEV_BYPASS) istemci."""
    async for c in _client_for(create_app(make_settings(auth_dev_bypass=True))):
        yield c
