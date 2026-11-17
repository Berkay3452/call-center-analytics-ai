"""Kullanıcı hesapları (docs/db_schema.md §3.11, #278).

Her tekne sahibi (`role='owner'`, `customer_id` dolu) ve yönetici (`role='admin'`, `customer_id`
boş) için bir hesap. Parola yalnızca argon2id karması olarak saklanır (bkz.
`app/services/accounts.py`). Giriş ucu henüz açık değildir (giriş ekranı kararı #265'e bağlı).
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin
from app.db.checks import in_enum
from app.domain.accounts import AccountRole


class UserAccount(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "user_accounts"
    __table_args__ = (
        in_enum("role", AccountRole, nullable=False),
        CheckConstraint("username = lower(username) AND length(username) > 0", name="username"),
        CheckConstraint(
            "(role = 'owner' AND customer_id IS NOT NULL) "
            "OR (role = 'admin' AND customer_id IS NULL)",
            name="role_customer",
        ),
        CheckConstraint("failed_attempts >= 0", name="failed_attempts"),
        Index("ix_user_accounts_username", "username", unique=True),
        # Bir tekne sahibinin en fazla bir hesabı olur (yöneticide customer_id NULL, çakışmaz).
        Index("ix_user_accounts_customer_id", "customer_id", unique=True),
    )

    username: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE")
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
