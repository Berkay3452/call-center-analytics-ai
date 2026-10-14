"""Miço AI (Tekne Sahibi asistanı) şemaları.

Asistanın dışa açılan sözleşmesidir: sohbet API'si (#28) `AssistantRequest` alır ve
`AssistantAnswer` döner. Arayüzdeki kaynak kartları `sources` listesinden çizilir.
"""

import datetime as dt
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class QuestionType(StrEnum):
    """Sorgu planlayıcının soru sınıfları (diyagram 03)."""

    GECMIS_ONERI = "gecmis_oneri"  # bakım geçmişi ve öneri: tekne karnesi araması
    SAYISAL = "sayisal"  # gider toplamı, kalan hak, son bakım tarihi: hazır araçlar
    KAPSAM_DISI = "kapsam_disi"  # asistanın işi olmayan sorular: nazik ret


class AssistantTool(StrEnum):
    """`sayisal` sorular için hazır araçlar (LLM sayıyı kendisi hesaplamaz)."""

    GET_EXPENSE_TOTAL = "get_expense_total"
    GET_REMAINING_PACKAGE = "get_remaining_package"
    GET_LAST_MAINTENANCE = "get_last_maintenance"


SourceKind = Literal["service_record", "boat_note", "expense", "subscription"]


class SourceRef(BaseModel):
    """Cevabın dayandığı kayıt; arayüzde kaynak kartı olarak gösterilir."""

    kind: SourceKind
    record_id: str = Field(min_length=1)
    title: str = Field(description="Kartın başlığı (ör. '15 Ağustos 2026 servis kaydı').")
    date: dt.date | None = None
    excerpt: str | None = Field(default=None, description="Kayıttan kısa alıntı.")


class AssistantRequest(BaseModel):
    """Tekne sahibinin sorusu. `owner_id` .NET API'nin doğruladığı oturum kullanıcısıdır."""

    question: str = Field(min_length=1, max_length=1000)
    owner_id: str = Field(min_length=1, description="Oturumdaki tekne sahibi; zorunlu.")

    @field_validator("question", "owner_id")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Boş olamaz.")
        return value


class AssistantAnswer(BaseModel):
    answer: str
    question_type: QuestionType
    sources: list[SourceRef] = Field(default_factory=list)
    found: bool = Field(
        default=True,
        description="False: kayıtlarda bilgi bulunamadı; arayüz 'bulamadım' durumunu gösterir.",
    )
