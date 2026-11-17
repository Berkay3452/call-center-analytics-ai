"""Kayan pencere hız sınırı (#271).

İki uygulama aynı arayüzü sağlar:
- `RedisSlidingWindow`: Redis sıralı kümesi + tek Lua betiği (atomik). Çok süreçli/çok örnekli
  canlı ortam için varsayılandır.
- `InMemorySlidingWindow`: tek süreç içi; testler ve Redis'siz yerel çalışma içindir.

Redis erişilemezse **açık kalır** (fail-open): istek sınırlanmadan geçer ve uyarı günlüğe yazılır.
Gerekçe: hız sınırı bir koruma katmanıdır, Redis'in kapalı olması tüm arayüzü kapatmamalıdır.
Redis'siz ortamda sınırın uygulanmadığı `RATE_LIMIT_BACKEND=off|memory` ile açıkça seçilebilir.
"""

import time
import uuid
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

import structlog
from redis.asyncio import Redis

log = structlog.get_logger(__name__)

# KEYS[1]=anahtar, ARGV: şimdi(ms), pencere(ms), sınır, üye, yalnız-bak(1/0)
_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
local count = redis.call('ZCARD', key)
if count >= limit then
  local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
  return {0, count, tonumber(oldest[2])}
end
if ARGV[5] == '1' then
  return {1, count, 0}
end
redis.call('ZADD', key, now, ARGV[4])
redis.call('PEXPIRE', key, window)
return {1, count + 1, 0}
"""


@dataclass(frozen=True)
class Decision:
    allowed: bool
    limit: int
    count: int
    retry_after_s: int = 0

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.count)


class RateLimiter(Protocol):
    async def hit(self, key: str, limit: int, window_s: int) -> Decision:
        """Bir istek sayar; sınır aşıldıysa saymaz ve `allowed=False` döner."""
        ...

    async def peek(self, key: str, limit: int, window_s: int) -> Decision:
        """Saymadan durumu okur (engelli mi?)."""
        ...


def _retry_after(oldest_ms: float, now_ms: int, window_ms: int) -> int:
    return max(1, -(-int(oldest_ms + window_ms - now_ms) // 1000))  # yukarı yuvarla


class RedisSlidingWindow:
    def __init__(self, get_redis: Callable[[], Redis], prefix: str = "rl") -> None:
        self._get_redis = get_redis
        self._prefix = prefix

    async def _run(self, key: str, limit: int, window_s: int, *, peek: bool) -> Decision:
        now_ms = time.time_ns() // 1_000_000
        window_ms = window_s * 1000
        try:
            redis = self._get_redis()
            raw: Any = await redis.eval(  # type: ignore[misc]
                _LUA,
                1,
                f"{self._prefix}:{key}",
                str(now_ms),
                str(window_ms),
                str(limit),
                f"{now_ms}-{uuid.uuid4().hex[:8]}",
                "1" if peek else "0",
            )
        except Exception as exc:  # Redis kapalı/yavaş: fail-open
            log.warning("ratelimit.redis_unavailable", error=type(exc).__name__)
            return Decision(True, limit, 0)
        allowed, count, oldest = int(raw[0]), int(raw[1]), float(raw[2])
        if allowed:
            return Decision(True, limit, count)
        return Decision(False, limit, count, _retry_after(oldest, now_ms, window_ms))

    async def hit(self, key: str, limit: int, window_s: int) -> Decision:
        return await self._run(key, limit, window_s, peek=False)

    async def peek(self, key: str, limit: int, window_s: int) -> Decision:
        return await self._run(key, limit, window_s, peek=True)


class InMemorySlidingWindow:
    """Tek süreçli uygulama (asyncio tek iş parçacığında çalıştığı için kilit gerekmez)."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def _decide(self, key: str, limit: int, window_s: int, *, count_it: bool) -> Decision:
        now = self._clock()
        hits = self._hits[key]
        while hits and hits[0] <= now - window_s:
            hits.popleft()
        if len(hits) >= limit:
            return Decision(False, limit, len(hits), max(1, int(hits[0] + window_s - now) + 1))
        if count_it:
            hits.append(now)
        if not hits:
            self._hits.pop(key, None)  # boş anahtarlar birikmesin
        return Decision(True, limit, len(hits))

    async def hit(self, key: str, limit: int, window_s: int) -> Decision:
        return self._decide(key, limit, window_s, count_it=True)

    async def peek(self, key: str, limit: int, window_s: int) -> Decision:
        return self._decide(key, limit, window_s, count_it=False)
