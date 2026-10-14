"""API sözleşmesi: uçların istek ve yanıt şemaları (#46).

Uç listesi, yetki başlıkları ve örnekler: `docs/api.md` ve `docs/ornekler/api/`. Frontend
karşılığı `frontend/lib/api-types.ts`; alan adlarının aynı kaldığını
`tests/test_api_contract.py` denetler.

Kurallar:
- JSON alan adları snake_case'tir (backend ile aynı); arayüz `lib/api.ts`'te çevirir.
- Tarih/saatler ISO 8601, saat dilimli (UTC).
- Konuşmada olmayan bilgi `null` gelir; arayüz "—" gösterir.
- Tekne sahibi uçlarında kullanıcı kimliği gövdede değil, `X-User-Id` başlığında gelir (#24).
"""

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, TypeAdapter, model_validator

from app.domain.enums import (
    CallType,
    NextAction,
    RequestCategory,
    SalesOutcomeType,
    ServiceMode,
    SwitchboardOutcome,
    Urgency,
)
from app.schemas.analysis import (
    AgentRun,
    AnalysisStatus,
    CallClassification,
    CallSummary,
    CrmExtraction,
    SalesAnalysis,
)
from app.schemas.assistant import QuestionType, SourceRef

# Çağrının işlenme durumu. İlk üçü agent sonucunu (AnalysisStatus) değil, sürecin aşamasını
# anlatır: beklemede → (ses varsa) yazıya_cevriliyor → isleniyor → tamam | kismi | basarisiz.
CallState = Literal["beklemede", "yaziya_cevriliyor", "isleniyor", "tamam", "kismi", "basarisiz"]
Speaker = Literal["customer", "rep"]


# --- Filtreler (sorgu parametreleri) -------------------------------------------------------


class CallFilters(BaseModel):
    """`GET /calls` ve `GET /crm` sorgu parametreleri. Hepsi isteğe bağlıdır."""

    date_from: date | None = Field(default=None, description="Bu günden itibaren (dahil).")
    date_to: date | None = Field(default=None, description="Bu güne kadar (dahil).")
    call_type: CallType | None = None
    urgency: Urgency | None = None
    request_category: RequestCategory | None = None
    state: CallState | None = None
    q: str | None = Field(
        default=None, max_length=100, description="Müşteri, tekne veya marina adında arama."
    )
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    @model_validator(mode="after")
    def _dates_ordered(self) -> "CallFilters":
        if self.date_from and self.date_to and self.date_to < self.date_from:
            raise ValueError("date_to, date_from'dan önce olamaz.")
        return self


class PeriodFilter(BaseModel):
    """`GET /analytics/summary` sorgu parametreleri; boşsa son 30 gün."""

    date_from: date | None = None
    date_to: date | None = None

    @model_validator(mode="after")
    def _dates_ordered(self) -> "PeriodFilter":
        if self.date_from and self.date_to and self.date_to < self.date_from:
            raise ValueError("date_to, date_from'dan önce olamaz.")
        return self


# --- Çağrı listesi ve detayı (#51) ---------------------------------------------------------


class CallListItem(BaseModel):
    """Çağrı listesindeki bir satır: santral bilgisi + en son analizin özeti."""

    id: UUID
    started_at: datetime
    duration_s: int | None = None
    answer_delay_s: int | None = None
    switchboard_outcome: SwitchboardOutcome | None = None
    customer_name: str | None = None
    boat_name: str | None = None
    marina: str | None = None
    state: CallState
    call_type: CallType | None = None
    request_category: RequestCategory | None = None
    urgency: Urgency | None = None
    sales_outcome: SalesOutcomeType | None = None
    summary: str | None = Field(default=None, description="En son analizin özeti.")


class TranscriptSegmentOut(BaseModel):
    index: int = Field(ge=0)
    speaker: Speaker
    start_ms: int | None = None
    end_ms: int | None = None
    text: str


class TranscriptOut(BaseModel):
    """Admin ekranı için transkript. Telefon/kimlik gibi kişisel veriler maskelidir."""

    text: str
    segments: list[TranscriptSegmentOut] = Field(default_factory=list)


class AnalysisOut(BaseModel):
    """Bir analiz sürümü. Başarısız agent'ın alanı `null` kalır, nedeni `errors`'tadır."""

    version: int = Field(ge=1)
    status: AnalysisStatus
    created_at: datetime
    classification: CallClassification | None = None
    crm: CrmExtraction | None = None
    sales: SalesAnalysis | None = None
    summary: CallSummary | None = None
    errors: dict[str, str] = Field(default_factory=dict)
    runs: list[AgentRun] = Field(default_factory=list)


class CallDetail(BaseModel):
    """`GET /calls/{id}`: çağrı, transkript ve en son analiz."""

    id: UUID
    started_at: datetime
    duration_s: int | None = None
    answer_delay_s: int | None = None
    switchboard_outcome: SwitchboardOutcome | None = None
    customer_id: UUID | None = Field(default=None, description="Miço Usta müşterisi eşleştiyse.")
    boat_id: UUID | None = None
    customer_name: str | None = None
    customer_phone: str | None = Field(default=None, description="Yalnızca admin görür.")
    boat_name: str | None = None
    boat_model: str | None = None
    marina: str | None = None
    has_audio: bool = False
    state: CallState
    error: str | None = Field(default=None, description="state=basarisiz ise nedeni.")
    transcript: TranscriptOut | None = None
    analysis: AnalysisOut | None = None


# --- CRM kayıt önerileri (#51) ------------------------------------------------------------


class CrmRecordItem(BaseModel):
    """CRM ekranındaki bir öneri: hocanın 7 alanı + kaynağı olan çağrı."""

    call_id: UUID
    started_at: datetime
    customer_name: str | None = None
    boat_name: str | None = None
    analysis_version: int = Field(ge=1)
    request_category: RequestCategory | None = None
    location: str | None = None
    problem: str | None = None
    service_mode: ServiceMode | None = None
    urgency: Urgency | None = None
    potential_job: str | None = None
    next_action: NextAction | None = None
    evidence: dict[str, str] = Field(default_factory=dict)


# --- Çağrı alma ve analiz (#48, #49) ------------------------------------------------------


class SegmentIn(BaseModel):
    speaker: Speaker
    text: str = Field(min_length=1)
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, ge=0)


class CallCreate(BaseModel):
    """`POST /calls`: sesi olmayan çağrı (transkript metniyle). Ses için `POST /calls/audio`.

    `transcript` veya `segments`ten en az biri gerekir. Analiz hemen kuyruğa alınır.
    """

    started_at: datetime
    duration_s: int | None = Field(default=None, ge=0)
    answer_delay_s: int | None = Field(default=None, ge=0)
    switchboard_outcome: SwitchboardOutcome | None = None
    customer_name: str | None = None
    customer_phone: str | None = None
    boat_name: str | None = None
    boat_model: str | None = None
    marina: str | None = None
    transcript: str | None = Field(default=None, description="Düz metin; satır başında konuşmacı.")
    segments: list[SegmentIn] = Field(default_factory=list)

    @model_validator(mode="after")
    def _has_text(self) -> "CallCreate":
        if not (self.transcript and self.transcript.strip()) and not self.segments:
            raise ValueError("transcript veya segments verilmelidir.")
        return self


class AudioCallMeta(BaseModel):
    """`POST /calls/audio` form alanları (multipart; ses dosyası `file` alanında).

    `CallCreate` ile aynı çağrı bilgileri, transkript hariç: metin STT ile üretilir.
    """

    started_at: datetime
    duration_s: int | None = Field(default=None, ge=0)
    answer_delay_s: int | None = Field(default=None, ge=0)
    switchboard_outcome: SwitchboardOutcome | None = None
    customer_name: str | None = None
    customer_phone: str | None = None
    boat_name: str | None = None
    boat_model: str | None = None
    marina: str | None = None


class CallAccepted(BaseModel):
    """`POST /calls`, `POST /calls/audio` ve `POST /calls/{id}/analyze` yanıtı (202)."""

    call_id: UUID
    state: CallState
    task_id: str | None = Field(default=None, description="Arka plan görevinin kimliği.")


class CallStatus(BaseModel):
    """`GET /calls/{id}/status`: arayüz bunu birkaç saniyede bir sorar."""

    call_id: UUID
    state: CallState
    analysis_version: int | None = Field(default=None, description="Biten son analiz sürümü.")
    error: str | None = None
    updated_at: datetime


# --- Miço AI sohbeti (#28) ----------------------------------------------------------------


class ChatQuestion(BaseModel):
    """`POST /chat/messages`. `session_id` boşsa yeni oturum açılır."""

    question: str = Field(min_length=1, max_length=1000)
    session_id: UUID | None = None


class ChatMessageOut(BaseModel):
    id: UUID
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime
    question_type: QuestionType | None = Field(default=None, description="Yalnızca asistanda.")
    sources: list[SourceRef] = Field(default_factory=list)
    found: bool = Field(default=True, description="False: 'bulamadım' durumu.")


class ChatReply(BaseModel):
    """Soru ve cevabın ikisi de kaydedilir ve döner."""

    session_id: UUID
    question: ChatMessageOut
    answer: ChatMessageOut


class ChatSessionOut(BaseModel):
    id: UUID
    title: str | None = Field(default=None, description="İlk sorudan üretilir.")
    created_at: datetime
    updated_at: datetime


class ChatSessionDetail(BaseModel):
    session: ChatSessionOut
    messages: list[ChatMessageOut] = Field(default_factory=list)


# --- Akışlı cevap (SSE): POST /chat/messages/stream ---------------------------------------
#
# Her olay SSE'de `event: <type>` ve `data: <JSON>` olarak gelir. Sıra: 1-2 `status`, ardından
# kaynak kontrolü bittikten sonra `delta` parçaları, en sonda `done` (veya hata olursa `error`).
# Metin kaynak kontrolünden SONRA akıtılır; böylece ekranda görünen cümle sonradan silinmez.

StreamStage = Literal["araniyor", "hazirlaniyor", "dogrulaniyor"]


class StatusEvent(BaseModel):
    """İşlem aşaması; arayüz "Kayıtlar aranıyor…" gibi bir durum gösterir."""

    type: Literal["status"] = "status"
    stage: StreamStage


class DeltaEvent(BaseModel):
    """Cevap metninin bir parçası; parçalar sırayla birleştirilir."""

    type: Literal["delta"] = "delta"
    text: str


class DoneEvent(BaseModel):
    """Akışın sonu: kaydedilen soru/cevap, kaynak kartları ve `found` bilgisi."""

    type: Literal["done"] = "done"
    reply: ChatReply


class ErrorEvent(BaseModel):
    """Akış sırasında hata; bağlantı kapanır, soru kaydedilmişse yeniden denenebilir."""

    type: Literal["error"] = "error"
    code: str
    message: str


ChatStreamEvent = Annotated[
    StatusEvent | DeltaEvent | DoneEvent | ErrorEvent, Field(discriminator="type")
]
chat_stream_event_adapter: TypeAdapter[ChatStreamEvent] = TypeAdapter(ChatStreamEvent)
