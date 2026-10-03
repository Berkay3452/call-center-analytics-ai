import httpx


async def test_health_ok(client: httpx.AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["env"] == "test"


async def test_request_id_is_generated(client: httpx.AsyncClient) -> None:
    resp = await client.get("/health")
    assert len(resp.headers["x-request-id"]) == 32


async def test_request_id_is_propagated(client: httpx.AsyncClient) -> None:
    resp = await client.get("/health", headers={"X-Request-ID": "istek-123"})
    assert resp.headers["x-request-id"] == "istek-123"


async def test_readiness_degraded_when_dependencies_down(client: httpx.AsyncClient) -> None:
    # Veritabanı ve Redis bilerek ulaşılamaz → 503 ve bileşen bazında "error".
    resp = await client.get("/health/ready")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["components"] == {"database": "error", "redis": "error"}
