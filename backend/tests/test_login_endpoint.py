"""Giriş ucu `POST /auth/login` (#369): rol seçimi, genel hata, sayaçlar, denetim, sınır.

Veritabanı gerekmez: hesap doğrulaması (`verify_credentials`) ve denetim yazımı sahtelenir;
gerçek karma/kilit mantığı `test_accounts*.py` içindedir.
"""

import secrets
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.api import deps
from app.api.routes import auth as auth_routes
from app.core.errors import TooManyRequestsError
from app.domain.accounts import AccountRole
from app.domain.audit import AuditAction
from app.main import create_app
from app.services.accounts import LoginFailure, LoginResult
from tests.conftest import TEST_SERVICE_KEY, _client_for, make_settings

HEADERS = {"X-Service-Key": TEST_SERVICE_KEY}
SECRET = secrets.token_urlsafe(16)
ACCOUNT_ID = uuid4()
CUSTOMER_ID = uuid4()


class _Session:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1

    async def scalar(self, _stmt: object) -> str:
        return "Ahmet Yılmaz"


class Spy:
    def __init__(self) -> None:
        self.verify_calls: list[tuple[AccountRole, str]] = []
        self.audit: list[dict[str, Any]] = []
        self.ip_hits = 0
        self.result = LoginResult(
            True, account_id=ACCOUNT_ID, role=AccountRole.OWNER, customer_id=CUSTOMER_ID
        )


@pytest.fixture
def spy(monkeypatch: pytest.MonkeyPatch) -> Spy:
    s = Spy()

    async def verify(_session: object, role: AccountRole, username: str, _password: str) -> Any:
        s.verify_calls.append((role, username))
        return s.result

    async def audit(_factory: object, **kwargs: Any) -> bool:
        s.audit.append(kwargs)
        return True

    async def hit(*_args: object, **_kwargs: object) -> None:
        s.ip_hits += 1

    monkeypatch.setattr(auth_routes, "verify_credentials", verify)
    monkeypatch.setattr(auth_routes, "record_audit_event_isolated", audit)
    monkeypatch.setattr(auth_routes, "record_login_failure_ip", hit)
    return s


@pytest.fixture
async def client(spy: Spy) -> AsyncIterator[httpx.AsyncClient]:
    app: FastAPI = create_app(make_settings())
    session = _Session()

    async def fake_session() -> AsyncIterator[_Session]:
        yield session

    app.dependency_overrides[deps.get_db_session] = fake_session
    async for c in _client_for(app):
        yield c


def body(
    role: str = "owner", username: str = "ahmet.yilmaz", password: str = SECRET
) -> dict[str, str]:
    return {"role": role, "username": username, "password": password}


async def test_owner_login_returns_identity_without_secrets(
    client: httpx.AsyncClient, spy: Spy
) -> None:
    resp = await client.post("/api/v1/auth/login", json=body(), headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data == {
        "role": "owner",
        "account_id": str(ACCOUNT_ID),
        "customer_id": str(CUSTOMER_ID),
        "display_name": "Ahmet Yılmaz",
    }
    assert SECRET not in resp.text and "hash" not in resp.text
    assert spy.verify_calls == [(AccountRole.OWNER, "ahmet.yilmaz")]
    assert spy.audit[-1]["action"] is AuditAction.GIRIS_BASARILI
    assert spy.ip_hits == 0  # başarılı giriş IP bütçesini tüketmez


async def test_admin_login_uses_admin_table_and_has_no_customer(
    client: httpx.AsyncClient, spy: Spy
) -> None:
    spy.result = LoginResult(
        True,
        account_id=ACCOUNT_ID,
        role=AccountRole.ADMIN,
        customer_id=None,
        display_name="Yönetici 1",
    )
    resp = await client.post("/api/v1/auth/login", json=body("admin", "yonetici1"), headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["customer_id"] is None and resp.json()["display_name"] == "Yönetici 1"
    assert spy.verify_calls == [(AccountRole.ADMIN, "yonetici1")]


@pytest.mark.parametrize(
    "failure",
    [
        LoginFailure.UNKNOWN_USER,
        LoginFailure.WRONG_PASSWORD,
        LoginFailure.LOCKED,
        LoginFailure.INACTIVE,
    ],
)
async def test_every_failure_returns_the_same_generic_401(
    client: httpx.AsyncClient, spy: Spy, failure: LoginFailure
) -> None:
    spy.result = LoginResult(False, failure, account_id=ACCOUNT_ID)
    resp = await client.post("/api/v1/auth/login", json=body(), headers=HEADERS)
    assert resp.status_code == 401
    assert resp.json()["error"]["message"] == auth_routes.GENERIC_LOGIN_ERROR
    assert SECRET not in resp.text
    assert spy.ip_hits == 1  # başarısız deneme IP bütçesine yazılır
    event = spy.audit[-1]
    assert event["action"] is AuditAction.GIRIS_BASARISIZ
    assert event["details"] == {"rol": "owner", "neden": failure.value}
    assert "ahmet" not in repr(event) and SECRET not in repr(event)  # ham ad/parola yazılmaz


async def test_lock_is_audited_separately_but_response_is_unchanged(
    client: httpx.AsyncClient, spy: Spy
) -> None:
    spy.result = LoginResult(
        False, LoginFailure.WRONG_PASSWORD, account_id=ACCOUNT_ID, just_locked=True
    )
    resp = await client.post("/api/v1/auth/login", json=body(), headers=HEADERS)
    assert resp.status_code == 401
    assert resp.json()["error"]["message"] == auth_routes.GENERIC_LOGIN_ERROR
    assert spy.audit[-1]["action"] is AuditAction.HESAP_KILITLENDI


async def test_login_requires_service_key(client: httpx.AsyncClient, spy: Spy) -> None:
    resp = await client.post("/api/v1/auth/login", json=body())
    assert resp.status_code == 401
    assert not spy.verify_calls  # doğrulamaya hiç girilmez


@pytest.mark.parametrize(
    "payload",
    [
        {"role": "superuser", "username": "a", "password": "b"},
        {"role": "owner", "username": "", "password": "b"},
        {"role": "owner", "username": "a", "password": ""},
        {"role": "owner", "username": "a\x00b", "password": "b"},
        {"role": "owner", "username": "a" * 101, "password": "b"},
        {"role": "owner", "username": "a", "password": "p" * 201},
        {"role": "owner", "username": "a"},
    ],
)
async def test_invalid_payload_is_422_and_never_reaches_verification(
    client: httpx.AsyncClient, spy: Spy, payload: dict[str, str]
) -> None:
    resp = await client.post("/api/v1/auth/login", json=payload, headers=HEADERS)
    assert resp.status_code == 422
    assert not spy.verify_calls


async def test_exhausted_ip_budget_gives_429_before_any_verification(
    client: httpx.AsyncClient, spy: Spy, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def blocked(*_a: object, **_k: object) -> None:
        raise TooManyRequestsError("Çok fazla başarısız giriş denemesi.", retry_after_s=30)

    monkeypatch.setattr(auth_routes, "enforce_login_ip_limit", blocked)
    resp = await client.post("/api/v1/auth/login", json=body(), headers=HEADERS)
    assert resp.status_code == 429
    assert not spy.verify_calls
