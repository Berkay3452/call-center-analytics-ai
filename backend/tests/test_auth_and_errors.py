from collections.abc import Callable

import httpx

from app.core.config import Settings
from app.main import create_app
from tests.conftest import TEST_SERVICE_KEY, _client_for

OWNER_ID = "3f2b8c1e-5d4a-4e6f-9a7b-1c2d3e4f5a6b"


async def test_unknown_route_uses_error_envelope(client: httpx.AsyncClient) -> None:
    resp = await client.get("/olmayan-yol")
    assert resp.status_code == 404
    error = resp.json()["error"]
    assert error["code"] == "not_found"
    assert error["request_id"] == resp.headers["x-request-id"]


async def test_me_without_service_key_returns_401(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/me")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


async def test_me_with_wrong_service_key_returns_401(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/me", headers={"X-Service-Key": "wrong-key"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


async def test_me_with_valid_service_key_returns_200(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/me", headers={"X-Service-Key": TEST_SERVICE_KEY})
    assert resp.status_code == 200
    body = resp.json()
    assert body["authenticated"] is True
    assert body["owner_id"] is None


async def test_me_passes_optional_user_id_header(client: httpx.AsyncClient) -> None:
    resp = await client.get(
        "/api/v1/me",
        headers={"X-Service-Key": TEST_SERVICE_KEY, "X-User-Id": f" {OWNER_ID} "},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["authenticated"] is True
    assert body["owner_id"] == OWNER_ID


async def test_owner_endpoint_requires_user_id_header(client: httpx.AsyncClient) -> None:
    resp_missing = await client.get(
        "/api/v1/me/owner",
        headers={"X-Service-Key": TEST_SERVICE_KEY},
    )
    assert resp_missing.status_code == 400
    assert resp_missing.json()["error"]["code"] == "bad_request"

    resp_blank = await client.get(
        "/api/v1/me/owner",
        headers={"X-Service-Key": TEST_SERVICE_KEY, "X-User-Id": "   "},
    )
    assert resp_blank.status_code == 400
    assert resp_blank.json()["error"]["code"] == "bad_request"


async def test_owner_endpoint_succeeds_with_service_key_and_user_id(
    client: httpx.AsyncClient,
) -> None:
    resp = await client.get(
        "/api/v1/me/owner",
        headers={"X-Service-Key": TEST_SERVICE_KEY, "X-User-Id": OWNER_ID},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["authenticated"] is True
    assert body["owner_id"] == OWNER_ID


async def test_me_without_service_key_config_is_unavailable(
    settings_factory: Callable[..., Settings],
) -> None:
    # İstek X-Service-Key gönderiyor ama sunucuda SERVICE_API_KEY yapılandırılmamış → 503.
    app = create_app(settings_factory(service_api_key=None))
    async for unconfigured_client in _client_for(app):
        resp = await unconfigured_client.get(
            "/api/v1/me", headers={"X-Service-Key": TEST_SERVICE_KEY}
        )
        assert resp.status_code == 503
        assert resp.json()["error"]["code"] == "service_unavailable"


async def test_me_with_dev_bypass(dev_client: httpx.AsyncClient) -> None:
    resp = await dev_client.get("/api/v1/me")
    assert resp.status_code == 200
    assert resp.json()["authenticated"] is True


async def test_user_id_must_be_uuid(client: httpx.AsyncClient) -> None:
    resp = await client.get(
        "/api/v1/me/owner",
        headers={"X-Service-Key": TEST_SERVICE_KEY, "X-User-Id": "owner_001"},
    )
    assert resp.status_code == 400
    assert "UUID" in resp.json()["error"]["message"]
    resp_admin = await client.get(
        "/api/v1/me", headers={"X-Service-Key": TEST_SERVICE_KEY, "X-User-Id": "owner_001"}
    )
    assert resp_admin.status_code == 400
