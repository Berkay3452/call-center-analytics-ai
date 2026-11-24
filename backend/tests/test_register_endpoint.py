"""Kaydol ucu `POST /auth/register` (#382): doğrulama, yinelenen e-posta, sınır, denetim.

Veritabanı gerekmez: `register_owner` ve denetim yazımı sahtelenir; gerçek müşteri + hesap yazımı
`test_accounts_integration.py` içinde gerçek veritabanıyla denenir.
"""

import secrets
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.api import deps
from app.api.routes import auth as auth_routes
from app.core.ratelimit import InMemorySlidingWindow
from app.domain.audit import AuditAction
from app.main import create_app
from app.services.accounts import EmailTakenError
from tests.conftest import TEST_SERVICE_KEY, _client_for, make_settings

HEADERS = {"X-Service-Key": TEST_SERVICE_KEY}
PASSWORD = secrets.token_urlsafe(16)
ACCOUNT_ID, CUSTOMER_ID = uuid4(), uuid4()


class _Session:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class Spy:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.audit: list[dict[str, Any]] = []
        self.taken = False
        self.session = _Session()


@pytest.fixture
def spy(monkeypatch: pytest.MonkeyPatch) -> Spy:
    s = Spy()

    async def register(_session: object, **kwargs: Any) -> Any:
        s.calls.append(kwargs)
        if s.taken:
            raise EmailTakenError
        return (
            SimpleNamespace(id=ACCOUNT_ID),
            SimpleNamespace(id=CUSTOMER_ID, full_name=kwargs["full_name"]),
        )

    async def audit(_factory: object, **kwargs: Any) -> bool:
        s.audit.append(kwargs)
        return True

    monkeypatch.setattr(auth_routes, "register_owner", register)
    monkeypatch.setattr(auth_routes, "record_audit_event_isolated", audit)
    return s


@pytest.fixture
async def client(spy: Spy) -> AsyncIterator[httpx.AsyncClient]:
    app: FastAPI = create_app(make_settings())
    app.state.rate_limiter = InMemorySlidingWindow()

    async def fake_session() -> AsyncIterator[_Session]:
        yield spy.session

    app.dependency_overrides[deps.get_db_session] = fake_session
    async for c in _client_for(app):
        yield c


def payload(**over: str) -> dict[str, str]:
    data = {
        "first_name": " Ayşe ",
        "last_name": "Demir",
        "phone": "0532 123 45 67",
        "email": " Ayse.Demir@Example.com ",
        "password": PASSWORD,
        "password_confirm": PASSWORD,
    }
    data.update(over)
    return data


async def test_register_creates_owner_and_normalizes_input(
    client: httpx.AsyncClient, spy: Spy
) -> None:
    resp = await client.post("/api/v1/auth/register", json=payload(), headers=HEADERS)
    assert resp.status_code == 201
    assert resp.json() == {
        "role": "owner",
        "account_id": str(ACCOUNT_ID),
        "customer_id": str(CUSTOMER_ID),
        "display_name": "Ayşe Demir",
    }
    assert PASSWORD not in resp.text and "hash" not in resp.text
    assert spy.calls == [
        {
            "full_name": "Ayşe Demir",
            "phone": "+905321234567",
            "email": "ayse.demir@example.com",
            "password": PASSWORD,
        }
    ]
    assert spy.session.commits == 1
    assert spy.audit[-1]["action"] is AuditAction.HESAP_OLUSTURULDU
    assert PASSWORD not in str(spy.audit) and "example.com" not in str(spy.audit)


async def test_duplicate_email_is_conflict_with_generic_message(
    client: httpx.AsyncClient, spy: Spy
) -> None:
    spy.taken = True
    resp = await client.post("/api/v1/auth/register", json=payload(), headers=HEADERS)
    assert resp.status_code == 409
    assert resp.json()["error"]["message"] == auth_routes.REGISTER_ERROR
    assert spy.session.rollbacks == 1 and spy.session.commits == 0
    assert spy.audit == []


@pytest.mark.parametrize(
    "over",
    [
        {"password_confirm": "baska-bir-parola-123"},
        {"password": "kisa", "password_confirm": "kisa"},
        {"email": "gecersiz"},
        {"email": "a@b"},
        {"phone": "12345"},
        {"phone": "0212 123 45 67"},
        {"first_name": "   "},
        {"last_name": ""},
        {"password": "x" * 201, "password_confirm": "x" * 201},
        {"first_name": "Ay\x00şe"},
    ],
)
async def test_invalid_input_is_422_and_never_reaches_service(
    client: httpx.AsyncClient, spy: Spy, over: dict[str, str]
) -> None:
    resp = await client.post("/api/v1/auth/register", json=payload(**over), headers=HEADERS)
    assert resp.status_code == 422
    assert spy.calls == []


@pytest.mark.parametrize(
    "phone", ["+90 532 123 45 67", "05321234567", "5321234567", "(0532) 123-45-67"]
)
async def test_phone_formats_are_normalized(
    client: httpx.AsyncClient, spy: Spy, phone: str
) -> None:
    resp = await client.post("/api/v1/auth/register", json=payload(phone=phone), headers=HEADERS)
    assert resp.status_code == 201
    assert spy.calls[-1]["phone"] == "+905321234567"


async def test_weak_password_is_rejected_by_policy(
    client: httpx.AsyncClient, spy: Spy, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def weak(_session: object, **_kwargs: Any) -> Any:
        raise auth_routes.PasswordPolicyError("Parola en az 12 karakter olmalı.")

    monkeypatch.setattr(auth_routes, "register_owner", weak)
    resp = await client.post(
        "/api/v1/auth/register",
        json=payload(password="kisa", password_confirm="kisa"),
        headers=HEADERS,
    )
    assert resp.status_code == 409
    assert "12 karakter" in resp.json()["error"]["message"]


async def test_register_requires_service_key(client: httpx.AsyncClient, spy: Spy) -> None:
    resp = await client.post("/api/v1/auth/register", json=payload())
    assert resp.status_code == 401
    assert spy.calls == []


async def test_ip_registration_budget_returns_429(client: httpx.AsyncClient, spy: Spy) -> None:
    codes = [
        (await client.post("/api/v1/auth/register", json=payload(), headers=HEADERS)).status_code
        for _ in range(auth_routes.REGISTER_PER_HOUR + 2)
    ]
    assert codes[: auth_routes.REGISTER_PER_HOUR] == [201] * auth_routes.REGISTER_PER_HOUR
    assert codes[-1] == 429


async def test_client_cannot_choose_role_or_customer(client: httpx.AsyncClient, spy: Spy) -> None:
    resp = await client.post(
        "/api/v1/auth/register",
        json=payload(role="admin", customer_id=str(uuid4())),
        headers=HEADERS,
    )
    assert resp.status_code == 201
    assert set(spy.calls[-1]) == {"full_name", "phone", "email", "password"}
