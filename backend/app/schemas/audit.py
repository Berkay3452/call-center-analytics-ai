"""Denetim günlüğü şemaları (#267). Sözleşme: docs/api.md `GET /audit-log`."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.audit import AuditAction, AuditActorRole, AuditOutcome


class AuditLogItem(BaseModel):
    """Tek denetim kaydı. Kişisel veri içermez: kimlik, tür ve sabit değerler."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    occurred_at: datetime
    actor_id: UUID | None = None
    actor_role: AuditActorRole | None = None
    action: AuditAction
    target_type: str | None = None
    target_id: str | None = None
    outcome: AuditOutcome
    request_id: str | None = None
    ip: str | None = None
    details: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class AuditLogFilters(BaseModel):
    """`GET /audit-log` sorgu parametreleri. Hepsi isteğe bağlıdır; en yeni kayıt başta gelir."""

    action: AuditAction | None = None
    outcome: AuditOutcome | None = None
    actor_id: UUID | None = None
    target_type: str | None = Field(default=None, max_length=64)
    target_id: str | None = Field(default=None, max_length=64)
    since: datetime | None = Field(default=None, description="Bu andan itibaren (dahil, UTC).")
    until: datetime | None = Field(default=None, description="Bu ana kadar (hariç, UTC).")
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    @model_validator(mode="after")
    def _range_ordered(self) -> "AuditLogFilters":
        if self.since and self.until and self.until <= self.since:
            raise ValueError("until, since'ten sonra olmalıdır.")
        return self
