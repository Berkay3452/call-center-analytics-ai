"""FastAPI giriş noktası.

Çalıştırma (backend/ klasöründen):
    uv run uvicorn app.main:app --reload
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.router import api_v1_router
from app.api.routes import health
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.core.redis import create_redis
from app.db.session import create_engine, create_session_factory

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Açılışta paylaşılan kaynakları kurar, kapanışta serbest bırakır.

    Bağlantılar tembel kurulur: veritabanı/Redis kapalı olsa bile uygulama açılır,
    durum /health/ready üzerinden görülür.
    """
    settings: Settings = app.state.settings
    app.state.engine = create_engine(settings)
    app.state.session_factory = create_session_factory(app.state.engine)
    app.state.redis = create_redis(settings.redis_url, settings.health_check_timeout_s)
    logger.info("startup", env=settings.app_env, version=__version__)
    try:
        yield
    finally:
        await app.state.redis.aclose()
        await app.state.engine.dispose()
        logger.info("shutdown")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Uygulama fabrikası. Testler kendi ayarlarıyla ayrı bir örnek oluşturabilir."""
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_json)

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        lifespan=lifespan,
        # Üretimde etkileşimli dokümantasyon kapalı.
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
    )
    app.state.settings = settings
    # Testlerde verilen ayarların bağımlılıklarda da kullanılması için.
    app.dependency_overrides[get_settings] = lambda: settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    # En dışta: request_id hata yanıtları dahil her yanıta eklenir.
    app.add_middleware(RequestContextMiddleware)

    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(api_v1_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
