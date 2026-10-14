"""Miço Usta tarafı tablolar (DIŞ KAYNAK, docs/db_schema.md §4).

Bu tablolar Miço Usta uygulamasınındır; AI servisi canlıda bunları yalnızca OKUR. Geliştirmede
ve testte sentetik veriyle (#23) doldurulmak üzere bizim veritabanımızda da oluşturulur. Gerçek
şema hocadan gelince bu dosya ve migration'ı güncellenir.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin
from app.db.checks import in_enum
from app.domain.enums import RequestCategory, ServiceOrderStatus


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Customer(UUIDPrimaryKeyMixin, Base):
    """Tekne sahipleri (müşteriler)."""

    __tablename__ = "customers"

    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    phone: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    marina: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()


class Boat(UUIDPrimaryKeyMixin, Base):
    """Tekneler; her tekne bir müşteriye (`owner_id`) aittir."""

    __tablename__ = "boats"
    __table_args__ = (Index("ix_boats_owner_id", "owner_id"),)

    owner_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str | None] = mapped_column(Text)
    year: Mapped[int | None] = mapped_column(SmallInteger)
    marina: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()


class Craftsman(UUIDPrimaryKeyMixin, Base):
    """Ustalar (teknisyenler)."""

    __tablename__ = "craftsmen"

    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    specialty: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()


class ServiceOrder(UUIDPrimaryKeyMixin, Base):
    """Servis emirleri; bir teknede yapılacak/yapılmış iş."""

    __tablename__ = "service_orders"
    __table_args__ = (
        in_enum("status", ServiceOrderStatus, nullable=False),
        in_enum("category", RequestCategory),
        Index("ix_orders_boat_id", "boat_id"),
    )

    boat_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("boats.id"), nullable=False
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False
    )
    craftsman_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("craftsmen.id")
    )
    category: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(f"'{ServiceOrderStatus.YENI_ATANDI.value}'")
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created_at()


class BoatNote(UUIDPrimaryKeyMixin, Base):
    """Ustanın tekneye düştüğü notlar (tekne karnesi); Miço AI bunları RAG ile arar."""

    __tablename__ = "boat_notes"
    __table_args__ = (Index("ix_notes_boat_id", "boat_id"),)

    boat_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("boats.id"), nullable=False
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("craftsmen.id")
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    note_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = _created_at()


class Expense(UUIDPrimaryKeyMixin, Base):
    """Tekne giderleri; Miço AI 'bu ay ne kadar harcadım' sorusunu buradan cevaplar."""

    __tablename__ = "expenses"
    __table_args__ = (
        CheckConstraint("amount >= 0", name="amount_non_negative"),
        Index("ix_expenses_boat_id", "boat_id"),
    )

    boat_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("boats.id"), nullable=False
    )
    service_order_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("service_orders.id")
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default=text("'TRY'"))
    description: Mapped[str | None] = mapped_column(Text)
    expense_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = _created_at()


class Subscription(UUIDPrimaryKeyMixin, Base):
    """Bakım paketleri / abonelikler (ör. Miço Başlangıç, Miço Standart, Miço VIP)."""

    __tablename__ = "subscriptions"
    __table_args__ = (
        CheckConstraint(
            "used_services >= 0 AND used_services <= total_services", name="used_within_total"
        ),
        Index("ix_subs_customer_id", "customer_id"),
    )

    customer_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False
    )
    boat_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("boats.id"))
    plan_name: Mapped[str] = mapped_column(Text, nullable=False)
    total_services: Mapped[int] = mapped_column(Integer, nullable=False)
    used_services: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    starts_at: Mapped[date | None] = mapped_column(Date)
    expires_at: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = _created_at()
