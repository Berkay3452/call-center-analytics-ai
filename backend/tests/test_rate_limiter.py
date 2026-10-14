"""LLM hız sınırlayıcısı testleri (sahte saat; gerçekten beklenmez)."""

from collections.abc import Callable

import pytest

from app.agents.call_classifier import CallClassifierAgent
from app.core.config import Settings
from app.llm.client import RateLimiter
from tests.llm_fakes import scripted
from tests.test_agents import CLASSIFICATION_JSON, tuzla_ctx


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def make_limiter(per_minute: int) -> tuple[RateLimiter, FakeClock]:
    clock = FakeClock()
    return RateLimiter(per_minute, clock=clock, sleep=clock.sleep), clock


async def test_requests_under_limit_do_not_wait() -> None:
    limiter, clock = make_limiter(3)

    for _ in range(3):
        assert await limiter.acquire("model-a") == 0
    assert clock.sleeps == []


async def test_request_over_limit_waits_until_oldest_leaves_window() -> None:
    limiter, clock = make_limiter(2)
    await limiter.acquire("model-a")  # t=0
    clock.now = 10
    await limiter.acquire("model-a")  # t=10

    clock.now = 15
    waited = await limiter.acquire("model-a")

    assert waited == pytest.approx(45)  # t=0'daki istek t=60'ta pencereden çıkar
    assert clock.now == pytest.approx(60)


async def test_limits_are_per_model() -> None:
    limiter, clock = make_limiter(1)
    await limiter.acquire("hizli")

    assert await limiter.acquire("guclu") == 0
    assert clock.sleeps == []


async def test_zero_means_unlimited() -> None:
    limiter, clock = make_limiter(0)

    for _ in range(100):
        await limiter.acquire("model-a")
    assert clock.sleeps == []


async def test_agent_acquires_rate_limit_before_calling_llm(
    settings_factory: Callable[..., Settings], monkeypatch: pytest.MonkeyPatch
) -> None:
    keys: list[str] = []

    class SpyLimiter:
        async def acquire(self, key: str) -> float:
            keys.append(key)
            return 0.0

    monkeypatch.setattr("app.agents.llm_agent.llm_rate_limiter", lambda settings: SpyLimiter())
    agent = CallClassifierAgent(settings=settings_factory(), model=scripted(CLASSIFICATION_JSON))

    result = await agent.run(tuzla_ctx())

    assert result.status == "ok"
    assert keys == ["sahte-model"]  # sınır model adına göre tutulur
