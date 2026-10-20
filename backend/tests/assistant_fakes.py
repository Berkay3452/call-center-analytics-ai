# ruff: noqa: E501
"""Çevrimdışı birim testleri için sahte tekne verisi ve sahte araçlar (#22, #50).

Üretim kodu gerçek veritabanını kullanır (#27, #26). Bu modül yalnızca `tests/test_assistant.py`
içinde, veritabanı olmadan akışı (planlayıcı, cevap kurma, kaynak kontrolü) denemek için
`install(monkeypatch)` ile araçların ve aramanın yerine konur. Tüm erişim `owner_id` iledir.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

import pytest

from app.agents.grounding import normalize
from app.assistant import assistant as assistant_module
from app.assistant import tools
from app.assistant.retrieval import Passage
from app.assistant.tools import ExpenseTotal, LastMaintenance, OwnerRequiredError, RemainingPackage
from app.schemas.assistant import SourceRef


@dataclass(frozen=True)
class Boat:
    boat_id: str
    name: str
    model: str


@dataclass(frozen=True)
class ServiceRecord:
    record_id: str
    boat_id: str
    on: date
    category: str
    job: str
    craftsman: str


@dataclass(frozen=True)
class BoatNote:
    record_id: str
    boat_id: str
    on: date
    text: str


@dataclass(frozen=True)
class Expense:
    record_id: str
    boat_id: str
    on: date
    amount: Decimal
    description: str


@dataclass(frozen=True)
class Subscription:
    record_id: str
    plan: str
    total: int
    used: int
    ends_on: date


@dataclass(frozen=True)
class OwnerData:
    boats: list[Boat] = field(default_factory=list)
    services: list[ServiceRecord] = field(default_factory=list)
    notes: list[BoatNote] = field(default_factory=list)
    expenses: list[Expense] = field(default_factory=list)
    subscription: Subscription | None = None


_OWNERS: dict[str, OwnerData] = {
    "owner-001": OwnerData(
        boats=[Boat("boat-001", "Poyraz", "Motoryat 42")],
        services=[
            ServiceRecord(
                "srv-101",
                "boat-001",
                date(2026, 8, 15),
                "makine",
                "250 saatlik periyodik bakım",
                "Mehmet Şimşek",
            ),
            ServiceRecord(
                "srv-102",
                "boat-001",
                date(2026, 3, 10),
                "elektrik_elektronik",
                "Akü grubu değişimi",
                "Hakan Aksoy",
            ),
        ],
        notes=[
            BoatNote(
                "note-101",
                "boat-001",
                date(2026, 8, 15),
                "Ana makine 250 saatlik bakımı tamamlandı, impeller yenilendi. Altı ay sonra yakıt filtresi kontrolü önerilir.",
            ),
            BoatNote(
                "note-102",
                "boat-001",
                date(2026, 3, 10),
                "Servis aküleri değiştirildi. Şarj regülatörü normal çalışıyor, bir sonraki akü kontrolü sezon sonunda yapılmalı.",
            ),
            BoatNote(
                "note-103",
                "boat-001",
                date(2026, 8, 15),
                "Sintine pompası şamandırası temizlendi, çalışma testi başarılı.",
            ),
        ],
        expenses=[
            Expense(
                "exp-101", "boat-001", date(2026, 8, 15), Decimal("18500.00"), "Periyodik bakım"
            ),
            Expense(
                "exp-102",
                "boat-001",
                date(2026, 10, 1),
                Decimal("14250.00"),
                "Marina bağlama ve elektrik/su",
            ),
            Expense(
                "exp-103", "boat-001", date(2026, 3, 10), Decimal("9200.00"), "Akü grubu değişimi"
            ),
        ],
        subscription=Subscription("sub-101", "Gold", total=2, used=1, ends_on=date(2027, 3, 31)),
    ),
    "owner-002": OwnerData(
        boats=[Boat("boat-002", "Albatros", "Beneteau Oceanis 45")],
        services=[
            ServiceRecord(
                "srv-201",
                "boat-002",
                date(2026, 6, 2),
                "makine",
                "Yakıt filtresi ve enjektör temizliği",
                "Selim Kaya",
            ),
        ],
        notes=[
            BoatNote(
                "note-201",
                "boat-002",
                date(2026, 6, 2),
                "Yakıt filtresi tıkanmıştı, değiştirildi. Enjektörler temizlendi, devir sorunu giderildi.",
            ),
        ],
        expenses=[
            Expense(
                "exp-201", "boat-002", date(2026, 6, 2), Decimal("6400.00"), "Yakıt sistemi servisi"
            ),
        ],
        subscription=None,
    ),
}


def get_owner_data(owner_id: str) -> OwnerData:
    """Tekne sahibinin kayıtları; bilinmeyen kullanıcı için boş veri (başkasınınki asla)."""
    return _OWNERS.get(owner_id, OwnerData())


def require_owner(owner_id: str) -> OwnerData:
    if not owner_id or not str(owner_id).strip():
        raise OwnerRequiredError("owner_id zorunludur.")
    return get_owner_data(str(owner_id).strip())


def _own_boat_ids(data: OwnerData, boat_id: str | None) -> set[str]:
    ids = {b.boat_id for b in data.boats}
    return ids if boat_id is None else ids & {boat_id}


async def get_expense_total(
    owner_id: str,
    *,
    start: date | None = None,
    end: date | None = None,
    boat_id: str | None = None,
    session: object = None,
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


async def get_remaining_package(
    owner_id: str, *, boat_id: str | None = None, session: object = None
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


async def get_last_maintenance(
    owner_id: str,
    *,
    boat_id: str | None = None,
    category: str | None = None,
    session: object = None,
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


_STOP = frozenset(
    {"bir", "bu", "şu", "ve", "ile", "mi", "mı", "mu", "mü", "de", "da", "için", "ne", "neden"}
    | {"nasıl", "zaman", "hangi", "var", "yok", "son", "yapıldı", "yapmalıyım", "oldu", "olur"}
    | {"gerekir", "benim", "bana", "senin"}
)


def _tokens(text: str) -> set[str]:
    return {t for t in normalize(text).split() if len(t) > 2 and t not in _STOP}


async def search_boat_notes(
    owner_id: str,
    query: str,
    *,
    limit: int = 3,
    session: object = None,
    embedder: object = None,
) -> list[Passage]:
    """Sorguyla en çok kelime paylaşan kayıtlar; eşleşme yoksa boş liste."""
    data = require_owner(owner_id)
    wanted = {t[:5] for t in _tokens(query)}
    scored: list[tuple[int, Passage]] = []
    for note in data.notes:
        score = len(wanted & {t[:5] for t in _tokens(note.text)})
        if score:
            scored.append(
                (
                    score,
                    Passage(
                        source=SourceRef(
                            kind="boat_note",
                            record_id=note.record_id,
                            title=f"{note.on.strftime('%d.%m.%Y')} usta notu",
                            date=note.on,
                            excerpt=note.text,
                        ),
                        text=note.text,
                    ),
                )
            )
    scored.sort(key=lambda x: (-x[0], x[1].source.record_id))
    return [p for _, p in scored[:limit]]


async def get_upcoming_maintenance(
    owner_id: str, *, today: date, session: object = None
) -> list[object]:
    """Çevrimdışı testlerde yaklaşan iş yoktur; kurallar gerçek veritabanında denenir (#125)."""
    require_owner(owner_id)
    return []


def install(monkeypatch: pytest.MonkeyPatch) -> None:
    """Araçların ve aramanın yerine sahte sürümlerini koyar (yalnızca bu test oturumunda)."""
    monkeypatch.setattr(tools, "get_expense_total", get_expense_total)
    monkeypatch.setattr(tools, "get_remaining_package", get_remaining_package)
    monkeypatch.setattr(tools, "get_last_maintenance", get_last_maintenance)
    monkeypatch.setattr(tools, "get_upcoming_maintenance", get_upcoming_maintenance)
    monkeypatch.setattr(assistant_module, "search_boat_notes", search_boat_notes)
