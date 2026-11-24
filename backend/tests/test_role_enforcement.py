"""Sunucuda rol denetimi (#275): yönetici uçları tekne sahibine 403, sahip uçları yöneticiye 403.

Rol sunucuda belirlenir: `X-User-Id` yok → yönetici/servis bağlamı; `X-User-Id` → imzalı rol
(`X-User-Role`, yoksa `owner`). Rol imza mesajına dahildir; sahibin imzası `admin`e çevrilemez.
Veritabanı gerekmez: rol denetimi iş mantığından önce çalışır. Anahtarlar çalışma anında üretilir.
"""

import secrets
from typing import Any
from uuid import uuid4

import httpx
import pytest

from app.api.deps import require_admin, require_owner_id
from app.core.config import Settings
from app.core.errors import AppError, ForbiddenError
from app.core.security import CallerContext, sign_user_id
from app.domain.accounts import AccountRole
from app.domain.audit import AuditActorRole
from app.main import create_app
from app.services.audit import actor_of
from tests.conftest import TEST_SERVICE_KEY, _client_for, make_settings
from tests.test_authorization_matrix import OWNER_PREFIXES, ROUTES

KEY = secrets.token_urlsafe(32)
USER = str(uuid4())

# `/me*` ve `/auth/*` (giriş, #369) rolü belirleyen/doğrulayan uçlardır; rol denetimi dışındadır.
STAFF_ROUTES = [
    (m, p)
    for m, p in ROUTES
    if not p.startswith(OWNER_PREFIXES) and not p.startswith(("/api/v1/me", "/api/v1/auth/"))
]
OWNER_ROUTES = [(m, p) for m, p in ROUTES if p.startswith(OWNER_PREFIXES)]


def _settings() -> Settings:
    return make_settings(user_signing_key=KEY, user_signature_required=True)


def _headers(role: str | None, *, signed_role: bool | str | None = True) -> dict[str, str]:
    """Servis anahtarı + kimlik + imza. `signed_role=True` → imza `role`ü kapsar."""
    signed = role if signed_role is True else signed_role
    h = {
        "X-Service-Key": TEST_SERVICE_KEY,
        "X-User-Id": USER,
        "X-User-Signature": sign_user_id(USER, KEY, role=signed or None),
    }
    if role:
        h["X-User-Role"] = role
    return h


async def _call(method: str, path: str, headers: dict[str, str]) -> httpx.Response:
    resp: httpx.Response | None = None
    async for c in _client_for(create_app(_settings())):
        resp = await c.request(method, path, headers=headers)
    assert resp is not None
    return resp


def test_route_groups_are_not_empty() -> None:
    assert len(STAFF_ROUTES) >= 15
    assert len(OWNER_ROUTES) >= 8
    assert any(p.startswith("/api/v1/audit-log") for _, p in STAFF_ROUTES)
    assert any(p.startswith("/api/v1/crm") for _, p in STAFF_ROUTES)


@pytest.mark.parametrize(("method", "path"), STAFF_ROUTES)
async def test_owner_is_forbidden_on_every_staff_route(method: str, path: str) -> None:
    for role in (None, "owner"):
        resp = await _call(method, path, _headers(role))
        assert resp.status_code == 403, (method, path, role, resp.text[:100])
        assert resp.json()["error"]["code"] == "forbidden"


@pytest.mark.parametrize(("method", "path"), OWNER_ROUTES)
async def test_admin_identity_is_forbidden_on_owner_routes(method: str, path: str) -> None:
    resp = await _call(method, path, _headers("admin"))
    assert resp.status_code == 403, (method, path, resp.text[:100])


@pytest.mark.parametrize(("method", "path"), OWNER_ROUTES[:3])
async def test_admin_service_context_gets_400_not_data_on_owner_routes(
    method: str, path: str
) -> None:
    # Kimliksiz servis çağrısı sahip ucunda veri görmez (X-User-Id zorunlu).
    resp = await _call(method, path, {"X-Service-Key": TEST_SERVICE_KEY})
    assert resp.status_code == 400


# --- rol sahteciliği ----------------------------------------------------------------------------


async def test_owner_signature_cannot_be_upgraded_to_admin() -> None:
    # Rolsüz (sahip) imzası yakalanıp `X-User-Role: admin` eklenirse imza geçersizdir.
    h = _headers("admin", signed_role=None)
    resp = await _call("GET", "/api/v1/audit-log", h)
    assert resp.status_code == 401


async def test_signature_for_other_role_is_rejected() -> None:
    h = _headers("admin", signed_role="owner")
    assert (await _call("GET", "/api/v1/audit-log", h)).status_code == 401


async def test_role_requires_user_id() -> None:
    h = {"X-Service-Key": TEST_SERVICE_KEY, "X-User-Role": "admin"}
    assert (await _call("GET", "/api/v1/me", h)).status_code == 400


async def test_unknown_role_is_rejected() -> None:
    h = _headers("superuser")
    assert (await _call("GET", "/api/v1/me", h)).status_code == 400


async def test_signed_admin_identity_passes_auth_and_role_is_not_leaked() -> None:
    resp = await _call("GET", "/api/v1/me", _headers("admin"))
    assert resp.status_code == 200
    assert resp.json() == {"authenticated": True, "owner_id": USER}


async def test_role_header_is_case_insensitive_when_signed_consistently() -> None:
    h = _headers("Admin", signed_role="admin")
    assert (await _call("GET", "/api/v1/me", h)).status_code == 200


# --- bağımlılık birimleri -----------------------------------------------------------------------


async def test_require_admin_and_owner_units() -> None:
    admin_service = CallerContext()
    admin_user = CallerContext(owner_id=USER, role=AccountRole.ADMIN)
    owner = CallerContext(owner_id=USER, role=AccountRole.OWNER)

    assert await require_admin(admin_service) is admin_service
    assert await require_admin(admin_user) is admin_user
    with pytest.raises(ForbiddenError):
        await require_admin(owner)

    assert await require_owner_id(owner) == USER
    with pytest.raises(ForbiddenError):
        await require_owner_id(admin_user)
    with pytest.raises(AppError) as exc:
        await require_owner_id(admin_service)
    assert not isinstance(exc.value, ForbiddenError)  # 400: kimlik zorunlu


def test_audit_actor_for_admin_identity_is_not_boat_owner() -> None:
    owner_id, role = actor_of(CallerContext(owner_id=USER, role=AccountRole.ADMIN))
    assert str(owner_id) == USER and role == AuditActorRole.SERVIS
    _, owner_role = actor_of(CallerContext(owner_id=USER, role=AccountRole.OWNER))
    assert owner_role == AuditActorRole.TEKNE_SAHIBI
    assert actor_of(CallerContext()) == (None, AuditActorRole.SERVIS)


def test_helper_types() -> None:
    h: dict[str, Any] = _headers("admin")
    assert {"X-User-Role", "X-User-Signature"} <= set(h)
