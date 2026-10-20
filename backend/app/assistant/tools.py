"""Hazır araçlar: sayısal sorular için hesabı kod yapar, LLM sayı uydurmaz (#27).

Gerçek veritabanı sorguları (PostgreSQL / Supabase):
- `get_expense_total`: Tarih aralığı ve isteğe bağlı tekneye göre gider toplamı.
- `get_remaining_package`: Abonelik/paketteki kalan bakım hakkı ve bitiş tarihi.
- `get_last_maintenance`: En son tamamlanan servis kaydı (isteğe bağlı tekne/kategoriyle).
- `get_upcoming_maintenance`: Yakında yapılması gerekenler: açık servis emirleri, periyodik
  bakım kuralları, usta notlarındaki "N ay sonra" önerileri, bitmek üzere olan paket (#125).

Kurallar:
- `owner_id` ilk ve zorunlu parametredir; boşsa `OwnerRequiredError`. Yetki burada, kodda
  uygulanır, prompt'a bırakılmaz.
- Başka bir tekne sahibinin teknesi/kaydı hiçbir koşulda dönmez; `boat_id` verilse bile o
  sahibe ait değilse kayıt yokmuş gibi davranılır.
- Kayıt yoksa istisna değil `None` (veya toplamı 0 olan `ExpenseTotal`) döner; asistan
  "bulamadım" diyebilsin.
- Sonuçlar, hesabın dayandığı kayıtları `sources` ile taşır (arayüzde kaynak kartı olur).
- Parametreli sorgu kullanılır (SQLAlchemy ORM/Core; SQL enjeksiyonuna karşı tam korumalı).
- Üretimde sahte veri yoktur; çevrimdışı birim testleri araçları
  `tests/assistant_fakes.py` ile değiştirir.
"""

import calendar
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant.formatting import format_date, format_try
from app.core.config import Settings
from app.db.models.external import (
    Boat,
    BoatNote,
    Craftsman,
    Expense,
    ServiceOrder,
    Subscription,
)
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


def require_owner(owner_id: str) -> str:
    """`owner_id` kontrolü: boşsa `OwnerRequiredError` fırlatır; temizlenmiş değeri döner."""
    if not owner_id or not str(owner_id).strip():
        raise OwnerRequiredError("owner_id zorunludur.")
    return str(owner_id).strip()


def _parse_uuid(val: str | UUID | None) -> UUID | None:
    if val is None:
        return None
    if isinstance(val, UUID):
        return val
    try:
        return UUID(str(val).strip())
    except (ValueError, AttributeError):
        return None


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
            excerpt=format_try(Decimal(str(e.amount))),
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
    clean_owner = require_owner(owner_id)

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
    clean_owner = require_owner(owner_id)

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
    clean_owner = require_owner(owner_id)

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


# --- Yaklaşan bakım (#125) ----------------------------------------------------------------------

# Bugünden ileri ve geri bakılan pencere (gün); gecikmiş öneriler de yapılması gereken sayılır.
UPCOMING_HORIZON_DAYS = 120
OVERDUE_WINDOW_DAYS = 90
SUBSCRIPTION_WARN_DAYS = 30
PERIODIC_MONTHS = {"makine": 12, "tekne_guvenligi": 12}
PERIODIC_LABELS = {
    "makine": "Ana makine yıllık periyodik bakımı",
    "tekne_guvenligi": "Can salı ve güvenlik ekipmanı yıllık kontrolü",
}
_OPEN_STATUS_LABELS = {
    ServiceOrderStatus.YENI_ATANDI.value: "usta atandı",
    ServiceOrderStatus.KESIFTE.value: "keşifte",
    ServiceOrderStatus.ONAYLANDI.value: "onaylandı",
    ServiceOrderStatus.DEVAM_EDIYOR.value: "devam ediyor",
}
_NUMBER_WORDS = {
    "bir": 1, "iki": 2, "üç": 3, "dört": 4, "beş": 5, "altı": 6,
    "yedi": 7, "sekiz": 8, "dokuz": 9, "on": 10, "on bir": 11, "on iki": 12,
}  # fmt: skip
_AFTER = re.compile(
    r"(\d{1,2}|on iki|on bir|bir|iki|üç|dört|beş|altı|yedi|sekiz|dokuz|on)\s+(ay|yıl)\s+sonra",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class UpcomingItem:
    """Yaklaşan (veya gecikmiş) iş: ne, ne zaman, neden ve dayandığı kayıt."""

    boat_name: str
    what: str
    due_on: date | None
    reason: str
    overdue: bool = False
    sources: list[SourceRef] = field(default_factory=list)


def add_months(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    year, month = d.year + month_index // 12, month_index % 12 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def note_recommendation(text: str, on: date) -> tuple[str, date] | None:
    """Usta notundaki "altı ay sonra ... kontrol" türü öneriyi (cümle, tarih) olarak çıkarır."""
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        match = _AFTER.search(sentence)
        if match is None:
            continue
        raw = match.group(1).casefold()
        amount = int(raw) if raw.isdigit() else _NUMBER_WORDS[raw]
        months = amount * 12 if match.group(2).casefold() == "yıl" else amount
        return sentence.strip().rstrip("."), add_months(on, months)
    return None


def _in_window(due: date, today: date) -> bool:
    earliest = today - timedelta(days=OVERDUE_WINDOW_DAYS)
    return earliest <= due <= today + timedelta(days=UPCOMING_HORIZON_DAYS)


def _order_source(order: ServiceOrder, on: date | None, title: str) -> SourceRef:
    return SourceRef(
        kind="service_record",
        record_id=str(order.id),
        title=title,
        date=on,
        excerpt=order.description,
    )


async def _get_upcoming_maintenance_db(
    session: AsyncSession, owner_uuid: UUID, today: date
) -> list[UpcomingItem]:
    boat_rows = (await session.scalars(select(Boat).where(Boat.owner_id == owner_uuid))).all()
    boats = {b.id: b.name for b in boat_rows}
    if not boats:
        return []
    items: list[UpcomingItem] = []

    # 1. Açık servis emirleri: zaten planlanmış veya süren işler.
    open_orders = (
        await session.scalars(
            select(ServiceOrder)
            .where(
                ServiceOrder.boat_id.in_(boats),
                ServiceOrder.status != ServiceOrderStatus.TAMAMLANDI.value,
            )
            .order_by(ServiceOrder.scheduled_at.asc().nullslast())
        )
    ).all()
    for order in open_orders:
        on = order.scheduled_at.date() if order.scheduled_at else None
        status = _OPEN_STATUS_LABELS.get(order.status, order.status)
        items.append(
            UpcomingItem(
                boat_name=boats[order.boat_id],
                what=order.description or "Servis işi",
                due_on=on,
                reason=f"açık servis emri, durum: {status}",
                sources=[_order_source(order, on, f"Açık servis emri ({status})")],
            )
        )

    # 2. Periyodik bakım: kategoride son tamamlanan işten itibaren kural süresi.
    done = (
        await session.scalars(
            select(ServiceOrder)
            .where(
                ServiceOrder.boat_id.in_(boats),
                ServiceOrder.status == ServiceOrderStatus.TAMAMLANDI.value,
                ServiceOrder.category.in_(PERIODIC_MONTHS),
            )
            .order_by(ServiceOrder.completed_at.desc().nullslast())
        )
    ).all()
    seen: set[tuple[UUID, str]] = set()
    for order in done:
        if order.completed_at is None or order.category is None:
            continue
        key = (order.boat_id, order.category)
        if key in seen:
            continue  # yalnızca kategorideki en son iş
        seen.add(key)
        last = order.completed_at.date()
        due = add_months(last, PERIODIC_MONTHS[order.category])
        if _in_window(due, today):
            items.append(
                UpcomingItem(
                    boat_name=boats[order.boat_id],
                    what=PERIODIC_LABELS[order.category],
                    due_on=due,
                    reason=f"son bakım {format_date(last)}, yıllık periyot",
                    overdue=due < today,
                    sources=[_order_source(order, last, f"{last:%d.%m.%Y} servis kaydı")],
                )
            )

    # 3. Usta notlarındaki "N ay/yıl sonra" önerileri.
    notes = (
        await session.scalars(
            select(BoatNote)
            .where(BoatNote.boat_id.in_(boats), BoatNote.note_date.is_not(None))
            .order_by(BoatNote.note_date.desc())
        )
    ).all()
    for note in notes:
        if note.note_date is None:
            continue
        found = note_recommendation(note.content, note.note_date)
        if found is None:
            continue
        sentence, due = found
        if _in_window(due, today):
            items.append(
                UpcomingItem(
                    boat_name=boats[note.boat_id],
                    what=sentence,
                    due_on=due,
                    reason=f"usta notu, {format_date(note.note_date)}",
                    overdue=due < today,
                    sources=[
                        SourceRef(
                            kind="boat_note",
                            record_id=str(note.id),
                            title=f"{note.note_date:%d.%m.%Y} usta notu",
                            date=note.note_date,
                            excerpt=note.content,
                        )
                    ],
                )
            )

    # 4. Yakında biten abonelik/paket.
    subs = (
        await session.scalars(
            select(Subscription).where(
                Subscription.customer_id == owner_uuid,
                Subscription.expires_at.is_not(None),
                Subscription.expires_at >= today,
                Subscription.expires_at <= today + timedelta(days=SUBSCRIPTION_WARN_DAYS),
            )
        )
    ).all()
    for sub in subs:
        if sub.expires_at is None:
            continue
        items.append(
            UpcomingItem(
                boat_name=boats.get(sub.boat_id, "") if sub.boat_id else "",
                what=f"{sub.plan_name} paketinin yenilenmesi",
                due_on=sub.expires_at,
                reason=f"paket {format_date(sub.expires_at)} tarihinde bitiyor",
                sources=[
                    SourceRef(
                        kind="subscription",
                        record_id=str(sub.id),
                        title=f"{sub.plan_name} paket",
                        date=sub.expires_at,
                        excerpt=f"{sub.used_services}/{sub.total_services} bakım hakkı kullanıldı",
                    )
                ],
            )
        )

    items.sort(key=lambda i: (i.due_on is None, i.due_on or today))
    return items


async def get_upcoming_maintenance(
    owner_id: str,
    *,
    today: date,
    session: AsyncSession | None = None,
) -> list[UpcomingItem]:
    """Sahibin teknelerinde yakında (veya gecikmiş) yapılması gerekenler; LLM yok, kurallar."""
    clean_owner = require_owner(owner_id)
    owner_uuid = _parse_uuid(clean_owner)
    if owner_uuid is None:
        return []
    if session is not None:
        return await _get_upcoming_maintenance_db(session, owner_uuid, today)
    async with worker_session(Settings()) as sess:
        return await _get_upcoming_maintenance_db(sess, owner_uuid, today)
