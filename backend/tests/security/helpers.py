"""Güvenlik paketi ortak yardımcıları."""

from collections.abc import AsyncIterator

import httpx

from app.core.config import Settings
from app.main import create_app
from tests.conftest import TEST_SERVICE_KEY, _client_for

OWNER_A = "11111111-1111-4111-8111-111111111111"
OWNER_B = "22222222-2222-4222-8222-222222222222"


def owner_headers(owner_id: str) -> dict[str, str]:
    return {"X-Service-Key": TEST_SERVICE_KEY, "X-User-Id": owner_id}


async def client_for(settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    """Verilen ayarlarla uygulama kurar (yaşam döngüsü açılıp kapanır)."""
    async for c in _client_for(create_app(settings)):
        yield c
