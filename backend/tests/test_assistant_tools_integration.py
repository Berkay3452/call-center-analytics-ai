"""Miço AI hazır araçları gerçek veritabanı entegrasyon testleri (#27).

Yalnızca `RUN_DB_TESTS=1` iken çalışır.
Test edilen kurallar:
- Üç araç gerçek tablolarla (expenses, subscriptions, service_orders, boats, craftsmen) çalışır.
- Yetki: her sorgu `owner_id` ile süzülür; başka kullanıcının teknesi hiçbir koşulda dönmez.
- Kayıt yokken net sonuç döner (toplam 0 veya None).
- Sonuçlar `sources` listesiyle döner (arayüz kartı için).
- Parametreli sorgu ile SQL enjeksiyonuna karşı tam korumalıdır.
"""

import os
from collections.abc import AsyncIterator
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.assistant import tools
from app.assistant.assistant import answer_question
from app.assistant.llm import AssistantLLM
from app.core.config import Settings
from app.schemas.assistant import AssistantRequest, QuestionType
from tests.llm_fakes import scripted

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_DB_TESTS") != "1", reason="RUN_DB_TESTS=1 değil (gerçek veritabanı gerekir)"
)

# Seed verisindeki bilinen tekne sahipleri ve tekneleri (#23 deterministik tohum)
AHMET_ID = UUID("606bd734-644f-5c21-af2f-dc734c4ecd67")  # Ahmet Yılmaz
POYRAZ_ID = UUID("289ee4a4-2598-5e69-8907-b044be2f85e5")  # Poyraz (Ahmet'in teknesi)

FATMA_ID = UUID("8ff32870-b5ca-5689-a6af-3548246f014e")  # Fatma Kaya
ALBATROS_ID = UUID("1a2239f0-0dcc-5987-bd4f-c0d53da4c47e")  # Albatros (Fatma'nın teknesi)

BURAK_ID = UUID("c57e2519-87f4-597e-be0c-80889768255a")  # Burak Çelik
RUZGAR_ID = UUID("69dc9a93-16f8-582c-bb29-377971e819ca")  # Rüzgar (Burak'ın teknesi)

TODAY = date(2026, 10, 12)


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
def session_factory(conn: AsyncConnection) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )


# --- 1. Gider Toplamı (get_expense_total) ---


async def test_get_expense_total_real_db(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        # Ahmet Yılmaz'ın tüm giderleri
        ahmet_total = await tools.get_expense_total(str(AHMET_ID), session=session)
        assert ahmet_total.item_count >= 3
        assert ahmet_total.total_try > Decimal("40000.00")
        assert len(ahmet_total.sources) == ahmet_total.item_count

        # Ekim 2026 tarih filtresi
        october = await tools.get_expense_total(
            str(AHMET_ID),
            start=date(2026, 10, 1),
            end=date(2026, 10, 31),
            session=session,
        )
        assert october.item_count == 1
        assert october.total_try == Decimal("14250.00")
        assert len(october.sources) == 1
        src = october.sources[0]
        assert src.kind == "expense"
        assert src.date == date(2026, 10, 1)
        assert src.excerpt is not None and "14,250.00 TL" in src.excerpt

        # Kendi teknesiyle sorgulama (Ahmet'in 2 teknesi var; Poyraz'a ait 5 gider filtrelenir)
        poyraz_total = await tools.get_expense_total(
            str(AHMET_ID), boat_id=str(POYRAZ_ID), session=session
        )
        assert poyraz_total.item_count == 5
        assert poyraz_total.total_try == Decimal("96100.00")
        assert poyraz_total.item_count < ahmet_total.item_count

        # Fatma Kaya'nın giderleri
        fatma_total = await tools.get_expense_total(str(FATMA_ID), session=session)
        assert fatma_total.item_count == 4
        assert fatma_total.total_try == Decimal("54350.00")

        # İki kullanıcının gider kaynakları kesinlikle kesişmez (yetki kanıtı)
        ahmet_records = {s.record_id for s in ahmet_total.sources}
        fatma_records = {s.record_id for s in fatma_total.sources}
        assert ahmet_records.isdisjoint(fatma_records)


async def test_get_expense_total_cross_owner_isolation(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Ahmet, Fatma'nın teknesi Albatros için sorgu yaparsa 0 kayıt döner."""
    async with session_factory() as session:
        result = await tools.get_expense_total(
            str(AHMET_ID), boat_id=str(ALBATROS_ID), session=session
        )
        assert result.item_count == 0
        assert result.total_try == Decimal("0")
        assert result.sources == []

        # Fatma da Ahmet'in teknesi Poyraz için sorgu yaparsa 0 kayıt döner
        result2 = await tools.get_expense_total(
            str(FATMA_ID), boat_id=str(POYRAZ_ID), session=session
        )
        assert result2.item_count == 0
        assert result2.total_try == Decimal("0")


# --- 2. Kalan Paket Hakkı (get_remaining_package) ---


async def test_get_remaining_package_real_db(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        # Ahmet Yılmaz'ın Gold paketi var (2 toplam, 1 kullanılmış, 1 kalan, bitiş 2027-03-31)
        pkg = await tools.get_remaining_package(str(AHMET_ID), session=session)
        assert pkg is not None
        assert pkg.plan == "Gold"
        assert pkg.remaining == 1
        assert pkg.total == 2
        assert pkg.ends_on == date(2027, 3, 31)
        assert len(pkg.sources) == 1
        src = pkg.sources[0]
        assert src.kind == "subscription"
        assert src.title == "Gold paket"
        assert src.excerpt is not None and "1/2 bakım hakkı kullanıldı" in src.excerpt

        # Burak Çelik'in Miço Başlangıç paketi var (2 toplam, 0 kullanılmış, 2 kalan)
        burak_pkg = await tools.get_remaining_package(str(BURAK_ID), session=session)
        assert burak_pkg is not None
        assert burak_pkg.plan == "Miço Başlangıç"
        assert burak_pkg.remaining == 2
        assert burak_pkg.total == 2
        assert burak_pkg.ends_on == date(2027, 1, 1)

        # Fatma Kaya'nın aboneliği yok -> None döner
        fatma_pkg = await tools.get_remaining_package(str(FATMA_ID), session=session)
        assert fatma_pkg is None


async def test_get_remaining_package_cross_owner_isolation(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Ahmet, başkasının teknesi için paket sorarsa None döner."""
    async with session_factory() as session:
        pkg = await tools.get_remaining_package(
            str(AHMET_ID), boat_id=str(ALBATROS_ID), session=session
        )
        assert pkg is None


# --- 3. Son Bakım Tarihi (get_last_maintenance) ---


async def test_get_last_maintenance_real_db(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        # Ahmet Yılmaz'ın son bakımı: 2026-08-15, 250 saatlik periyodik bakım, Mehmet Şimşek, Poyraz
        last = await tools.get_last_maintenance(str(AHMET_ID), session=session)
        assert last is not None
        assert last.on == date(2026, 8, 15)
        assert last.boat_name == "Poyraz"
        assert "250 saatlik periyodik bakım" in last.job
        assert last.craftsman == "Mehmet Şimşek"
        assert len(last.sources) == 1
        src = last.sources[0]
        assert src.kind == "service_record"
        assert src.date == date(2026, 8, 15)
        assert src.excerpt is not None and "250 saatlik periyodik bakım" in src.excerpt

        # Kategori filtresi: elektrik_elektronik
        elec = await tools.get_last_maintenance(
            str(AHMET_ID), category="elektrik_elektronik", session=session
        )
        assert elec is not None
        assert elec.on == date(2026, 3, 10)
        assert elec.job == "Akü grubu değişimi"
        assert elec.craftsman == "Hakan Aksoy"

        # Kategori filtresi: iklimlendirme (Ahmet'te yok) -> None döner
        assert (
            await tools.get_last_maintenance(
                str(AHMET_ID), category="iklimlendirme", session=session
            )
            is None
        )

        # Fatma Kaya'nın son bakımı: 2026-06-02, Albatros, Selim Kaya
        fatma_last = await tools.get_last_maintenance(str(FATMA_ID), session=session)
        assert fatma_last is not None
        assert fatma_last.on == date(2026, 6, 2)
        assert fatma_last.boat_name == "Albatros"
        assert fatma_last.craftsman == "Selim Kaya"


async def test_get_last_maintenance_cross_owner_isolation(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Başka kullanıcının teknesiyle bakım sorulduğunda None döner."""
    async with session_factory() as session:
        assert (
            await tools.get_last_maintenance(
                str(AHMET_ID), boat_id=str(ALBATROS_ID), session=session
            )
            is None
        )
        assert (
            await tools.get_last_maintenance(str(FATMA_ID), boat_id=str(POYRAZ_ID), session=session)
            is None
        )


# --- 4. Bilinmeyen veya Geçersiz Kullanıcılar ---


async def test_unknown_owner_returns_empty_in_real_db(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    random_owner = str(uuid4())
    async with session_factory() as session:
        exps = await tools.get_expense_total(random_owner, session=session)
        assert exps.item_count == 0 and exps.total_try == Decimal("0") and exps.sources == []

        pkg = await tools.get_remaining_package(random_owner, session=session)
        assert pkg is None

        last = await tools.get_last_maintenance(random_owner, session=session)
        assert last is None


@pytest.mark.parametrize("invalid_owner", ["", "   "])
async def test_empty_owner_raises_error(invalid_owner: str) -> None:
    with pytest.raises(tools.OwnerRequiredError):
        await tools.get_expense_total(invalid_owner)
    with pytest.raises(tools.OwnerRequiredError):
        await tools.get_remaining_package(invalid_owner)
    with pytest.raises(tools.OwnerRequiredError):
        await tools.get_last_maintenance(invalid_owner)


# --- 5. answer_question Uçtan Uca Gerçek Oturumla ---


async def test_answer_question_numeric_with_real_db_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    llm = AssistantLLM(model=scripted())  # Sayısal soruda LLM çağrılmaz
    async with session_factory() as session:
        # 1. Bu ay ne kadar harcadım?
        res1 = await answer_question(
            AssistantRequest(owner_id=str(AHMET_ID), question="Bu ay ne kadar harcadım?"),
            llm=llm,
            today=TODAY,
            session=session,
        )
        assert res1.question_type == QuestionType.SAYISAL
        assert res1.found is True
        assert "Ekim 2026 döneminde toplam giderleriniz 14.250,00 TL (1 kalem)." in res1.answer
        assert len(res1.sources) == 1

        # 2. Kaç bakım hakkım kaldı?
        res2 = await answer_question(
            AssistantRequest(owner_id=str(AHMET_ID), question="Kaç bakım hakkım kaldı?"),
            llm=llm,
            today=TODAY,
            session=session,
        )
        assert res2.question_type == QuestionType.SAYISAL
        assert res2.found is True
        assert "Gold paketinizde 1 bakım hakkınız kaldı" in res2.answer
        assert "31 Mart 2027" in res2.answer

        # 3. Son bakım ne zaman yapıldı?
        res3 = await answer_question(
            AssistantRequest(owner_id=str(AHMET_ID), question="Son bakım ne zaman yapıldı?"),
            llm=llm,
            today=TODAY,
            session=session,
        )
        assert res3.question_type == QuestionType.SAYISAL
        assert res3.found is True
        assert "Poyraz için son bakım 15 Ağustos 2026 tarihinde yapıldı" in res3.answer
        assert "Mehmet Şimşek" in res3.answer


async def test_tools_standalone_without_session() -> None:
    """Session geçilmediğinde araçlar worker_session açarak DB'yi başarıyla sorgular."""
    october = await tools.get_expense_total(
        str(AHMET_ID),
        start=date(2026, 10, 1),
        end=date(2026, 10, 31),
    )
    assert october.item_count == 1
    assert october.total_try == Decimal("14250.00")

    pkg = await tools.get_remaining_package(str(AHMET_ID))
    assert pkg is not None and pkg.plan == "Gold"

    last = await tools.get_last_maintenance(str(AHMET_ID))
    assert last is not None and last.boat_name == "Poyraz"
