"""Denetim günlüğü tablosu (docs/db_schema.md §3.10, #267).

Yalnızca eklenir: veritabanı tetikleyicisi UPDATE, DELETE ve TRUNCATE'i reddeder (migration 0006).
Kişisel veri yazılmaz; yalnızca kimlikler, türler ve sabit değerler (bkz. `app/services/audit.py`).
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin
from app.db.checks import in_enum
from app.domain.audit import AuditOutcome


class AuditLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        in_enum("outcome", AuditOutcome, nullable=False),
        Index("ix_audit_log_occurred_at", "occurred_at"),
        Index("ix_audit_log_action_occurred_at", "action", "occurred_at"),
        Index("ix_audit_log_actor_id", "actor_id"),
        Index("ix_audit_log_target", "target_type", "target_id"),
    )

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # FK yok: müşteri/çağrı silinse bile denetim izi kalır.
    actor_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    actor_role: Mapped[str | None] = mapped_column(Text)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    target_type: Mapped[str | None] = mapped_column(Text)
    target_id: Mapped[str | None] = mapped_column(Text)
    outcome: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'basarili'"))
    request_id: Mapped[str | None] = mapped_column(Text)
    ip: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
