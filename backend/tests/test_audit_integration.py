"""Denetim günlüğü, gerçek veritabanı entegrasyon testleri (#267).

Yalnızca `RUN_DB_TESTS=1` iken çalışır. Her test geri alınan bir işlemde çalışır: ortak
geliştirme veritabanına kalıcı satır yazılmaz (denetim günlüğü zaten silinemez).

Kapsam: yalnızca ekleme (UPDATE/DELETE/TRUNCATE reddi), listeleme ve süzgeçler, kimlik doğrulama
başarısızlığı, çağrı yükleme, CRM onay/red, servis emri oluşturma/durum, asistan güvenlik
tetikleyicisi ve kayıtlarda ham kişisel veri bulunmaması.
"""

import os
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.api.deps import get_db_session
from app.api.routes.call_intake import get_enqueue
from app.assistant.assistant import answer_question
from app.core.config import Settings
from app.db.models.ai import AnalysisResult, Call
from app.db.models.audit import AuditLog
from app.db.models.external import Customer
from app.domain.audit import AuditAction, AuditOutcome
from app.main import create_app
from app.schemas.assistant import AssistantRequest
from app.services.audit import record_audit_event
from tests.conftest import TEST_SERVICE_KEY, make_settings

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_DB_TESTS") != "1", reason="RUN_DB_TESTS=1 değil (gerçek veritabanı gerekir)"
)

HEADERS = {"X-Service-Key": TEST_SERVICE_KEY}


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
    app = create_app(make_settings(database_url=Settings().database_url, audit_auth_failures=True))

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    # Lifespan çalışmadığı için kimlik doğrulama başarısızlığı yazıcısı test fabrikasını kullanır.
    app.state.session_factory = factory
    app.dependency_overrides[get_enqueue] = lambda: lambda call_id, kind: "task-test"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _events(
    factory: async_sessionmaker[AsyncSession], request_id: str | None = None
) -> list[AuditLog]:
    async with factory() as session:
        stmt = select(AuditLog).order_by(AuditLog.occurred_at, AuditLog.id)
        if request_id:
            stmt = stmt.where(AuditLog.request_id == request_id)
        return list((await session.scalars(stmt)).all())


async def _seed_call(session: AsyncSession) -> Call:
    stmt = (
        select(Call)
        .join(AnalysisResult, Call.id == AnalysisResult.call_id)
        .where(Call.customer_id.is_not(None), Call.boat_id.is_not(None))
        .limit(1)
    )
    call = await session.scalar(stmt)
    assert call is not None, "Seed verisinde analizli, eşleşmiş çağrı yok."
    return call


async def test_audit_log_is_append_only(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as session:
        event = await record_audit_event(
            session, action=AuditAction.SES_ERISIMI, target_type="call", target_id=uuid4()
        )
        assert event.id is not None and event.occurred_at is not None

        for statement in (
            "UPDATE audit_log SET outcome = 'hata'",
            "DELETE FROM audit_log",
            "TRUNCATE TABLE audit_log",
        ):
            with pytest.raises(DBAPIError, match="yalnızca ekleme"):
                async with session.begin_nested():
                    await session.execute(text(statement))
        assert await session.get(AuditLog, event.id) is not None


async def test_outcome_check_constraint(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as session:
        with pytest.raises(DBAPIError):
            async with session.begin_nested():
                await session.execute(
                    text("INSERT INTO audit_log (action, outcome) VALUES ('x', 'belirsiz')")
                )


async def test_auth_failure_is_recorded_without_key_value(
    client: AsyncClient, factory: async_sessionmaker[AsyncSession]
) -> None:
    attempt = "yanlis" + "-deneme-" + "9876"
    missing = await client.get("/api/v1/crm", headers={"X-Request-ID": "kd-eksik"})
    wrong = await client.get(
        "/api/v1/crm", headers={"X-Service-Key": attempt, "X-Request-ID": "kd-yanlis"}
    )
    assert missing.status_code == wrong.status_code == 401

    (ev_missing,) = await _events(factory, "kd-eksik")
    (ev_wrong,) = await _events(factory, "kd-yanlis")
    assert ev_missing.action == "kimlik_dogrulama_basarisiz"
    assert ev_missing.outcome == AuditOutcome.REDDEDILDI.value
    assert ev_missing.actor_role == "anonim"
    assert ev_missing.target_id == "crm"
    assert ev_missing.details == {"neden": "eksik"}
    assert ev_wrong.details == {"neden": "gecersiz"}
    assert ev_wrong.ip is not None
    assert attempt not in repr([ev_wrong.details, ev_wrong.target_id, ev_wrong.request_id])


async def test_call_upload_crm_and_service_order_events(
    client: AsyncClient, factory: async_sessionmaker[AsyncSession]
) -> None:
    created = await client.post(
        "/api/v1/calls",
        json={"started_at": "2026-11-17T09:00:00Z", "transcript": "Müşteri: Merhaba."},
        headers={**HEADERS, "X-Request-ID": "kd-yukle"},
    )
    assert created.status_code == 202, created.text
    (upload,) = await _events(factory, "kd-yukle")
    assert upload.action == "cagri_yuklendi"
    assert upload.target_id == created.json()["call_id"]
    assert upload.actor_role == "servis"
    assert upload.details == {"kaynak": "metin"}

    async with factory() as session:
        call = await _seed_call(session)
    approved = await client.post(
        f"/api/v1/crm/{call.id}/approve",
        json={"note": "Ali Yılmaz aradı, 0532 123 45 67"},  # not kaydedilir ama günlüğe girmez
        headers={**HEADERS, "X-Request-ID": "kd-onay"},
    )
    assert approved.status_code == 200, approved.text
    order_id = approved.json()["service_order_id"]
    onay = {e.action: e for e in await _events(factory, "kd-onay")}
    assert set(onay) == {"crm_onaylandi", "servis_emri_olusturuldu"}
    assert onay["crm_onaylandi"].target_id == str(call.id)
    assert onay["servis_emri_olusturuldu"].target_id == order_id

    rejected = await client.post(
        f"/api/v1/crm/{call.id}/reject",
        json={"note": "gerek yok"},
        headers={**HEADERS, "X-Request-ID": "kd-red"},
    )
    assert rejected.status_code == 200
    (red,) = await _events(factory, "kd-red")
    assert red.action == "crm_reddedildi"

    status = await client.patch(
        f"/api/v1/service-orders/{order_id}/status",
        json={"status": "kesifte"},
        headers={**HEADERS, "X-Request-ID": "kd-durum"},
    )
    assert status.status_code == 200, status.text
    (durum,) = await _events(factory, "kd-durum")
    assert durum.action == "servis_emri_durum_degisti"
    assert durum.details == {"yeni_durum": "kesifte"}


async def test_no_raw_personal_data_in_any_event(
    client: AsyncClient, factory: async_sessionmaker[AsyncSession]
) -> None:
    async with factory() as session:
        call = await _seed_call(session)
        customer = await session.get(Customer, call.customer_id)
    assert customer is not None
    await client.post(
        f"/api/v1/crm/{call.id}/approve",
        json={"note": "kisisel not"},
        headers={**HEADERS, "X-Request-ID": "kd-kvkk"},
    )
    rows = await _events(factory, "kd-kvkk")
    assert rows
    dump = repr([(r.target_id, r.details, r.actor_role, r.ip, r.request_id) for r in rows])
    for personal in (customer.full_name, customer.phone, "kisisel not"):
        if personal:
            assert personal not in dump


async def test_list_endpoint_filters_and_admin_only(
    client: AsyncClient, factory: async_sessionmaker[AsyncSession]
) -> None:
    owner = uuid4()
    async with factory() as session:
        await record_audit_event(
            session,
            action=AuditAction.ASISTAN_INJECTION,
            actor_id=owner,
            actor_role="tekne_sahibi",
            target_type="assistant",
            outcome=AuditOutcome.REDDEDILDI,
            details={"kural": "girdi_deseni"},
            request_id="kd-liste",
        )
        await session.commit()

    resp = await client.get(
        f"/api/v1/audit-log?action=asistan_injection&actor_id={owner}&outcome=reddedildi",
        headers=HEADERS,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 1 and len(body["items"]) == 1
    item = body["items"][0]
    assert item["actor_id"] == str(owner)
    assert item["actor_role"] == "tekne_sahibi"
    assert item["details"] == {"kural": "girdi_deseni"}
    assert item["request_id"] == "kd-liste"

    none = await client.get(f"/api/v1/audit-log?actor_id={uuid4()}", headers=HEADERS)
    assert none.json()["total"] == 0

    forbidden = await client.get("/api/v1/audit-log", headers={**HEADERS, "X-User-Id": str(owner)})
    assert forbidden.status_code == 403

    # Görüntüleme de kaydedilir.
    viewed = [e for e in await _events(factory) if e.action == "denetim_goruntulendi"]
    assert viewed and viewed[-1].target_type == "audit_log"


async def test_assistant_safety_trigger_is_recorded(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    async with factory() as session:
        customer_id = await session.scalar(select(Customer.id).limit(1))
        assert isinstance(customer_id, UUID)
        question = "DROP TABLE customers"
        answer = await answer_question(
            AssistantRequest(question=question, owner_id=str(customer_id)), session=session
        )
        assert answer.question_type.value == "kapsam_disi"
        await session.commit()  # sohbet turu da işlemi böyle kapatır

    events = [e for e in await _events(factory) if e.action == "asistan_injection"]
    assert events
    last = events[-1]
    assert last.actor_id == customer_id and last.actor_role == "tekne_sahibi"
    assert last.outcome == "reddedildi"
    assert "customers" not in repr(last.details) and "DROP" not in repr(last.details)
