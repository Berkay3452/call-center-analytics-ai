"""Miço AI Asistan sohbet uçları gerçek veritabanı entegrasyon testleri (#28).

Yalnızca `RUN_DB_TESTS=1` iken çalışır.
Test edilenler:
- `POST /api/v1/assistant/chat`: SSE akışı (token -> sources -> done)
- `POST /api/v1/chat/messages/stream`: SSE akışı (status -> delta -> done)
- `POST /api/v1/chat/messages`: Senkron cevap
- `GET /api/v1/assistant/sessions/{id}`: Oturum geçmişi ve kullanıcı izolasyonu
- `GET /api/v1/assistant/sessions`: Oturum listesi
- Soru ve cevapların veritabanına (`chat_sessions`, `chat_messages`) yazılması
- Başka kullanıcının oturumunun okunamaması (404)
"""

import json
import os
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.api.deps import get_db_session
from app.core.config import Settings
from app.db.models.ai import ChatMessage, ChatSession
from app.main import create_app
from tests.conftest import TEST_SERVICE_KEY, make_settings

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_DB_TESTS") != "1", reason="RUN_DB_TESTS=1 değil (gerçek veritabanı gerekir)"
)

AHMET_ID = UUID("606bd734-644f-5c21-af2f-dc734c4ecd67")  # Ahmet Yılmaz (Poyraz)
FATMA_ID = UUID("8ff32870-b5ca-5689-a6af-3548246f014e")  # Fatma Kaya (Albatros)


@pytest.fixture
async def conn() -> AsyncIterator[AsyncConnection]:
    engine = create_async_engine(Settings().database_url)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        try:
            yield connection
        finally:
            await transaction.rollback()
    await engine.dispose()


@pytest.fixture
def factory(conn: AsyncConnection) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )


@pytest.fixture
async def client(factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncClient]:
    app = create_app(make_settings(database_url=Settings().database_url))

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _parse_sse(text: str) -> list[tuple[str, str]]:
    """SSE metnini (event, data) çiftleri listesine dönüştürür."""
    events: list[tuple[str, str]] = []
    current_event: str | None = None
    current_data: list[str] = []

    for line in text.splitlines():
        if line.startswith("event:"):
            current_event = line.replace("event:", "").strip()
        elif line.startswith("data:"):
            current_data.append(line.replace("data:", "").strip())
        elif line == "" and current_event is not None:
            events.append((current_event, "\n".join(current_data)))
            current_event = None
            current_data = []

    if current_event is not None:
        events.append((current_event, "\n".join(current_data)))

    return events


# --- 1. POST /api/v1/assistant/chat (SSE: token -> sources -> done) ---


async def test_assistant_chat_stream_creates_session_and_messages(
    client: AsyncClient, factory: async_sessionmaker[AsyncSession]
) -> None:
    headers = {"X-Service-Key": TEST_SERVICE_KEY, "X-User-Id": str(AHMET_ID)}
    question_text = "Bu ay ne kadar harcadım?"

    resp = await client.post(
        "/api/v1/assistant/chat",
        json={"question": question_text},
        headers=headers,
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]

    events = _parse_sse(resp.text)
    event_names = [e[0] for e in events]

    # Olaylar token -> sources -> done sırasıyla gelmelidir
    assert "token" in event_names
    assert "sources" in event_names
    assert "done" in event_names
    assert event_names.index("token") < event_names.index("sources") < event_names.index("done")

    # token parçaları birleştirildiğinde anlamlı bir metin oluşturur
    tokens = [json.loads(data).get("text", "") for ev, data in events if ev == "token"]
    full_text = "".join(tokens)
    assert "gider" in full_text.lower() or "tl" in full_text.lower()

    # sources listesi
    sources_data = next(json.loads(data) for ev, data in events if ev == "sources")
    assert isinstance(sources_data, list)

    # done verisi
    done_data = next(json.loads(data) for ev, data in events if ev == "done")
    session_id = UUID(done_data["session_id"])
    assert done_data["question"]["content"] == question_text
    assert done_data["answer"]["content"] == full_text

    # Veritabanında oturum ve mesajların kaydedildiğini doğrula
    async with factory() as db:
        chat_sess = await db.scalar(select(ChatSession).where(ChatSession.id == session_id))
        assert chat_sess is not None
        assert chat_sess.owner_id == AHMET_ID
        assert chat_sess.title == question_text

        msgs = (
            await db.scalars(
                select(ChatMessage)
                .where(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.created_at.asc())
            )
        ).all()
        assert len(msgs) == 2
        assert msgs[0].role == "user" and msgs[0].content == question_text
        assert msgs[1].role == "assistant" and msgs[1].content == full_text


async def test_assistant_chat_stream_continues_existing_session(
    client: AsyncClient, factory: async_sessionmaker[AsyncSession]
) -> None:
    headers = {"X-Service-Key": TEST_SERVICE_KEY, "X-User-Id": str(AHMET_ID)}

    # 1. soru: yeni oturum
    r1 = await client.post(
        "/api/v1/assistant/chat",
        json={"question": "Kaç bakım hakkım kaldı?"},
        headers=headers,
    )
    events1 = _parse_sse(r1.text)
    done_data1 = next(json.loads(data) for ev, data in events1 if ev == "done")
    session_id = done_data1["session_id"]

    # 2. soru: mevcut session_id ile devam et
    r2 = await client.post(
        "/api/v1/assistant/chat",
        json={"question": "Son bakım ne zaman yapıldı?", "session_id": session_id},
        headers=headers,
    )
    events2 = _parse_sse(r2.text)
    done_data2 = next(json.loads(data) for ev, data in events2 if ev == "done")
    assert done_data2["session_id"] == session_id

    # Veritabanında aynı oturum altında 4 mesaj (2 soru + 2 cevap) olmalı
    async with factory() as db:
        msgs = (
            await db.scalars(
                select(ChatMessage)
                .where(ChatMessage.session_id == UUID(session_id))
                .order_by(ChatMessage.created_at.asc())
            )
        ).all()
        assert len(msgs) == 4
        assert [m.role for m in msgs] == ["user", "assistant", "user", "assistant"]


# --- 2. POST /api/v1/chat/messages/stream (SSE: status -> delta -> done) ---


async def test_chat_messages_stream_endpoint(client: AsyncClient) -> None:
    headers = {"X-Service-Key": TEST_SERVICE_KEY, "X-User-Id": str(AHMET_ID)}
    resp = await client.post(
        "/api/v1/chat/messages/stream",
        json={"question": "Kaç bakım hakkım kaldı?"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]

    events = _parse_sse(resp.text)
    event_names = [e[0] for e in events]

    assert "status" in event_names
    assert "delta" in event_names
    assert "done" in event_names


# --- 3. POST /api/v1/chat/messages (Senkron Yanıt) ---


async def test_chat_messages_sync_endpoint(client: AsyncClient) -> None:
    headers = {"X-Service-Key": TEST_SERVICE_KEY, "X-User-Id": str(AHMET_ID)}
    resp = await client.post(
        "/api/v1/chat/messages",
        json={"question": "Son bakım ne zaman yapıldı?"},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "session_id" in data
    assert data["question"]["role"] == "user"
    assert data["answer"]["role"] == "assistant"
    assert "Poyraz" in data["answer"]["content"] or "bakım" in data["answer"]["content"]


# --- 4. GET Oturum Detayı ve Kullanıcı İzolasyonu ---


async def test_get_session_detail_and_cross_user_isolation(client: AsyncClient) -> None:
    ahmet_headers = {"X-Service-Key": TEST_SERVICE_KEY, "X-User-Id": str(AHMET_ID)}
    fatma_headers = {"X-Service-Key": TEST_SERVICE_KEY, "X-User-Id": str(FATMA_ID)}

    # Ahmet bir oturum açar
    r = await client.post(
        "/api/v1/chat/messages",
        json={"question": "Toplam masrafım ne kadar?"},
        headers=ahmet_headers,
    )
    session_id = r.json()["session_id"]

    # Ahmet kendi oturumunu okuyabilir
    r_ahmet = await client.get(
        f"/api/v1/assistant/sessions/{session_id}",
        headers=ahmet_headers,
    )
    assert r_ahmet.status_code == 200
    data_ahmet = r_ahmet.json()
    assert data_ahmet["session"]["id"] == session_id
    assert len(data_ahmet["messages"]) == 2

    # Fatma, Ahmet'in oturumunu okumaya çalışırsa 404 döner (izolasyon kanıtı)
    r_fatma = await client.get(
        f"/api/v1/assistant/sessions/{session_id}",
        headers=fatma_headers,
    )
    assert r_fatma.status_code == 404
    assert r_fatma.json()["error"]["code"] == "not_found"

    # docs/api.md uyumlu uçla da (/chat/sessions/{session_id}) Fatma 404 alır
    r_fatma_alt = await client.get(
        f"/api/v1/chat/sessions/{session_id}",
        headers=fatma_headers,
    )
    assert r_fatma_alt.status_code == 404


async def test_list_sessions_cross_user_isolation(client: AsyncClient) -> None:
    ahmet_headers = {"X-Service-Key": TEST_SERVICE_KEY, "X-User-Id": str(AHMET_ID)}
    fatma_headers = {"X-Service-Key": TEST_SERVICE_KEY, "X-User-Id": str(FATMA_ID)}

    # Ahmet bir oturum açar
    r = await client.post(
        "/api/v1/chat/messages",
        json={"question": "Kaç bakım hakkım kaldı?"},
        headers=ahmet_headers,
    )
    ahmet_session_id = r.json()["session_id"]

    # Ahmet listelediğinde oturumunu görür
    r_ahmet = await client.get("/api/v1/assistant/sessions", headers=ahmet_headers)
    assert r_ahmet.status_code == 200
    ahmet_sessions = r_ahmet.json()
    assert any(s["id"] == ahmet_session_id for s in ahmet_sessions)

    # Fatma listelediğinde Ahmet'in oturumunu ASLA görmez
    r_fatma = await client.get("/api/v1/assistant/sessions", headers=fatma_headers)
    assert r_fatma.status_code == 200
    fatma_sessions = r_fatma.json()
    assert all(s["id"] != ahmet_session_id for s in fatma_sessions)


async def test_non_existent_customer_returns_404(client: AsyncClient) -> None:
    random_customer_id = str(uuid4())
    headers = {"X-Service-Key": TEST_SERVICE_KEY, "X-User-Id": random_customer_id}

    r = await client.post(
        "/api/v1/assistant/chat",
        json={"question": "Merhaba"},
        headers=headers,
    )
    assert r.status_code == 200
    events = _parse_sse(r.text)
    # SSE içinde error olayı döner
    error_event = next((json.loads(d) for ev, d in events if ev == "error"), None)
    assert error_event is not None
    assert error_event["code"] == "not_found"
