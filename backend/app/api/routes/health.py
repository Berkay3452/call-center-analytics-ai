"""Sağlık uçları.

- /health        : süreç ayakta mı? (canlılık — bağımlılıklara bakmaz)
- /health/ready  : veritabanı ve Redis erişilebilir mi? (hazır olma — yük dengeleyici/compose için)
"""

import asyncio
from collections.abc import Coroutine
from typing import Any

import structlog
from fastapi import APIRouter, Request, Response, status
from redis.asyncio import Redis
from sqlalchemy import text

from app import __version__
from app.api.deps import RedisDep, SettingsDep
from app.schemas.common import ComponentState, HealthResponse, ReadinessResponse

router = APIRouter(tags=["health"])
logger = structlog.get_logger(__name__)


@router.get("/health", response_model=HealthResponse)
async def health(settings: SettingsDep) -> HealthResponse:
    return HealthResponse(status="ok", version=__version__, env=settings.app_env)


async def _check_db(request: Request) -> ComponentState:
    try:
        async with request.app.state.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return "ok"
    except Exception as exc:
        logger.warning("readiness_db_failed", error=str(exc))
        return "error"


async def _check_redis(redis: Redis) -> ComponentState:
    try:
        await redis.ping()
        return "ok"
    except Exception as exc:
        logger.warning("readiness_redis_failed", error=str(exc))
        return "error"


async def _with_timeout(
    coro: Coroutine[Any, Any, ComponentState], timeout_s: float
) -> ComponentState:
    try:
        return await asyncio.wait_for(coro, timeout=timeout_s)
    except TimeoutError:
        return "error"


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse}},
)
async def readiness(
    request: Request, response: Response, redis: RedisDep, settings: SettingsDep
) -> ReadinessResponse:
    timeout = settings.health_check_timeout_s
    db_state, redis_state = await asyncio.gather(
        _with_timeout(_check_db(request), timeout),
        _with_timeout(_check_redis(redis), timeout),
    )
    components: dict[str, ComponentState] = {"database": db_state, "redis": redis_state}
    # TODO: Embedding servisi (TEI) RAG aşamasında buraya eklenecek.
    if all(state == "ok" for state in components.values()):
        return ReadinessResponse(status="ok", components=components)
    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(status="degraded", components=components)
