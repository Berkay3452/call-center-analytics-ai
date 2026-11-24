"""ORM modelleri: şemanın Python karşılığı (docs/db_schema.md).

Alembic `Base.metadata` üzerinden bu paketi okur; yeni model eklenince buraya da eklenmelidir.
- `accounts.py`: kullanıcı hesapları (#278)
- `ai.py`: AI servisi tabloları
- `audit.py`: denetim günlüğü (yalnızca ekleme)
- `external.py`: Miço Usta tarafı tablolar (dış kaynak; canlıda yalnızca okunur)
"""

from app.db.base import Base
from app.db.models.accounts import AdminAccount, OwnerAccount
from app.db.models.ai import (
    AgentRun,
    AnalysisResult,
    Call,
    ChatMessage,
    ChatSession,
    CrmReview,
    RagChunk,
    Transcript,
    TranscriptSegment,
)
from app.db.models.audit import AuditLog
from app.db.models.external import (
    Boat,
    BoatNote,
    Craftsman,
    Customer,
    Expense,
    ServiceOrder,
    Subscription,
)

__all__ = [
    "AdminAccount",
    "AgentRun",
    "AnalysisResult",
    "AuditLog",
    "Base",
    "Boat",
    "BoatNote",
    "Call",
    "ChatMessage",
    "ChatSession",
    "Craftsman",
    "CrmReview",
    "Customer",
    "Expense",
    "OwnerAccount",
    "RagChunk",
    "ServiceOrder",
    "Subscription",
    "Transcript",
    "TranscriptSegment",
]
