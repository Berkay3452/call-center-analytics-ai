"""Miço AI Asistan sohbet uçları birim testleri (#28).

Yetkilendirme (X-Service-Key, X-User-Id), doğrulama (400, 401, 422),
OpenAPI şeması ve sözleşme uyumu.
"""

from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.api.deps import get_db_session
from app.main import create_app
from tests.conftest import TEST_SERVICE_KEY, _client_for, make_settings

VALID_USER_ID = str(UUID("606bd734-644f-5c21-af2f-dc734c4ecd67"))
HEADERS = {
    "X-Service-Key": TEST_SERVICE_KEY,
    "X-User-Id": VALID_USER_ID,
}


class DummySession:
    """Sahte DB oturumu."""

    pass


@pytest.fixture
def test_app() -> FastAPI:
    app = create_app(make_settings())

    async def fake_session() -> AsyncIterator[DummySession]:
        yield DummySession()

    app.dependency_overrides[get_db_session] = fake_session
    return app


@pytest.fixture
async def test_client(test_app: FastAPI) -> AsyncIterator[AsyncClient]:
    async for c in _client_for(test_app):
        yield c


async def test_assistant_chat_requires_service_key(test_client: AsyncClient) -> None:
    """X-Service-Key yoksa 401 Unauthorized döner."""
    resp = await test_client.post(
        "/api/v1/assistant/chat",
        json={"question": "Bakım ne zaman?"},
        headers={"X-User-Id": VALID_USER_ID},
    )
    assert resp.status_code == 401
    data = resp.json()
    assert data["error"]["code"] == "unauthorized"


async def test_assistant_chat_requires_user_id(test_client: AsyncClient) -> None:
    """X-User-Id yoksa 400 Bad Request döner."""
    resp = await test_client.post(
        "/api/v1/assistant/chat",
        json={"question": "Bakım ne zaman?"},
        headers={"X-Service-Key": TEST_SERVICE_KEY},
    )
    assert resp.status_code == 400
    data = resp.json()
    assert "X-User-Id" in data["error"]["message"]


async def test_assistant_chat_requires_valid_uuid_user_id(test_client: AsyncClient) -> None:
    """X-User-Id geçerli bir UUID değilse 400 Bad Request döner."""
    resp = await test_client.post(
        "/api/v1/assistant/chat",
        json={"question": "Bakım ne zaman?"},
        headers={"X-Service-Key": TEST_SERVICE_KEY, "X-User-Id": "gecersiz-id"},
    )
    assert resp.status_code == 400
    data = resp.json()
    assert "UUID olmalıdır" in data["error"]["message"]


async def test_assistant_chat_empty_question_rejected(test_client: AsyncClient) -> None:
    """Boş soru 422 Unprocessable Entity döner."""
    resp = await test_client.post(
        "/api/v1/assistant/chat",
        json={"question": ""},
        headers=HEADERS,
    )
    assert resp.status_code == 422


async def test_assistant_session_detail_requires_auth(test_client: AsyncClient) -> None:
    """Oturum detayı uçları kimlik doğrulama gerektirir."""
    dummy_session_id = str(UUID("11111111-1111-4111-8111-111111111111"))
    # Service key yok
    r1 = await test_client.get(
        f"/api/v1/assistant/sessions/{dummy_session_id}",
        headers={"X-User-Id": VALID_USER_ID},
    )
    assert r1.status_code == 401

    # User id yok
    r2 = await test_client.get(
        f"/api/v1/assistant/sessions/{dummy_session_id}",
        headers={"X-Service-Key": TEST_SERVICE_KEY},
    )
    assert r2.status_code == 400


async def test_openapi_schema_contains_assistant_and_chat_endpoints(test_app: FastAPI) -> None:
    """FastAPI OpenAPI şemasında Issue #28 ve docs/api.md uçları görünür."""
    schema = test_app.openapi()
    paths = schema["paths"]

    # Issue #28 uçları
    assert "/api/v1/assistant/chat" in paths
    assert "post" in paths["/api/v1/assistant/chat"]

    assert "/api/v1/assistant/sessions/{id}" in paths
    assert "get" in paths["/api/v1/assistant/sessions/{id}"]

    assert "/api/v1/assistant/sessions" in paths
    assert "get" in paths["/api/v1/assistant/sessions"]

    # docs/api.md uyumlu uçlar
    assert "/api/v1/chat/messages/stream" in paths
    assert "post" in paths["/api/v1/chat/messages/stream"]

    assert "/api/v1/chat/messages" in paths
    assert "post" in paths["/api/v1/chat/messages"]

    assert "/api/v1/chat/sessions/{session_id}" in paths
    assert "get" in paths["/api/v1/chat/sessions/{session_id}"]

    assert "/api/v1/chat/sessions" in paths
    assert "get" in paths["/api/v1/chat/sessions"]
