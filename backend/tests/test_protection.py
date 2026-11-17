"""Koruma katmanı testleri (#271): hız sınırı, gövde sınırı, güvenlik başlıkları, hata iletileri.

Redis gerekmez: sınır mantığı bellek içi uygulamayla, Redis uygulaması ise erişilemeyen bir
sunucuyla (fail-open davranışı) denenir. Gerçek Redis testi: `test_protection_redis.py`.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest
from redis.asyncio import Redis

from app.core.public_errors import UNEXPECTED, analysis_error, stt_error
from app.core.ratelimit import InMemorySlidingWindow, RedisSlidingWindow
from app.main import create_app
from tests.conftest import TEST_SERVICE_KEY, make_settings

OWNER_A = "11111111-1111-4111-8111-111111111111"
OWNER_B = "22222222-2222-4222-8222-222222222222"
HEADERS = {"X-Service-Key": TEST_SERVICE_KEY}


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


async def test_sliding_window_counts_and_expires() -> None:
    clock = Clock()
    limiter = InMemorySlidingWindow(clock=clock)
    for _ in range(3):
        assert (await limiter.hit("k", 3, 60)).allowed
    blocked = await limiter.hit("k", 3, 60)
    assert not blocked.allowed and blocked.count == 3 and 1 <= blocked.retry_after_s <= 61
    # Reddedilen istek sayılmaz; pencere kayınca yeniden izin verilir.
    clock.now += 61
    assert (await limiter.hit("k", 3, 60)).allowed


async def test_sliding_window_is_per_key_and_peek_does_not_count() -> None:
    limiter = InMemorySlidingWindow(clock=Clock())
    assert (await limiter.hit("a", 1, 60)).allowed
    assert not (await limiter.hit("a", 1, 60)).allowed
    assert (await limiter.hit("b", 1, 60)).allowed
    assert (await limiter.peek("c", 1, 60)).allowed
    assert (await limiter.peek("c", 1, 60)).allowed  # bakmak saymaz
    assert (await limiter.hit("c", 1, 60)).allowed
    assert not (await limiter.peek("c", 1, 60)).allowed


async def test_redis_limiter_fails_open_when_redis_is_down() -> None:
    dead = Redis.from_url("redis://127.0.0.1:1/0", socket_connect_timeout=0.3)
    limiter = RedisSlidingWindow(lambda: dead)
    decision = await limiter.hit("k", 1, 60)
    assert decision.allowed  # Redis yokken istekler sınırlanmaz (belgelenen davranış)
    await dead.aclose()


@asynccontextmanager
async def _client(**overrides: Any) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(make_settings(rate_limit_backend="memory", **overrides))
    # ASGITransport lifespan'i çalıştırmaz; veritabanı/Redis nesneleri için elle açıyoruz.
    async with app.router.lifespan_context(app):
        # Veritabanı kapalıyken uç noktalar 500 döner; istemciye istisna fırlatılmasın.
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@pytest.fixture
async def limited() -> AsyncIterator[httpx.AsyncClient]:
    async with _client(rate_limit_general_per_min=3, rate_limit_assistant_per_min=2) as c:
        yield c


async def test_general_limit_returns_429_with_retry_after(limited: httpx.AsyncClient) -> None:
    for _ in range(3):
        assert (await limited.get("/api/v1/me", headers=HEADERS)).status_code == 200
    resp = await limited.get("/api/v1/me", headers={**HEADERS, "X-Request-ID": "rl-1"})
    assert resp.status_code == 429
    assert int(resp.headers["retry-after"]) >= 1
    assert resp.headers["x-ratelimit-remaining"] == "0"
    body = resp.json()["error"]
    assert body["code"] == "rate_limited"
    assert body["request_id"] == "rl-1" and resp.headers["x-request-id"] == "rl-1"
    assert body["details"]["retry_after_s"] >= 1


async def test_limit_is_per_identity_and_health_is_exempt(limited: httpx.AsyncClient) -> None:
    for _ in range(3):
        await limited.get("/api/v1/me", headers={**HEADERS, "X-User-Id": OWNER_A})
    assert (
        await limited.get("/api/v1/me", headers={**HEADERS, "X-User-Id": OWNER_A})
    ).status_code == 429
    # Başka kimlik kendi kovasını kullanır.
    assert (
        await limited.get("/api/v1/me", headers={**HEADERS, "X-User-Id": OWNER_B})
    ).status_code == 200
    for _ in range(10):
        assert (await limited.get("/health")).status_code == 200
        assert (await limited.options("/api/v1/me")).status_code != 429


async def test_assistant_endpoints_have_tighter_limit() -> None:
    async with _client(rate_limit_general_per_min=100, rate_limit_assistant_per_min=2) as c:
        headers = {**HEADERS, "X-User-Id": OWNER_A}
        codes = [
            (await c.post("/api/v1/chat/messages", json={"question": "selam"}, headers=headers))
            for _ in range(3)
        ]
        assert codes[2].status_code == 429
        assert codes[2].json()["error"]["details"]["bucket"] == "asistan"
        # Asistan dışı uçlar etkilenmez.
        assert (await c.get("/api/v1/me", headers=headers)).status_code == 200


async def test_repeated_auth_failures_are_throttled_per_ip() -> None:
    async with _client(rate_limit_auth_fail_per_min=3, rate_limit_general_per_min=100) as c:
        statuses = [(await c.get("/api/v1/me", headers={"X-Service-Key": "yanlis"})).status_code]
        statuses += [
            (await c.get("/api/v1/me", headers={"X-Service-Key": "yanlis"})).status_code
            for _ in range(4)
        ]
        assert statuses[:3] == [401, 401, 401]
        assert statuses[3:] == [429, 429]
        # Engelli IP doğru anahtarla da bir süre içeri alınmaz (kaba kuvvet koruması).
        blocked = await c.get("/api/v1/me", headers=HEADERS)
        assert blocked.status_code == 429 and int(blocked.headers["retry-after"]) >= 1


async def test_rate_limit_off_does_not_limit() -> None:
    app = create_app(make_settings(rate_limit_backend="off", rate_limit_general_per_min=1))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        for _ in range(5):
            assert (await c.get("/api/v1/me", headers=HEADERS)).status_code == 200


async def test_json_body_over_limit_is_rejected_with_413() -> None:
    async with _client(max_json_body_kb=1) as c:
        big = {"question": "a" * 2048}
        resp = await c.post(
            "/api/v1/chat/messages", json=big, headers={**HEADERS, "X-User-Id": OWNER_A}
        )
        assert resp.status_code == 413
        assert resp.json()["error"]["code"] == "payload_too_large"
        small = await c.post("/api/v1/chat/messages", json={"question": "selam"}, headers=HEADERS)
        assert small.status_code != 413


async def test_chunked_json_body_over_limit_is_rejected_with_413() -> None:
    async with _client(max_json_body_kb=1) as c:

        async def chunks() -> AsyncIterator[bytes]:
            for _ in range(8):
                yield b'{"question": "' + b"a" * 400 + b'"}'

        resp = await c.post(
            "/api/v1/chat/messages",
            content=chunks(),  # Content-Length yok (chunked)
            headers={**HEADERS, "X-User-Id": OWNER_A, "Content-Type": "application/json"},
        )
        assert resp.status_code == 413
        assert resp.json()["error"]["code"] == "payload_too_large"


async def test_multipart_upload_is_not_limited_by_json_cap() -> None:
    async with _client(max_json_body_kb=1) as c:
        resp = await c.post(
            "/api/v1/calls/audio",
            files={"file": ("a.wav", b"RIFF" + b"\0" * 4096, "audio/wav")},
            headers=HEADERS,
        )
        # started_at eksik → doğrulama hatası; 413 değil (ses kendi sınırına sahiptir).
        assert resp.status_code == 422


async def test_security_headers_on_api_responses(limited: httpx.AsyncClient) -> None:
    resp = await limited.get("/api/v1/me", headers=HEADERS)
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["referrer-policy"] == "no-referrer"
    assert resp.headers["x-frame-options"] == "DENY"
    assert "strict-transport-security" not in resp.headers  # yerelde http
    throttled = [await limited.get("/api/v1/me", headers=HEADERS) for _ in range(3)][-1]
    assert throttled.status_code == 429
    assert throttled.headers["x-content-type-options"] == "nosniff"


async def test_hsts_only_in_production() -> None:
    app = create_app(
        make_settings(
            app_env="prod",
            service_api_key="x" * 40,
            audit_auth_failures=True,
            rate_limit_backend="memory",
        )
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        resp = await c.get("/health")
        assert "max-age=" in resp.headers["strict-transport-security"]


def test_public_error_messages_hide_raw_details() -> None:
    class Run:
        def __init__(self, agent: str, status: str, kind: str | None) -> None:
            self.agent, self.status, self.error_kind = agent, status, kind

    runs = [Run("call_classifier", "failed", "runtime"), Run("summarizer", "ok", None)]
    msg = analysis_error(runs)
    assert "call_classifier: servis hatası" in msg and "summarizer" not in msg
    assert "Traceback" not in msg and "Error" not in msg

    assert stt_error("Seste konuşma bulunamadı.", transient=False).endswith("bulunamadı.")
    leaked = "HTTP 401 invalid_api_key sk-LEAK from api.example.com"
    for transient in (True, False):
        assert "sk-LEAK" not in stt_error(leaked, transient=transient)
        assert "invalid_api_key" not in stt_error(leaked, transient=transient)
    assert UNEXPECTED.startswith("Beklenmeyen")
