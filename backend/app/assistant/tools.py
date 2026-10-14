"""Hazır araçlar: sayısal sorular için hesabı kod yapar, LLM sayı uydurmaz.

BU DOSYA #27'DE (Melih) GERÇEK VERİTABANI SORGULARIYLA DOLDURULACAK. Fonksiyon imzaları ve
dönüş tipleri sözleşmedir; yalnızca gövdeler değişir (şimdilik `fake_data` okunur).

Kurallar (her araç için):
- `owner_id` ilk ve zorunlu parametredir; boşsa `OwnerRequiredError`. Yetki burada, kodda
  uygulanır, prompt'a bırakılmaz.
- Başka bir tekne sahibinin teknesi/kaydı hiçbir koşulda dönmez; `boat_id` verilse bile o
  sahibe ait değilse kayıt yokmuş gibi davranılır.
- Kayıt yoksa istisna değil `None` (veya toplamı 0 olan sonuç) döner; asistan
  "bulamadım" diyebilsin.
- Sonuçlar, hesabın dayandığı kayıtları `sources` ile taşır (arayüzde kaynak kartı olur).
- Araçlar bağımsız, saf fonksiyonlardır (ileride MCP'ye sarılabilir).
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.assistant.fake_data import OwnerData, get_owner_data
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
    if not owner_id or not owner_id.strip():
        raise OwnerRequiredError("owner_id zorunludur.")
    return get_owner_data(owner_id.strip())


def _own_boat_ids(data: OwnerData, boat_id: str | None) -> set[str]:
    """Sahibin tekneleri; `boat_id` verilmişse ve sahibe ait değilse boş küme."""
    ids = {b.boat_id for b in data.boats}
    return ids if boat_id is None else ids & {boat_id}


def get_expense_total(
    owner_id: str,
    *,
    start: date | None = None,
    end: date | None = None,
    boat_id: str | None = None,
) -> ExpenseTotal:
    """Tarih aralığındaki (uçlar dahil) gider toplamı. Kayıt yoksa toplam 0 ve 0 kalem."""
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


def get_remaining_package(owner_id: str, *, boat_id: str | None = None) -> RemainingPackage | None:
    """Abonelik/paketteki kalan bakım hakkı; paket yoksa `None`."""
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


def get_last_maintenance(
    owner_id: str,
    *,
    boat_id: str | None = None,
    category: str | None = None,
) -> LastMaintenance | None:
    """En son servis kaydı (isteğe bağlı kategoriyle); kayıt yoksa `None`."""
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
