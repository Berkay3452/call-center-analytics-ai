"""Gerçek Redis ile kayan pencere hız sınırı (#271). Yalnızca `RUN_DB_TESTS=1` iken çalışır.

Anahtarlar teste özel rastgele önekle yazılır ve test sonunda silinir; ortak Redis'e dokunulmaz.
"""

import asyncio
import os
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from redis.asyncio import Redis

from app.core.config import Settings
from app.core.ratelimit import RedisSlidingWindow

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_DB_TESTS") != "1", reason="RUN_DB_TESTS=1 değil (gerçek Redis gerekir)"
)


@pytest.fixture
async def redis() -> AsyncIterator[Redis]:
    client = Redis.from_url(Settings().redis_url, decode_responses=True)
    try:
        yield client
    finally:
        keys = [k async for k in client.scan_iter("rl-test-*")]
        if keys:
            await client.delete(*keys)
        await client.aclose()


async def test_redis_window_limits_and_reports_retry_after(redis: Redis) -> None:
    limiter = RedisSlidingWindow(lambda: redis, prefix=f"rl-test-{uuid4().hex[:8]}")
    results = [await limiter.hit("kimlik", 3, 60) for _ in range(5)]
    assert [r.allowed for r in results] == [True, True, True, False, False]
    assert 1 <= results[3].retry_after_s <= 60
    assert results[3].count == 3  # reddedilenler sayılmaz
    assert not (await limiter.peek("kimlik", 3, 60)).allowed
    assert (await limiter.hit("baska", 3, 60)).allowed


async def test_redis_window_slides(redis: Redis) -> None:
    limiter = RedisSlidingWindow(lambda: redis, prefix=f"rl-test-{uuid4().hex[:8]}")
    assert (await limiter.hit("k", 1, 1)).allowed
    assert not (await limiter.hit("k", 1, 1)).allowed
    await asyncio.sleep(1.2)
    assert (await limiter.hit("k", 1, 1)).allowed


async def test_redis_window_is_atomic_under_concurrency(redis: Redis) -> None:
    limiter = RedisSlidingWindow(lambda: redis, prefix=f"rl-test-{uuid4().hex[:8]}")
    decisions = await asyncio.gather(*[limiter.hit("k", 10, 60) for _ in range(40)])
    assert sum(d.allowed for d in decisions) == 10
