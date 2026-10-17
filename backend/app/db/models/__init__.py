"""ORM modelleri: şemanın Python karşılığı (docs/db_schema.md).

Alembic `Base.metadata` üzerinden bu paketi okur; yeni model eklenince buraya da eklenmelidir.
- `ai.py`: AI servisi tabloları
- `external.py`: Miço Usta tarafı tablolar (dış kaynak; canlıda yalnızca okunur)
"""

from app.db.base import Base
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
    "AgentRun",
    "AnalysisResult",
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
    "RagChunk",
    "ServiceOrder",
    "Subscription",
    "Transcript",
    "TranscriptSegment",
]
