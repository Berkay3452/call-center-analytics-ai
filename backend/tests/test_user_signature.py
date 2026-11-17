"""İmzalı X-User-Id, anahtar rotasyonu, threadpool ve IP giriş sınırı (#266).

Veritabanı gerekmez. Anahtarlar çalışma anında üretilir (gitleaks: sabit sır yok).
"""

import asyncio
import secrets
import threading
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx
import pytest
import structlog.testing

from app.core.config import Settings
from app.core.errors import TooManyRequestsError, UnauthorizedError
from app.core.ratelimit import InMemorySlidingWindow
from app.core.security import sign_user_id, verify_service_key, verify_user_signature
from app.main import create_app
from app.services import accounts
from app.services.accounts import enforce_login_ip_limit, record_login_failure_ip
from tests.conftest import TEST_SERVICE_KEY, _client_for, make_settings

SIGNING_KEY = secrets.token_urlsafe(32)
OWNER = str(uuid4())


def _settings(**kw: Any) -> Settings:
    base: dict[str, Any] = {"user_signing_key": SIGNING_KEY, "user_signature_required": True}
    base.update(kw)
    return make_settings(**base)


async def _get(settings: Settings, headers: dict[str, str]) -> httpx.Response:
    resp: httpx.Response | None = None
    async for c in _client_for(create_app(settings)):
        resp = await c.get("/api/v1/me", headers={"X-Service-Key": TEST_SERVICE_KEY, **headers})
    assert resp is not None
    return resp


# --- imza ---------------------------------------------------------------------------------------


async def test_valid_signature_is_accepted() -> None:
    sig = sign_user_id(OWNER, SIGNING_KEY)
    resp = await _get(_settings(), {"X-User-Id": OWNER, "X-User-Signature": sig})
    assert resp.status_code == 200


async def test_missing_signature_is_rejected_when_required() -> None:
    resp = await _get(_settings(), {"X-User-Id": OWNER})
    assert resp.status_code == 401


async def test_signature_for_other_user_is_rejected() -> None:
    sig = sign_user_id(str(uuid4()), SIGNING_KEY)
    resp = await _get(_settings(), {"X-User-Id": OWNER, "X-User-Signature": sig})
    assert resp.status_code == 401


async def test_signature_with_service_key_is_rejected() -> None:
    # İmza anahtarı servis anahtarından ayrıdır: servis anahtarıyla atılan imza geçmez.
    sig = sign_user_id(OWNER, TEST_SERVICE_KEY)
    resp = await _get(_settings(), {"X-User-Id": OWNER, "X-User-Signature": sig})
    assert resp.status_code == 401


async def test_admin_context_needs_no_signature() -> None:
    assert (await _get(_settings(), {})).status_code == 200


async def test_unsigned_id_allowed_only_when_not_required() -> None:
    resp = await _get(_settings(user_signature_required=False), {"X-User-Id": OWNER})
    assert resp.status_code == 200
    # Gönderilmiş ama bozuk imza, zorunlu olmasa da reddedilir.
    bad = await _get(
        _settings(user_signature_required=False),
        {"X-User-Id": OWNER, "X-User-Signature": "1.abc"},
    )
    assert bad.status_code == 401


@pytest.mark.parametrize("sig", ["abc", "12.", ".abc", "x1.abc", "-5.abc"])
def test_malformed_signature_is_rejected(sig: str) -> None:
    with pytest.raises(UnauthorizedError):
        verify_user_signature(OWNER, sig, _settings())


def test_expired_and_future_signatures_are_rejected() -> None:
    now = time.time()
    s = _settings()
    old = sign_user_id(OWNER, SIGNING_KEY, int(now) - 61)
    with pytest.raises(UnauthorizedError) as exc:
        verify_user_signature(OWNER, old, s, now=now)
    assert getattr(exc.value, "reason", "") == "imza_suresi_doldu"
    future = sign_user_id(OWNER, SIGNING_KEY, int(now) + 60)
    with pytest.raises(UnauthorizedError):
        verify_user_signature(OWNER, future, s, now=now)
    verify_user_signature(OWNER, sign_user_id(OWNER, SIGNING_KEY, int(now) - 30), s, now=now)


def test_signing_key_rotation_window() -> None:
    old_key = secrets.token_urlsafe(32)
    new_key = secrets.token_urlsafe(32)
    old_sig = sign_user_id(OWNER, old_key)
    active = _settings(
        user_signing_key=new_key,
        user_signing_key_previous=old_key,
        user_signing_key_previous_expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    verify_user_signature(OWNER, old_sig, active)
    verify_user_signature(OWNER, sign_user_id(OWNER, new_key), active)
    expired = _settings(
        user_signing_key=new_key,
        user_signing_key_previous=old_key,
        user_signing_key_previous_expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    with pytest.raises(UnauthorizedError):
        verify_user_signature(OWNER, old_sig, expired)


# --- servis anahtarı rotasyonu ------------------------------------------------------------------


def test_service_key_rotation_window() -> None:
    old_key = secrets.token_urlsafe(32)
    active = make_settings(
        service_api_key_previous=old_key,
        service_api_key_previous_expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    verify_service_key(old_key, active)
    verify_service_key(TEST_SERVICE_KEY, active)
    expired = make_settings(
        service_api_key_previous=old_key,
        service_api_key_previous_expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    with pytest.raises(UnauthorizedError):
        verify_service_key(old_key, expired)
    verify_service_key(TEST_SERVICE_KEY, expired)


def test_previous_key_requires_expiry() -> None:
    with pytest.raises(ValueError, match="EXPIRES_AT"):
        make_settings(service_api_key_previous=secrets.token_urlsafe(32))
    with pytest.raises(ValueError, match="EXPIRES_AT"):
        make_settings(user_signing_key_previous=secrets.token_urlsafe(32))


def test_prod_requires_separate_signing_key_and_signature() -> None:
    svc = secrets.token_urlsafe(32)
    base: dict[str, Any] = {
        "app_env": "prod",
        "service_api_key": svc,
        "audit_auth_failures": True,
        "rate_limit_backend": "memory",
    }
    with pytest.raises(ValueError, match="USER_SIGNATURE_REQUIRED"):
        make_settings(**base, user_signing_key=secrets.token_urlsafe(32))
    with pytest.raises(ValueError, match="USER_SIGNING_KEY"):
        make_settings(**base, user_signature_required=True)
    with pytest.raises(ValueError, match="USER_SIGNING_KEY"):
        make_settings(**base, user_signature_required=True, user_signing_key=svc)
    ok = make_settings(
        **base, user_signature_required=True, user_signing_key=secrets.token_urlsafe(32)
    )
    assert ok.is_production


# --- argon2 iş parçacığında ---------------------------------------------------------------------


async def test_verify_credentials_runs_hash_off_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main_thread = threading.get_ident()
    seen: list[int] = []
    real = accounts.evaluate_login

    def spy(*args: Any, **kwargs: Any) -> Any:
        seen.append(threading.get_ident())
        return real(*args, **kwargs)

    monkeypatch.setattr(accounts, "evaluate_login", spy)
    # Gerçek günlükçü ilk kullanımda önbelleğe alınır ve başka testlerin `capture_logs`'unu bozar.
    monkeypatch.setattr(accounts, "log", structlog.testing.CapturingLogger())

    class FakeSession:
        async def scalar(self, _stmt: object) -> None:
            return None

        async def flush(self) -> None:
            return None

    result = await accounts.verify_credentials(
        FakeSession(),  # type: ignore[arg-type]
        "yok",
        secrets.token_urlsafe(16),
    )
    assert not result.ok
    assert seen
    assert seen[0] != main_thread


async def test_event_loop_stays_responsive_during_hash() -> None:
    ticks = 0

    async def ticker() -> None:
        nonlocal ticks
        while True:
            await asyncio.sleep(0.005)
            ticks += 1

    task = asyncio.create_task(ticker())
    await asyncio.to_thread(accounts._verify_hash, accounts._DUMMY_HASH, "x")
    task.cancel()
    assert ticks >= 1


# --- IP giriş sınırı ----------------------------------------------------------------------------


async def test_login_ip_limit_blocks_after_budget() -> None:
    limiter = InMemorySlidingWindow()
    for _ in range(3):
        await enforce_login_ip_limit(limiter, "1.2.3.4", limit=3, window_s=60)
        await record_login_failure_ip(limiter, "1.2.3.4", limit=3, window_s=60)
    with pytest.raises(TooManyRequestsError):
        await enforce_login_ip_limit(limiter, "1.2.3.4", limit=3, window_s=60)
    # Başka IP etkilenmez; sınırlayıcı yoksa (None) geçer.
    await enforce_login_ip_limit(limiter, "5.6.7.8", limit=3, window_s=60)
    await enforce_login_ip_limit(None, "1.2.3.4", limit=3, window_s=60)


def test_empty_signing_key_never_validates() -> None:
    # `.env.example` boş USER_SIGNING_KEY ile gelir: boş anahtarla atılan imza geçmemeli.
    s = make_settings(user_signing_key="", user_signature_required=True)
    forged = sign_user_id(OWNER, "")
    with pytest.raises(Exception):  # noqa: B017 - 503 (yapılandırılmamış) beklenir
        verify_user_signature(OWNER, forged, s)
