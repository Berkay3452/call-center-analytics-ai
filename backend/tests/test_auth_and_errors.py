import httpx


async def test_unknown_route_uses_error_envelope(client: httpx.AsyncClient) -> None:
    resp = await client.get("/olmayan-yol")
    assert resp.status_code == 404
    error = resp.json()["error"]
    assert error["code"] == "not_found"
    assert error["request_id"] == resp.headers["x-request-id"]


async def test_me_requires_token(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/me")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"
    assert resp.headers["www-authenticate"] == "Bearer"


async def test_me_without_supabase_config_is_unavailable(client: httpx.AsyncClient) -> None:
    # Token var ama SUPABASE_URL yapılandırılmamış → 503 (sessizce kabul edilmez).
    resp = await client.get("/api/v1/me", headers={"Authorization": "Bearer abc.def.ghi"})
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "service_unavailable"


async def test_me_with_dev_bypass(dev_client: httpx.AsyncClient) -> None:
    resp = await dev_client.get("/api/v1/me")
    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"
