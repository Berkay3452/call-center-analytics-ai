"""İmzalı `X-User-Id` saldırıları (OWASP API2, API1; #266): servis anahtarını ele geçiren biri bile
imza anahtarı olmadan başka bir sahip adına konuşamaz.

Veritabanı gerekmez: imza doğrulaması iş mantığından önce çalışır.
Anahtarlar çalışma anında üretilir.
"""

import secrets
import time
from collections.abc import AsyncIterator

import httpx
import pytest

from app.core.security import sign_user_id
from tests.conftest import TEST_SERVICE_KEY, make_settings
from tests.security.helpers import OWNER_A, OWNER_B, client_for

SIGNING_KEY = secrets.token_urlsafe(32)
PATHS = ["/api/v1/me", "/api/v1/assistant/sessions", "/api/v1/chat/sessions"]


def _headers(owner: str, signature: str | None) -> dict[str, str]:
    h = {"X-Service-Key": TEST_SERVICE_KEY, "X-User-Id": owner}
    if signature is not None:
        h["X-User-Signature"] = signature
    return h


def _forged() -> dict[str, str | None]:
    now = int(time.time())
    good = sign_user_id(OWNER_A, SIGNING_KEY, now)
    ts, _, mac = good.partition(".")
    other_key = secrets.token_urlsafe(32)
    flipped = mac[:-1] + ("0" if mac[-1] != "0" else "1")
    return {
        "eksik": None,
        "bos": "",
        "baska_sahibin_imzasi": sign_user_id(OWNER_B, SIGNING_KEY, now),
        "yanlis_anahtar": sign_user_id(OWNER_A, other_key, now),
        "servis_anahtariyla_imza": sign_user_id(OWNER_A, TEST_SERVICE_KEY, now),
        "mac_bozuk": f"{ts}.{flipped}",
        "zaman_damgasi_degistirildi": f"{now + 1}.{mac}",
        "suresi_dolmus": sign_user_id(OWNER_A, SIGNING_KEY, now - 86_400),
        "gelecek": sign_user_id(OWNER_A, SIGNING_KEY, now + 86_400),
        "bos_mac": f"{ts}.",
        "sadece_mac": mac,
        "harf_zaman": f"abc.{mac}",
        "sql": "' OR '1'='1",
        "uzun": "9" * 5000,
    }


FORGED = _forged()


@pytest.fixture
async def signed_client() -> AsyncIterator[httpx.AsyncClient]:
    settings = make_settings(user_signing_key=SIGNING_KEY, user_signature_required=True)
    async for c in client_for(settings):
        yield c


@pytest.mark.parametrize("kind", list(FORGED))
@pytest.mark.parametrize("path", PATHS)
async def test_forged_signature_is_rejected(
    signed_client: httpx.AsyncClient, path: str, kind: str
) -> None:
    resp = await signed_client.get(path, headers=_headers(OWNER_A, FORGED[kind]))

    assert resp.status_code == 401, (path, kind, resp.text[:100])
    assert SIGNING_KEY not in resp.text and TEST_SERVICE_KEY not in resp.text


async def test_valid_signature_is_accepted_only_for_its_own_owner(
    signed_client: httpx.AsyncClient,
) -> None:
    sig = sign_user_id(OWNER_A, SIGNING_KEY)

    assert (
        await signed_client.get("/api/v1/me", headers=_headers(OWNER_A, sig))
    ).status_code == 200
    # Aynı imza başka sahip kimliğiyle yeniden oynatılamaz (kimlik imzanın parçasıdır).
    replay = await signed_client.get("/api/v1/me", headers=_headers(OWNER_B, sig))
    assert replay.status_code == 401


async def test_signature_in_query_or_cookie_is_not_accepted(
    signed_client: httpx.AsyncClient,
) -> None:
    sig = sign_user_id(OWNER_A, SIGNING_KEY)
    headers = {"X-Service-Key": TEST_SERVICE_KEY, "X-User-Id": OWNER_A}

    by_query = await signed_client.get(f"/api/v1/me?X-User-Signature={sig}", headers=headers)
    by_cookie = await signed_client.get(
        "/api/v1/me", headers={**headers, "Cookie": f"X-User-Signature={sig}"}
    )

    assert by_query.status_code == by_cookie.status_code == 401


async def test_stolen_service_key_alone_cannot_impersonate_any_owner(
    signed_client: httpx.AsyncClient,
) -> None:
    for owner in (OWNER_A, OWNER_B):
        resp = await signed_client.get("/api/v1/chat/sessions", headers=_headers(owner, None))
        assert resp.status_code == 401


@pytest.mark.parametrize("claimed", ["admin", "ADMIN", " admin ", "staff", "root", "owner,admin"])
@pytest.mark.parametrize("path", ["/api/v1/audit-log", "/api/v1/calls", "/api/v1/service-orders"])
async def test_stolen_owner_signature_cannot_be_upgraded_to_a_staff_role(
    signed_client: httpx.AsyncClient, path: str, claimed: str
) -> None:
    """Yetki yükseltme (#275): sahibin imzası `X-User-Role` eklenerek yönetici yapılamaz."""
    headers = {**_headers(OWNER_A, sign_user_id(OWNER_A, SIGNING_KEY)), "X-User-Role": claimed}

    resp = await signed_client.get(path, headers=headers)

    assert resp.status_code in {400, 401, 403}, (path, claimed, resp.status_code)
