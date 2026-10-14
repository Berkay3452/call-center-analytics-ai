"""Hazır araçlar: sayısal sorular için hesabı kod yapar, LLM sayı uydurmaz (#27).

Gerçek veritabanı sorguları (PostgreSQL / Supabase):
- `get_expense_total`: Tarih aralığı ve isteğe bağlı tekneye göre gider toplamı.
- `get_remaining_package`: Abonelik/paketteki kalan bakım hakkı ve bitiş tarihi.
- `get_last_maintenance`: En son tamamlanan servis kaydı (isteğe bağlı tekne/kategoriyle).

Kurallar:
- `owner_id` ilk ve zorunlu parametredir; boşsa `OwnerRequiredError`. Yetki burada, kodda
  uygulanır, prompt'a bırakılmaz.
- Başka bir tekne sahibinin teknesi/kaydı hiçbir koşulda dönmez; `boat_id` verilse bile o
  sahibe ait değilse kayıt yokmuş gibi davranılır.
- Kayıt yoksa istisna değil `None` (veya toplamı 0 olan `ExpenseTotal`) döner; asistan
  "bulamadım" diyebilsin.
- Sonuçlar, hesabın dayandığı kayıtları `sources` ile taşır (arayüzde kaynak kartı olur).
- Parametreli sorgu kullanılır (SQLAlchemy ORM/Core; SQL enjeksiyonuna karşı tam korumalı).
- Araçlar bağımsız, saf fonksiyonlardır.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant.fake_data import _OWNERS, OwnerData, get_owner_data
from app.core.config import Settings
from app.db.models.external import Boat, Craftsman, Expense, ServiceOrder, Subscription
from app.db.session import worker_session
from app.domain.enums import ServiceOrderStatus
from app.schemas.assistant import SourceRef


class OwnerRequiredError(PermissionError):
    """`owner_id` verilmeden araç çağrıldı."""


@dataclass(frozen=True)
class ExpenseTotal:
    total_try: Decimal
    item_count: int
    sources: list[SourceRef] = field(default_factory=list)


@dataclass(frozen=True)
class RemainingPackage:
    plan: str
    remaining: int
    total: int
    ends_on: date
    sources: list[SourceRef] = field(default_factory=list)


@dataclass(frozen=True)
class LastMaintenance:
    on: date
    job: str
    craftsman: str
    boat_name: str
    sources: list[SourceRef] = field(default_factory=list)


def require_owner(owner_id: str) -> OwnerData:
    """`owner_id` kontrolü: boşsa `OwnerRequiredError` fırlatır."""
    if not owner_id or not str(owner_id).strip():
        raise OwnerRequiredError("owner_id zorunludur.")
    return get_owner_data(str(owner_id).strip())


def _parse_uuid(val: str | UUID | None) -> UUID | None:
    if val is None:
        return None
    if isinstance(val, UUID):
        return val
    try:
        return UUID(str(val).strip())
    except (ValueError, AttributeError):
        return None


def _own_boat_ids(data: OwnerData, boat_id: str | None) -> set[str]:
    """Sahibin tekneleri (sahte veri); `boat_id` verilmişse ve sahibe ait değilse boş küme."""
    ids = {b.boat_id for b in data.boats}
    return ids if boat_id is None else ids & {boat_id}


# --- Sahte veri yedekleri (çevrimdışı birim testleri ve mock kullanıcılar için) ---


def _get_expense_total_fake(
    owner_id: str,
    *,
    start: date | None = None,
    end: date | None = None,
    boat_id: str | None = None,
) -> ExpenseTotal:
    data = require_owner(owner_id)
    boats = _own_boat_ids(data, boat_id)
    items = [
        e
        for e in data.expenses
        if e.boat_id in boats and (start is None or e.on >= start) and (end is None or e.on <= end)
    ]
    return ExpenseTotal(
        total_try=sum((e.amount for e in items), Decimal("0")),
        item_count=len(items),
        sources=[
            SourceRef(
                kind="expense",
                record_id=e.record_id,
                title=e.description,
                date=e.on,
                excerpt=f"{e.amount:,.2f} TL",
            )
            for e in sorted(items, key=lambda e: e.on)
        ],
    )


def _get_remaining_package_fake(
    owner_id: str,
    *,
    boat_id: str | None = None,
) -> RemainingPackage | None:
    data = require_owner(owner_id)
    sub = data.subscription
    if sub is None or not _own_boat_ids(data, boat_id):
        return None
    return RemainingPackage(
        plan=sub.plan,
        remaining=sub.total - sub.used,
        total=sub.total,
        ends_on=sub.ends_on,
        sources=[
            SourceRef(
                kind="subscription",
                record_id=sub.record_id,
                title=f"{sub.plan} paket",
                date=sub.ends_on,
                excerpt=f"{sub.used}/{sub.total} bakım hakkı kullanıldı",
            )
        ],
    )


def _get_last_maintenance_fake(
    owner_id: str,
    *,
    boat_id: str | None = None,
    category: str | None = None,
) -> LastMaintenance | None:
    data = require_owner(owner_id)
    boats = {b.boat_id: b for b in data.boats if b.boat_id in _own_boat_ids(data, boat_id)}
    records = [
        s
        for s in data.services
        if s.boat_id in boats and (category is None or s.category == category)
    ]
    if not records:
        return None
    last = max(records, key=lambda s: s.on)
    return LastMaintenance(
        on=last.on,
        job=last.job,
        craftsman=last.craftsman,
        boat_name=boats[last.boat_id].name,
        sources=[
            SourceRef(
                kind="service_record",
                record_id=last.record_id,
                title=f"{last.on.strftime('%d.%m.%Y')} servis kaydı",
                date=last.on,
                excerpt=last.job,
            )
        ],
    )


# --- Gerçek Veritabanı Sorguları (#27) ---


async def _get_expense_total_db(
    session: AsyncSession,
    owner_uuid: UUID,
    *,
    start: date | None = None,
    end: date | None = None,
    boat_uuid: UUID | None = None,
) -> ExpenseTotal:
    stmt = select(Expense).join(Boat, Expense.boat_id == Boat.id).where(Boat.owner_id == owner_uuid)

    if boat_uuid is not None:
        stmt = stmt.where(Expense.boat_id == boat_uuid)

    if start is not None:
        stmt = stmt.where(Expense.expense_date >= start)

    if end is not None:
        stmt = stmt.where(Expense.expense_date <= end)

    stmt = stmt.order_by(Expense.expense_date.asc(), Expense.created_at.asc())

    result = await session.execute(stmt)
    expenses = result.scalars().all()

    total_try = sum((Decimal(str(e.amount)) for e in expenses), Decimal("0"))
    sources = [
        SourceRef(
            kind="expense",
            record_id=str(e.id),
            title=e.description or "Gider kaydı",
            date=e.expense_date,
            excerpt=f"{e.amount:,.2f} TL",
        )
        for e in expenses
    ]

    return ExpenseTotal(
        total_try=total_try,
        item_count=len(expenses),
        sources=sources,
    )


async def _get_remaining_package_db(
    session: AsyncSession,
    owner_uuid: UUID,
    *,
    boat_uuid: UUID | None = None,
) -> RemainingPackage | None:
    if boat_uuid is not None:
        boat_owned = await session.scalar(
            select(func.count(Boat.id)).where(
                Boat.id == boat_uuid,
                Boat.owner_id == owner_uuid,
            )
        )
        if not boat_owned:
            return None

    stmt = select(Subscription).where(Subscription.customer_id == owner_uuid)

    if boat_uuid is not None:
        stmt = stmt.where(
            or_(
                Subscription.boat_id == boat_uuid,
                Subscription.boat_id.is_(None),
            )
        )

    stmt = stmt.order_by(
        Subscription.expires_at.desc().nullslast(),
        Subscription.created_at.desc(),
    ).limit(1)

    result = await session.execute(stmt)
    sub = result.scalars().first()

    if sub is None:
        return None

    remaining = max(0, sub.total_services - sub.used_services)
    ends_on = sub.expires_at or sub.created_at.date()

    return RemainingPackage(
        plan=sub.plan_name,
        remaining=remaining,
        total=sub.total_services,
        ends_on=ends_on,
        sources=[
            SourceRef(
                kind="subscription",
                record_id=str(sub.id),
                title=f"{sub.plan_name} paket",
                date=ends_on,
                excerpt=f"{sub.used_services}/{sub.total_services} bakım hakkı kullanıldı",
            )
        ],
    )


async def _get_last_maintenance_db(
    session: AsyncSession,
    owner_uuid: UUID,
    *,
    boat_uuid: UUID | None = None,
    category: str | None = None,
) -> LastMaintenance | None:
    if boat_uuid is not None:
        boat_owned = await session.scalar(
            select(func.count(Boat.id)).where(
                Boat.id == boat_uuid,
                Boat.owner_id == owner_uuid,
            )
        )
        if not boat_owned:
            return None

    stmt = (
        select(ServiceOrder, Boat.name, Craftsman.full_name)
        .join(Boat, ServiceOrder.boat_id == Boat.id)
        .outerjoin(Craftsman, ServiceOrder.craftsman_id == Craftsman.id)
        .where(
            Boat.owner_id == owner_uuid,
            ServiceOrder.status == ServiceOrderStatus.TAMAMLANDI.value,
        )
    )

    if boat_uuid is not None:
        stmt = stmt.where(ServiceOrder.boat_id == boat_uuid)

    if category is not None and category.strip():
        stmt = stmt.where(ServiceOrder.category == category.strip())

    maintenance_date_expr = func.coalesce(
        ServiceOrder.completed_at,
        ServiceOrder.scheduled_at,
        ServiceOrder.created_at,
    )
    stmt = stmt.order_by(maintenance_date_expr.desc()).limit(1)

    result = await session.execute(stmt)
    row = result.first()

    if row is None:
        return None

    order, boat_name, craftsman_name = row
    dt = order.completed_at or order.scheduled_at or order.created_at
    on_date = dt.date() if dt else date.today()
    craftsman = craftsman_name or "Bilinmiyor"
    job = order.description or "Bakım/Onarım"

    return LastMaintenance(
        on=on_date,
        job=job,
        craftsman=craftsman,
        boat_name=boat_name,
        sources=[
            SourceRef(
                kind="service_record",
                record_id=str(order.id),
                title=f"{on_date.strftime('%d.%m.%Y')} servis kaydı",
                date=on_date,
                excerpt=job,
            )
        ],
    )


# --- Dışa Açık Hazır Araçlar ---


async def get_expense_total(
    owner_id: str,
    *,
    start: date | None = None,
    end: date | None = None,
    boat_id: str | None = None,
    session: AsyncSession | None = None,
) -> ExpenseTotal:
    """Tarih aralığındaki (uçlar dahil) gider toplamı. Kayıt yoksa toplam 0 ve 0 kalem."""
    require_owner(owner_id)
    clean_owner = owner_id.strip()

    if session is None and clean_owner in _OWNERS:
        return _get_expense_total_fake(clean_owner, start=start, end=end, boat_id=boat_id)

    owner_uuid = _parse_uuid(clean_owner)
    boat_uuid = _parse_uuid(boat_id)
    if owner_uuid is None or (boat_id is not None and boat_uuid is None):
        return ExpenseTotal(total_try=Decimal("0"), item_count=0, sources=[])

    if session is not None:
        return await _get_expense_total_db(
            session, owner_uuid, start=start, end=end, boat_uuid=boat_uuid
        )

    async with worker_session(Settings()) as sess:
        return await _get_expense_total_db(
            sess, owner_uuid, start=start, end=end, boat_uuid=boat_uuid
        )


async def get_remaining_package(
    owner_id: str,
    *,
    boat_id: str | None = None,
    session: AsyncSession | None = None,
) -> RemainingPackage | None:
    """Abonelik/paketteki kalan bakım hakkı; paket yoksa `None`."""
    require_owner(owner_id)
    clean_owner = owner_id.strip()

    if session is None and clean_owner in _OWNERS:
        return _get_remaining_package_fake(clean_owner, boat_id=boat_id)

    owner_uuid = _parse_uuid(clean_owner)
    boat_uuid = _parse_uuid(boat_id)
    if owner_uuid is None or (boat_id is not None and boat_uuid is None):
        return None

    if session is not None:
        return await _get_remaining_package_db(session, owner_uuid, boat_uuid=boat_uuid)

    async with worker_session(Settings()) as sess:
        return await _get_remaining_package_db(sess, owner_uuid, boat_uuid=boat_uuid)


async def get_last_maintenance(
    owner_id: str,
    *,
    boat_id: str | None = None,
    category: str | None = None,
    session: AsyncSession | None = None,
) -> LastMaintenance | None:
    """En son servis kaydı (isteğe bağlı kategoriyle); kayıt yoksa `None`."""
    require_owner(owner_id)
    clean_owner = owner_id.strip()

    if session is None and clean_owner in _OWNERS:
        return _get_last_maintenance_fake(clean_owner, boat_id=boat_id, category=category)

    owner_uuid = _parse_uuid(clean_owner)
    boat_uuid = _parse_uuid(boat_id)
    if owner_uuid is None or (boat_id is not None and boat_uuid is None):
        return None

    if session is not None:
        return await _get_last_maintenance_db(
            session, owner_uuid, boat_uuid=boat_uuid, category=category
        )

    async with worker_session(Settings()) as sess:
        return await _get_last_maintenance_db(
            sess, owner_uuid, boat_uuid=boat_uuid, category=category
        )
