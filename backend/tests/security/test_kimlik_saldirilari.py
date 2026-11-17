"""Kimlik saldırıları: anahtarsız, sahte, değiştirilmiş anahtar; yanlış kanaldan anahtar;
sahte `X-User-Id`; yetki yükseltme; kaba kuvvet; gereksiz bilgi sızıntısı (OWASP API2, API5, API8).

Veritabanı gerekmez: kimlik doğrulaması iş mantığından önce çalışır.
"""

from typing import Any

import httpx
import pytest

from tests.conftest import TEST_SERVICE_KEY, make_settings
from tests.security.helpers import OWNER_A, client_for, owner_headers

KEY = TEST_SERVICE_KEY
# Korunan örnek uçlar: yönetici ve tekne sahibi okuma uçları.
PROTECTED = [
    "/api/v1/me",
    "/api/v1/calls",
    "/api/v1/analytics/summary",
    "/api/v1/audit-log",
    "/api/v1/assistant/sessions",
    "/api/v1/chat/sessions",
]

FORGED_KEYS = [
    "",
    " ",
    KEY.upper(),
    KEY.title(),
    f" {KEY}",
    f"{KEY} ",
    f"{KEY}\t",
    KEY[:-1],
    KEY[1:],
    KEY + "x",
    KEY * 2,
    f"Bearer {KEY}",
    f"Basic {KEY}",
    "null",
    "undefined",
    "true",
    "*",
    "change-me-in-local-env",  # compose varsayılanı canlıda geçerli olmamalı
    "' OR '1'='1",
    "a" * 10_000,
]


@pytest.mark.parametrize("key", FORGED_KEYS)
@pytest.mark.parametrize("path", PROTECTED)
async def test_forged_or_mutated_service_key_is_rejected(
    client: httpx.AsyncClient, path: str, key: str
) -> None:
    resp = await client.get(path, headers={"X-Service-Key": key, "X-User-Id": OWNER_A})

    assert resp.status_code == 401, (path, key[:20])
    assert resp.json()["error"]["code"] == "unauthorized"


@pytest.mark.parametrize("raw", ["anahtarş".encode(), "ключ".encode(), KEY.encode() + b"\xff"])
async def test_non_ascii_service_key_is_rejected(client: httpx.AsyncClient, raw: bytes) -> None:
    resp = await client.get("/api/v1/me", headers=[(b"x-service-key", raw)])

    assert resp.status_code == 401


@pytest.mark.parametrize(
    "extra",
    [
        pytest.param({"params": {"X-Service-Key": KEY, "service_key": KEY}}, id="sorgu"),
        pytest.param(
            {"headers": {"Cookie": f"X-Service-Key={KEY}; service_key={KEY}"}}, id="cerez"
        ),
        pytest.param({"headers": {"Authorization": f"Bearer {KEY}"}}, id="bearer"),
        pytest.param({"headers": {"X-Api-Key": KEY}}, id="x-api-key"),
        pytest.param({"headers": {"X-Service-Key-Override": KEY}}, id="uzantili-baslik"),
        pytest.param({"headers": {"X-Forwarded-User": "admin"}}, id="vekil-kimlik"),
    ],
)
async def test_key_is_accepted_only_from_its_header(
    client: httpx.AsyncClient, extra: dict[str, Any]
) -> None:
    resp = await client.get("/api/v1/me", **extra)

    assert resp.status_code == 401


async def test_key_in_json_body_is_not_accepted(client: httpx.AsyncClient) -> None:
    body = {"X-Service-Key": KEY, "service_key": KEY, "owner_id": OWNER_A}
    resp = await client.post("/api/v1/crm/reviews", json=body)

    assert resp.status_code in {401, 404, 405}


@pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE", "POST", "HEAD"])
async def test_unusual_methods_do_not_bypass_authentication(
    client: httpx.AsyncClient, method: str
) -> None:
    resp = await client.request(method, "/api/v1/me")

    assert resp.status_code in {401, 405}


@pytest.mark.parametrize(
    "raw",
    [
        "1 OR 1=1",
        "'; DROP TABLE customers;--",
        "../../etc/passwd",
        "*",
        "null",
        "admin",
        "0",
        f"{OWNER_A},{OWNER_A}",  # birden çok kimlik
        f"{OWNER_A}x",
        OWNER_A.replace("-", "")[:-1],
        "%00",
        "<script>alert(1)</script>",
        "9" * 5000,
    ],
)
@pytest.mark.parametrize("path", ["/api/v1/assistant/sessions", "/api/v1/chat/sessions"])
async def test_spoofed_user_id_is_rejected_before_any_data_access(
    client: httpx.AsyncClient, path: str, raw: str
) -> None:
    resp = await client.get(path, headers={"X-Service-Key": KEY, "X-User-Id": raw})

    assert resp.status_code == 400, (path, raw[:30], resp.text[:100])


async def test_owner_identity_cannot_reach_admin_endpoints(client: httpx.AsyncClient) -> None:
    """Yetki yükseltme (BFLA): tekne sahibi kimliğiyle yönetici uçları 403 verir."""
    h = owner_headers(OWNER_A)

    assert (await client.get("/api/v1/audit-log", headers=h)).status_code == 403
    deleted = await client.delete("/api/v1/calls/00000000-0000-4000-8000-000000000001", headers=h)
    assert deleted.status_code == 403


async def test_owner_claims_in_query_do_not_substitute_for_the_key(
    client: httpx.AsyncClient,
) -> None:
    """Kimlik başlıkta aranır; sorgudaki `owner_id`/`role` yetki vermez."""
    resp = await client.get(f"/api/v1/audit-log?owner_id={OWNER_A}&role=admin")

    assert resp.status_code == 401


async def test_brute_force_is_throttled_and_blocks_even_the_right_key() -> None:
    settings = make_settings(rate_limit_backend="memory", rate_limit_auth_fail_per_min=5)
    async for c in client_for(settings):
        guesses = [
            (await c.get("/api/v1/me", headers={"X-Service-Key": f"tahmin-{i}"})).status_code
            for i in range(12)
        ]
        assert guesses[:5] == [401] * 5
        assert set(guesses[5:]) == {429}
        locked = await c.get("/api/v1/me", headers={"X-Service-Key": KEY})
        assert locked.status_code == 429
        assert int(locked.headers["retry-after"]) >= 1


@pytest.mark.parametrize("path", ["/api/v1/me", "/api/v1/calls", "/yok/boyle/bir/yol"])
async def test_error_bodies_do_not_leak_internals_or_the_supplied_key(
    client: httpx.AsyncClient, path: str
) -> None:
    probe = "gizli-deneme-anahtari-12345"
    resp = await client.get(path, headers={"X-Service-Key": probe})
    text = resp.text

    assert probe not in text
    assert KEY not in text
    for marker in ("Traceback", 'File "', "sqlalchemy", "asyncpg", "/app/", "site-packages"):
        assert marker not in text, marker
    assert "x-powered-by" not in resp.headers


async def test_only_health_endpoints_are_public(client: httpx.AsyncClient) -> None:
    """OpenAPI'deki parametresiz her GET ucu kimliksiz denenir; yalnızca /health 200 dönebilir."""
    paths = (await client.get("/openapi.json")).json()["paths"]
    public = [
        path
        for path, methods in paths.items()
        if "{" not in path and "get" in methods and (await client.get(path)).status_code == 200
    ]

    assert set(public) <= {"/health", "/health/ready", "/openapi.json"}, public


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"])
async def test_api_docs_are_closed_in_production(path: str) -> None:
    settings = make_settings(
        app_env="prod",
        service_api_key="x" * 40,
        rate_limit_backend="memory",
        audit_auth_failures=True,
    )
    async for c in client_for(settings):
        resp = await c.get(path)
        assert resp.status_code in {401, 404}, (path, resp.status_code)
