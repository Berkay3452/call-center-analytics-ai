"""Çağrı analizi şemaları.

Üç yerde ortak sözleşmedir: agent'ların LLM'den beklediği çıktı biçimi, veritabanındaki analiz
tabloları (#5) ve arayüz ekranları (#9). `Field(description=...)` metinleri LLM'e şema olarak
da gittiği için bilerek ayrıntılı yazılmıştır.

Kural: konuşmada olmayan bilgi uydurulmaz; ilgili alan `None` kalır.
"""

import re
from datetime import date
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.agents.base import AgentResult
from app.agents.names import CALL_CLASSIFIER, CRM_EXTRACTION, SALES_ANALYZER, SUMMARIZER
from app.domain.enums import (
    CallType,
    LossReason,
    NextAction,
    RequestCategory,
    SalesOutcomeType,
    ServiceMode,
    Urgency,
)

# Veritabanına ve arayüze giden değerler; bkz. #5 ve #9.
AnalysisStatus = Literal["tamam", "kismi", "basarisiz"]

_SENTENCE_END = re.compile(r"[.!?…]+(?:\s|$)")


# --- Agent çıktıları ------------------------------------------------------------------------


class CallClassification(BaseModel):
    """Çağrı Sınıflandırma Agent'ının çıktısı."""

    call_type: CallType = Field(
        description="Çağrının tipi: yeni müşteri, servis, teklif, acil, bilgi."
    )
    confidence: float = Field(ge=0, le=1, description="Kararın güveni (0 ile 1 arası).")
    reason: str = Field(
        min_length=1,
        description="Kararın tek cümlelik gerekçesi; hangi ifadeye dayandığı.",
    )


class CrmExtraction(BaseModel):
    """CRM Bilgi Çıkarım Agent'ının çıktısı (CRM kaydı önerisi).

    Konuşmada geçmeyen alan UYDURULMAZ, `None` bırakılır.
    """

    request_category: RequestCategory | None = Field(
        default=None, description="Müşteri talebinin kategorisi (ör. motor arızası)."
    )
    location: str | None = Field(
        default=None, description="Marina veya lokasyon (ör. Tuzla Marina)."
    )
    problem: str | None = Field(
        default=None, description="Sorunun kısa tarifi (ör. motor gaz verince devir almıyor)."
    )
    service_mode: ServiceMode | None = Field(
        default=None, description="Hizmetin veriliş biçimi (ör. yerinde servis)."
    )
    urgency: Urgency | None = Field(default=None, description="Aciliyet seviyesi.")
    potential_job: str | None = Field(
        default=None, description="Doğacak olası iş (ör. motor arıza tespiti)."
    )
    next_action: NextAction | None = Field(default=None, description="Önerilen sonraki aksiyon.")
    evidence: dict[str, str] = Field(
        default_factory=dict,
        description="Alan adı → konuşmadan kısa alıntı. Yalnızca dolu alanlar için verilir.",
    )

    @field_validator("evidence")
    @classmethod
    def _evidence_keys_are_fields(cls, value: dict[str, str]) -> dict[str, str]:
        unknown = set(value) - (set(cls.model_fields) - {"evidence"})
        if unknown:
            raise ValueError(f"evidence anahtarları alan adı olmalı: {sorted(unknown)}")
        return value


class SalesAnalysis(BaseModel):
    """Satış Analiz Agent'ının çıktısı."""

    outcome: SalesOutcomeType = Field(description="Satışın sonucu.")
    loss_reason: LossReason | None = Field(
        default=None,
        description="Kaybedilme nedeni. YALNIZCA outcome=kaybedildi iken verilir.",
    )
    evidence: str | None = Field(default=None, description="Kararı destekleyen kısa alıntı.")
    confidence: float = Field(ge=0, le=1, description="Kararın güveni (0 ile 1 arası).")

    @model_validator(mode="after")
    def _loss_reason_only_when_lost(self) -> "SalesAnalysis":
        lost = self.outcome == SalesOutcomeType.KAYBEDILDI
        if lost and self.loss_reason is None:
            raise ValueError(
                "outcome=kaybedildi iken loss_reason zorunludur (bilinmiyorsa 'diger')."
            )
        if not lost and self.loss_reason is not None:
            raise ValueError("loss_reason yalnızca outcome=kaybedildi iken verilebilir.")
        return self


class CallSummary(BaseModel):
    """Özetleme Agent'ının çıktısı."""

    summary: str = Field(
        min_length=1,
        description="Görüşmenin en fazla 3 cümlelik özeti. Üçüncü şahıs, Türkçe. Kişisel veri yok.",
    )
    key_points: list[str] = Field(
        default_factory=list, max_length=3, description="En fazla 3 kısa madde."
    )

    @field_validator("summary")
    @classmethod
    def _at_most_three_sentences(cls, value: str) -> str:
        if len(_SENTENCE_END.findall(value.strip())) > 3:
            raise ValueError("Özet en fazla 3 cümle olmalı.")
        return value


# --- Birleşik sonuç -------------------------------------------------------------------------


class AgentRun(BaseModel):
    """Bir agent çalışmasının kaydı (`agent_runs` tablosuna yazılacak satır)."""

    agent: str
    status: str
    attempts: int
    latency_ms: int
    error: str | None = None
    error_kind: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0

    @classmethod
    def from_result(cls, result: AgentResult[Any]) -> "AgentRun":
        return cls.model_validate(result.model_dump(exclude={"output"}))


class AnalysisResult(BaseModel):
    """Bir çağrının birleşik analiz sonucu. Başarısız agent'ın alanı `None` kalır."""

    call_id: UUID
    status: AnalysisStatus
    classification: CallClassification | None = None
    crm: CrmExtraction | None = None
    sales: SalesAnalysis | None = None
    summary: CallSummary | None = None
    errors: dict[str, str] = Field(default_factory=dict)
    runs: list[AgentRun] = Field(default_factory=list)

    @classmethod
    def from_outputs(
        cls,
        *,
        call_id: UUID,
        status: AnalysisStatus,
        outputs: dict[str, dict[str, Any]],
        errors: dict[str, str],
        runs: list[AgentRun],
    ) -> "AnalysisResult":
        """Orkestratörün agent adına göre topladığı çıktıları şemalı sonuca çevirir."""

        def pick[T: BaseModel](name: str, model: type[T]) -> T | None:
            return model.model_validate(outputs[name]) if name in outputs else None

        return cls(
            call_id=call_id,
            status=status,
            classification=pick(CALL_CLASSIFIER, CallClassification),
            crm=pick(CRM_EXTRACTION, CrmExtraction),
            sales=pick(SALES_ANALYZER, SalesAnalysis),
            summary=pick(SUMMARIZER, CallSummary),
            errors=errors,
            runs=runs,
        )


# --- KPI ------------------------------------------------------------------------------------


class CountItem(BaseModel):
    name: str
    count: int = Field(ge=0)


class KpiSummary(BaseModel):
    """Çağrı Analitiği ekranının KPI kartları ve grafikleri (Sistem mimarisi v3.1 §6.1)."""

    period_start: date
    period_end: date
    total_calls: int = Field(ge=0, description="Gelen çağrı sayısı.")
    new_customers: int = Field(ge=0)
    service_requests: int = Field(ge=0)
    quote_requests: int = Field(ge=0)
    urgent_requests: int = Field(ge=0)
    converted_sales: int = Field(ge=0, description="Satışa dönüşen çağrı sayısı.")
    lost_by_reason: dict[LossReason, int] = Field(
        default_factory=dict, description="Kaybedilme nedenine göre sayı."
    )
    top_problems: list[CountItem] = Field(default_factory=list, description="En sık arızalar.")
    busiest_marinas: list[CountItem] = Field(
        default_factory=list, description="En yoğun marinalar."
    )
    avg_answer_delay_s: float | None = Field(
        default=None,
        ge=0,
        description="Ortalama cevap süresi (sn). Ses dosyasından değil, çağrı bilgisinden gelir.",
    )

    @model_validator(mode="after")
    def _period_is_ordered(self) -> "KpiSummary":
        if self.period_end < self.period_start:
            raise ValueError("period_end, period_start'tan önce olamaz.")
        return self
