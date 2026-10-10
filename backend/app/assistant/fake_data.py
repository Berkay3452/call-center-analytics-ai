# ruff: noqa: E501
"""Sahte tekne verisi (#22). Gerçek veri Melih'in #23 sentetik verisi ve #27 sorgularıyla gelecek.

Tüm erişim `owner_id` ile yapılır: bir tekne sahibi yalnızca kendi kayıtlarını görür. Bu
modül veritabanının yerine geçtiği için aynı kuralı burada da uygular.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


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
                "periyodik_bakim",
                "250 saatlik periyodik bakım",
                "Mehmet Şimşek",
            ),
            ServiceRecord(
                "srv-102",
                "boat-001",
                date(2026, 3, 10),
                "elektrik_arizasi",
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
                "motor_arizasi",
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
