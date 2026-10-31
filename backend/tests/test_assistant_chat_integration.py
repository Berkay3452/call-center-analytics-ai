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
- Oturum silme (tek / hepsi): yalnızca sahibi, mesajlar CASCADE ile silinir (#176)
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


async def _count_messages(factory: async_sessionmaker[AsyncSession], session_id: str) -> int:
    async with factory() as s:
        stmt = select(ChatMessage).where(ChatMessage.session_id == UUID(session_id))
        rows = await s.scalars(stmt)
        return len(rows.all())


async def test_delete_session_removes_session_and_messages(
    client: AsyncClient, factory: async_sessionmaker[AsyncSession]
) -> None:
    headers = {"X-Service-Key": TEST_SERVICE_KEY, "X-User-Id": str(AHMET_ID)}
    r = await client.post(
        "/api/v1/chat/messages", json={"question": "Toplam masrafım ne kadar?"}, headers=headers
    )
    session_id = r.json()["session_id"]
    assert await _count_messages(factory, session_id) == 2

    for path in ("assistant", "chat"):
        resp = await client.delete(f"/api/v1/{path}/sessions/{session_id}", headers=headers)
        assert resp.status_code == (204 if path == "assistant" else 404)
    assert await _count_messages(factory, session_id) == 0
    get = await client.get(f"/api/v1/chat/sessions/{session_id}", headers=headers)
    assert get.status_code == 404


async def test_delete_session_of_another_owner_is_404_and_keeps_it(
    client: AsyncClient, factory: async_sessionmaker[AsyncSession]
) -> None:
    ahmet = {"X-Service-Key": TEST_SERVICE_KEY, "X-User-Id": str(AHMET_ID)}
    fatma = {"X-Service-Key": TEST_SERVICE_KEY, "X-User-Id": str(FATMA_ID)}
    r = await client.post(
        "/api/v1/chat/messages", json={"question": "Toplam masrafım ne kadar?"}, headers=ahmet
    )
    session_id = r.json()["session_id"]

    resp = await client.delete(f"/api/v1/assistant/sessions/{session_id}", headers=fatma)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"
    resp = await client.delete(f"/api/v1/chat/sessions/{session_id}", headers=fatma)
    assert resp.status_code == 404
    # Fatma'nın "hepsini sil" çağrısı Ahmet'in oturumuna dokunmaz.
    resp = await client.delete("/api/v1/chat/sessions", headers=fatma)
    assert resp.status_code == 204
    assert await _count_messages(factory, session_id) == 2
    assert (
        await client.get(f"/api/v1/chat/sessions/{session_id}", headers=ahmet)
    ).status_code == 200


async def test_delete_all_sessions_only_removes_own(
    client: AsyncClient, factory: async_sessionmaker[AsyncSession]
) -> None:
    ahmet = {"X-Service-Key": TEST_SERVICE_KEY, "X-User-Id": str(AHMET_ID)}
    fatma = {"X-Service-Key": TEST_SERVICE_KEY, "X-User-Id": str(FATMA_ID)}
    ids = []
    for _ in range(2):
        r = await client.post(
            "/api/v1/chat/messages", json={"question": "Toplam masrafım ne kadar?"}, headers=ahmet
        )
        ids.append(r.json()["session_id"])
    other = (
        await client.post(
            "/api/v1/chat/messages", json={"question": "Toplam masrafım ne kadar?"}, headers=fatma
        )
    ).json()["session_id"]

    assert (await client.delete("/api/v1/assistant/sessions", headers=ahmet)).status_code == 204
    assert (await client.get("/api/v1/chat/sessions", headers=ahmet)).json() == []
    for sid in ids:
        assert await _count_messages(factory, sid) == 0
    assert await _count_messages(factory, other) == 2


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


# --- 5. Hata durumları (inceleme düzeltmeleri) ---


async def test_unexpected_error_does_not_leak_details(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Beklenmeyen hatada istemciye iç hata metni değil genel mesaj gider."""
    from app.services import assistant_chat

    async def boom(*args: object, **kwargs: object) -> object:
        raise RuntimeError("password=gizli-ic-hata-ayrintisi")

    monkeypatch.setattr(assistant_chat, "answer_question", boom)
    headers = {"X-Service-Key": TEST_SERVICE_KEY, "X-User-Id": str(AHMET_ID)}

    resp = await client.post(
        "/api/v1/assistant/chat", json={"question": "Kaç bakım hakkım kaldı?"}, headers=headers
    )

    assert "gizli-ic-hata-ayrintisi" not in resp.text
    events = _parse_sse(resp.text)
    assert [e[0] for e in events] == ["error"]
    assert json.loads(events[0][1])["message"] == assistant_chat.GENERIC_ERROR_MESSAGE


async def test_llm_unavailable_gets_polite_message_without_echoing_question(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.assistant.llm import AssistantLLMError
    from app.services import assistant_chat

    async def down(*args: object, **kwargs: object) -> object:
        raise AssistantLLMError("sağlayıcı yok")

    monkeypatch.setattr(assistant_chat, "answer_question", down)
    headers = {"X-Service-Key": TEST_SERVICE_KEY, "X-User-Id": str(AHMET_ID)}

    resp = await client.post(
        "/api/v1/chat/messages", json={"question": "Gizli soru metni?"}, headers=headers
    )

    assert resp.status_code == 200
    answer = resp.json()["answer"]
    assert answer["content"] == assistant_chat.ASSISTANT_UNAVAILABLE_MESSAGE
    assert "Gizli soru" not in answer["content"] and answer["found"] is False


async def test_missing_llm_key_gets_polite_message(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """LLM_API_KEY yokken (kural dışı soruda planlayıcı LLM ister) genel hata değil nazik mesaj."""
    from app.llm.client import LLMNotConfiguredError
    from app.services import assistant_chat

    async def no_key(*args: object, **kwargs: object) -> object:
        raise LLMNotConfiguredError("LLM_API_KEY tanımlı değil (.env).")

    monkeypatch.setattr(assistant_chat, "answer_question", no_key)
    headers = {"X-Service-Key": TEST_SERVICE_KEY, "X-User-Id": str(AHMET_ID)}

    resp = await client.post("/api/v1/chat/messages", json={"question": "selam"}, headers=headers)

    assert resp.status_code == 200
    assert resp.json()["answer"]["content"] == assistant_chat.ASSISTANT_UNAVAILABLE_MESSAGE


# --- 6. Akış hızı ve Türkçe sayı biçimi (#83) ---


def test_chunk_text_is_word_by_word_and_lossless() -> None:
    from app.services.assistant_chat import _chunk_text

    text = "Ekim 2026 döneminde  toplam giderleriniz 14.250,00 TL (1 kalem).\nSon satır."
    chunks = _chunk_text(text)

    assert "".join(chunks) == text  # boşluk ve satır sonları dahil birebir
    assert len(chunks) == len(text.split())
    assert chunks[0] == "Ekim " and _chunk_text("") == []


def test_chunk_delay_is_per_word_but_total_time_is_capped() -> None:
    from app.services import assistant_chat as ac

    assert ac._chunk_delay(0) == 0.0
    assert ac._chunk_delay(10) == ac.STREAM_WORD_DELAY_S  # kısa cevap: kelime başına sabit
    long_words = 500
    assert ac._chunk_delay(long_words) * long_words <= ac.STREAM_MAX_TOTAL_S + 1e-9


async def test_stream_waits_between_words(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hazır soru cevabı da kelime kelime, bekleyerek akar (tek seferde basılmaz)."""
    from app.services import assistant_chat

    waits: list[float] = []
    real_sleep = assistant_chat.asyncio.sleep

    async def record(delay: float) -> None:
        waits.append(delay)
        await real_sleep(0)

    monkeypatch.setattr(assistant_chat.asyncio, "sleep", record)
    headers = {"X-Service-Key": TEST_SERVICE_KEY, "X-User-Id": str(AHMET_ID)}

    resp = await client.post(
        "/api/v1/chat/messages/stream",
        json={"question": "Kaç bakım hakkım kaldı?"},
        headers=headers,
    )

    events = _parse_sse(resp.text)
    deltas = [json.loads(d)["text"] for e, d in events if e == "delta"]
    assert len(deltas) >= 5  # kelime kelime (eskiden ~5 büyük parça)
    assert len(waits) == len(deltas) and all(w > 0 for w in waits)


async def test_expense_source_excerpt_uses_turkish_number_format(client: AsyncClient) -> None:
    """Kaynak kartı alıntısı da cevap metni gibi `14.250,00 TL` biçiminde olmalı."""
    headers = {"X-Service-Key": TEST_SERVICE_KEY, "X-User-Id": str(AHMET_ID)}

    resp = await client.post(
        "/api/v1/chat/messages", json={"question": "Bu ay ne kadar harcadım?"}, headers=headers
    )

    answer = resp.json()["answer"]
    assert "14.250,00 TL" in answer["content"]
    excerpts = [s["excerpt"] for s in answer["sources"]]
    assert excerpts and all("14.250,00 TL" in e for e in excerpts)
    assert not any("14,250.00" in e for e in excerpts)


# --- 6. Çok turlu bağlam (#111) ---


async def test_follow_up_turn_receives_session_history(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """İkinci soru aynı oturumun önceki mesajlarını `history` olarak alır; ilk soru boş alır."""
    from app.services import assistant_chat

    seen: list[list[tuple[str, str]]] = []
    real = assistant_chat.answer_question

    async def spy(req: object, **kwargs: object) -> object:
        seen.append([(t.role, t.content) for t in req.history])  # type: ignore[attr-defined]
        return await real(req, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(assistant_chat, "answer_question", spy)
    headers = {"X-Service-Key": TEST_SERVICE_KEY, "X-User-Id": str(AHMET_ID)}

    r1 = await client.post(
        "/api/v1/chat/messages", json={"question": "Kaç bakım hakkım kaldı?"}, headers=headers
    )
    session_id = r1.json()["session_id"]
    await client.post(
        "/api/v1/chat/messages",
        json={"question": "Son bakım ne zaman yapıldı?", "session_id": session_id},
        headers=headers,
    )

    assert seen[0] == []
    assert [role for role, _ in seen[1]] == ["user", "assistant"]
    assert seen[1][0][1] == "Kaç bakım hakkım kaldı?"


async def test_history_never_comes_from_another_owners_session(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fatma, Ahmet'in oturum kimliğiyle devam etmeye çalışırsa 404 alır; geçmiş okunmaz."""
    from app.services import assistant_chat

    calls = 0
    real = assistant_chat.answer_question

    async def spy(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        return await real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(assistant_chat, "answer_question", spy)
    ahmet = {"X-Service-Key": TEST_SERVICE_KEY, "X-User-Id": str(AHMET_ID)}
    fatma = {"X-Service-Key": TEST_SERVICE_KEY, "X-User-Id": str(FATMA_ID)}
    r1 = await client.post(
        "/api/v1/chat/messages", json={"question": "Kaç bakım hakkım kaldı?"}, headers=ahmet
    )
    session_id = r1.json()["session_id"]
    assert calls == 1

    r2 = await client.post(
        "/api/v1/chat/messages",
        json={"question": "Peki ne yapılmıştı?", "session_id": session_id},
        headers=fatma,
    )

    assert r2.status_code == 404
    assert calls == 1  # asistan hiç çalışmadı


async def test_load_history_skips_unavailable_message_and_keeps_order(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    from datetime import UTC, datetime, timedelta

    from app.services.assistant_chat import ASSISTANT_UNAVAILABLE_MESSAGE, load_history

    async with factory() as db:
        now = datetime.now(UTC)
        sess = ChatSession(id=uuid4(), owner_id=AHMET_ID, title="t", created_at=now, updated_at=now)
        db.add(sess)
        await db.flush()
        for i, (role, text) in enumerate(
            [
                ("user", "bir"),
                ("assistant", ASSISTANT_UNAVAILABLE_MESSAGE),
                ("user", "iki"),
                ("assistant", "cevap"),
            ]
        ):
            db.add(
                ChatMessage(
                    id=uuid4(),
                    session_id=sess.id,
                    role=role,
                    content=text,
                    question_type=None,
                    sources=[],
                    found=True,
                    created_at=now + timedelta(seconds=i),
                )
            )
        await db.flush()

        history = await load_history(db, sess)

    assert [(t.role, t.content) for t in history] == [
        ("user", "bir"),
        ("user", "iki"),
        ("assistant", "cevap"),
    ]
