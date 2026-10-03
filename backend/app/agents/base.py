"""Ajan sözleşmesi (framework'ten bağımsız).

Her ajan `AnalysisContext` alır, `AgentResult[ÇıktıŞeması]` döner. Ajan hatası orkestratörü
durdurmaz: başarısız ajan `status="failed"` ile döner ve çağrı "kısmi" tamamlanır.
"""

from abc import ABC, abstractmethod
from typing import Any, ClassVar, Literal
from uuid import UUID

from pydantic import BaseModel, Field

Speaker = Literal["rep", "customer", "unknown"]
AgentStatus = Literal["ok", "failed", "skipped"]
ModelTier = Literal["fast", "smart"]


class Segment(BaseModel):
    """Tek konuşmacının kesintisiz konuşma turu. Ajanlar yalnızca maskeli metni görür."""

    idx: int
    speaker: Speaker
    start_ms: int
    end_ms: int
    text_masked: str


class AnalysisContext(BaseModel):
    call_id: UUID
    segments: list[Segment]
    language: str = "tr"
    # Önceki ajanların çıktıları (ör. Şikayet ajanı, Duygu ve Konu çıktılarını kullanır).
    prior: dict[str, Any] = Field(default_factory=dict)


class AgentResult[T: BaseModel](BaseModel):
    agent: str
    status: AgentStatus
    output: T | None = None
    error: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    attempts: int = 1


class BaseAgent[T: BaseModel](ABC):
    """Tüm analiz ajanlarının tabanı.

    Alt sınıflar şunları tanımlar:
    - name           : benzersiz ajan adı (ör. "summarizer")
    - prompt_version : prompt dosyası sürümü (ör. "summary.v1"); önbellek anahtarına girer
    - output_schema  : LLM'den beklenen Pydantic çıktı şeması
    - model_tier     : "fast" veya "smart"
    """

    name: ClassVar[str]
    prompt_version: ClassVar[str]
    output_schema: ClassVar[type[BaseModel]]
    model_tier: ClassVar[ModelTier] = "fast"

    @abstractmethod
    async def run(self, ctx: AnalysisContext) -> AgentResult[T]:
        """Ajanı çalıştırır. İstisna fırlatmak yerine başarısızlığı AgentResult ile bildirir."""
