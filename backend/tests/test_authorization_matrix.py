"""Yetki matrisi (#158): HER `/api/v1` ucu servis anahtarı ister; tekne sahibi uçları ayrıca
geçerli `X-User-Id` ister. Yeni bir uç eklenip kimlik doğrulaması unutulursa bu test kırılır.

Veritabanı gerekmez: kimlik doğrulaması iş mantığından önce çalışır ve reddedilen istek ona ulaşmaz.
"""

import re
from uuid import uuid4

import httpx
import pytest

from app.main import create_app
from tests.conftest import TEST_SERVICE_KEY, _client_for, make_settings

# Yalnızca tekne sahibi oturumuna bağlı uçlar (admin uçlarında X-User-Id isteğe bağlıdır).
OWNER_PREFIXES = ("/api/v1/chat", "/api/v1/assistant")
OWNER_ID = str(uuid4())


def api_routes() -> list[tuple[str, str]]:
    """(yöntem, örnek yol) çiftleri; yol parametreleri geçerli UUID ile doldurulur.

    Yollar OpenAPI belgesinden okunur (FastAPI yönlendiricileri iç içe olduğundan `app.routes`
    düz liste vermez).
    """
    out: list[tuple[str, str]] = []
    for template, methods in create_app(make_settings()).openapi()["paths"].items():
        path = re.sub(r"\{[^}]+\}", str(uuid4()), template)
        if not path.startswith("/api/v1"):
            path = "/api/v1" + path if not path.startswith("/health") else path
        out.extend((method.upper(), path) for method in sorted(methods))
    return [(m, p) for m, p in out if p.startswith("/api/v1")]


ROUTES = api_routes()


def test_route_inventory_is_not_empty() -> None:
    # Boş liste, parametrik testin sessizce hiçbir şey denememesi demektir.
    assert len(ROUTES) >= 20
    assert any(path.startswith("/api/v1/chat") for _, path in ROUTES)
    assert any(path.startswith("/api/v1/calls") for _, path in ROUTES)


@pytest.mark.parametrize(("method", "path"), ROUTES)
async def test_every_route_rejects_missing_service_key(
    client: httpx.AsyncClient, method: str, path: str
) -> None:
    resp = await client.request(method, path, headers={"X-User-Id": OWNER_ID})

    assert resp.status_code == 401, (method, path, resp.text[:120])
    assert resp.json()["error"]["code"] == "unauthorized"


@pytest.mark.parametrize(("method", "path"), ROUTES)
async def test_every_route_rejects_wrong_service_key(
    client: httpx.AsyncClient, method: str, path: str
) -> None:
    resp = await client.request(
        method, path, headers={"X-Service-Key": "yanlis-anahtar", "X-User-Id": OWNER_ID}
    )

    assert resp.status_code == 401, (method, path)


@pytest.mark.parametrize(
    ("method", "path"), [(m, p) for m, p in ROUTES if p.startswith(OWNER_PREFIXES)]
)
async def test_owner_routes_require_user_id(
    client: httpx.AsyncClient, method: str, path: str
) -> None:
    resp = await client.request(method, path, headers={"X-Service-Key": TEST_SERVICE_KEY})

    assert resp.status_code == 400, (method, path, resp.text[:120])


@pytest.mark.parametrize(
    ("method", "path"), [(m, p) for m, p in ROUTES if p.startswith(OWNER_PREFIXES)]
)
async def test_owner_routes_reject_non_uuid_user_id(
    client: httpx.AsyncClient, method: str, path: str
) -> None:
    resp = await client.request(
        method, path, headers={"X-Service-Key": TEST_SERVICE_KEY, "X-User-Id": "1 OR 1=1"}
    )

    assert resp.status_code == 400, (method, path)


async def test_health_endpoints_stay_public(client: httpx.AsyncClient) -> None:
    # Canlılık kontrolü kimlik istemez (yük dengeleyici/orkestratör çağırır); gizli veri taşımaz.
    resp = await client.get("/health")

    assert resp.status_code == 200
    assert set(resp.json()) <= {"status", "version", "env"}


async def test_service_key_is_not_accepted_from_query_string(client: httpx.AsyncClient) -> None:
    # Anahtar yalnızca başlıkta kabul edilir: URL'ler günlüklere ve önbelleklere sızar.
    resp = await client.get(f"/api/v1/me?X-Service-Key={TEST_SERVICE_KEY}")

    assert resp.status_code == 401


async def test_dev_bypass_is_refused_outside_local_and_test() -> None:
    with pytest.raises(ValueError, match="AUTH_DEV_BYPASS"):
        make_settings(auth_dev_bypass=True, app_env="prod", service_api_key="x" * 40)


async def test_valid_key_is_accepted_everywhere_auth_is_checked() -> None:
    # Sağlamlık: kimlik doğrulaması geçilince istek 401 ile DEĞİL, iş mantığıyla yanıtlanır.
    async for c in _client_for(create_app(make_settings())):
        resp = await c.get("/api/v1/me", headers={"X-Service-Key": TEST_SERVICE_KEY})
        assert resp.status_code == 200
