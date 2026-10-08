"""Agent sözleşmesi (framework'ten bağımsız).

Her agent `AnalysisContext` alır, `AgentResult[ÇıktıŞeması]` döner. Agent hatası orkestratörü
durdurmaz: başarısız agent `status="failed"` ile döner ve çağrı "kısmi" tamamlanır.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, ClassVar, Literal
from uuid import UUID

from pydantic import BaseModel, Field

Speaker = Literal["rep", "customer", "unknown"]
AgentStatus = Literal["ok", "failed", "skipped"]
ModelTier = Literal["fast", "smart"]
# Hatanın türü orkestratörün ne yapacağını belirler:
# - validation : çıktı şemaya uymadı → agent'a hata mesajıyla bir kez düzeltme şansı verilir
# - runtime    : LLM/ağ/kod hatası → tekrar denenmez (ağ tekrarlarını LLM istemcisi zaten yapar)
# - timeout    : agent süre sınırını aştı → tekrar denenmez
AgentErrorKind = Literal["validation", "runtime", "timeout"]


class Segment(BaseModel):
    """Tek konuşmacının kesintisiz konuşma turu. Agent'lar yalnızca maskeli metni görür."""

    idx: int
    speaker: Speaker
    start_ms: int
    end_ms: int
    text_masked: str


class CallInfo(BaseModel):
    """Ses dosyasından çıkmayan çağrı bilgisi (santral/CRM kaydından gelir).

    Ortalama cevap süresi gibi KPI'lar buradan hesaplanır; agent'lar bağlam olarak görebilir.
    """

    started_at: datetime | None = None
    answer_delay_s: float | None = Field(default=None, ge=0, description="Çalma → açılma süresi")
    duration_s: float | None = Field(default=None, ge=0)
    outcome: str | None = Field(default=None, description="Santral/CRM'deki sonuç (ör. geri_ara)")


class AnalysisContext(BaseModel):
    call_id: UUID
    segments: list[Segment]
    call_info: CallInfo | None = None
    language: str = "tr"
    # Önceki aşamadaki agent'ların çıktıları
    # (ör. CRM Bilgi Çıkarım, Çağrı Sınıflandırma'nın çağrı tipini görür).
    prior: dict[str, Any] = Field(default_factory=dict)
    # Önceki denemenin doğrulama hatası. Doluysa agent bunu prompt'a ekleyip çıktısını düzeltir.
    feedback: str | None = None


class AgentResult[T: BaseModel](BaseModel):
    agent: str
    status: AgentStatus
    output: T | None = None
    error: str | None = None
    error_kind: AgentErrorKind | None = None
    model: str | None = None
    prompt_version: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    attempts: int = 1


class BaseAgent[T: BaseModel](ABC):
    """Tüm analiz agent'larının tabanı.

    Alt sınıflar şunları tanımlar:
    - name           : benzersiz agent adı (ör. "summary")
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
        """Agent'ı çalıştırır. İstisna fırlatmak yerine başarısızlığı AgentResult ile bildirir.

        Çıktı şemaya uymazsa `status="failed", error_kind="validation"` döner; orkestratör
        hata mesajını `ctx.feedback` ile geri verip bir kez daha çağırır.
        """
