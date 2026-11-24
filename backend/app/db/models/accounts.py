"""Kullanıcı hesapları (docs/db_schema.md §3.11, #278, #368).

Yönetici ve tekne sahibi hesapları AYRI tablolardadır: bir tekne sahibi hesabı hiçbir koşulda
yönetici yetkisi taşıyamaz, iki grubun kilit ve politika ayarı bağımsız değişebilir.
Parola yalnızca argon2id karması olarak saklanır (bkz. `app/services/accounts.py`).
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin


class AdminAccount(UUIDPrimaryKeyMixin, Base):
    """Yönetici (çağrı merkezi/ofis) hesabı."""

    __tablename__ = "admin_accounts"
    __table_args__ = (
        CheckConstraint("username = lower(username) AND length(username) > 0", name="username"),
        CheckConstraint("failed_attempts >= 0", name="failed_attempts"),
        Index("ix_admin_accounts_username", "username", unique=True),
    )

    username: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, server_default=text("true"))
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    password_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class OwnerAccount(UUIDPrimaryKeyMixin, Base):
    """Tekne sahibi hesabı; her müşterinin en fazla bir hesabı olur."""

    __tablename__ = "owner_accounts"
    __table_args__ = (
        CheckConstraint("username = lower(username) AND length(username) > 0", name="username"),
        CheckConstraint("failed_attempts >= 0", name="failed_attempts"),
        Index("ix_owner_accounts_username", "username", unique=True),
        Index("ix_owner_accounts_customer_id", "customer_id", unique=True),
    )

    username: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(nullable=False, server_default=text("true"))
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    password_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
