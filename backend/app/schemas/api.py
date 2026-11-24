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

import re
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, TypeAdapter, model_validator

from app.domain.accounts import MIN_PASSWORD_LENGTH
from app.domain.enums import (
    CallType,
    CrmReviewStatus,
    LossReason,
    MatchMethod,
    NextAction,
    RequestCategory,
    SalesOutcomeType,
    Sentiment,
    ServiceMode,
    ServiceOrderStatus,
    SwitchboardOutcome,
    Urgency,
)
from app.schemas.analysis import (
    AgentRun,
    AnalysisStatus,
    CallClassification,
    CallSummary,
    CrmExtraction,
    CustomerSentiment,
    SalesAnalysis,
)
from app.schemas.assistant import QuestionType, SourceRef
from app.schemas.safe import (
    Millis,
    NameStr,
    SafeStr,
    SaneDate,
    SaneDateTime,
    Seconds,
)

# Çağrının işlenme durumu. İlk üçü agent sonucunu (AnalysisStatus) değil, sürecin aşamasını
# anlatır: beklemede → (ses varsa) yazıya_cevriliyor → isleniyor → tamam | kismi | basarisiz.
CallState = Literal["beklemede", "yaziya_cevriliyor", "isleniyor", "tamam", "kismi", "basarisiz"]
# Süren işlemin aşaması (#218): kuyrukta bekliyor, ses yazıya çevriliyor, agent'lar analiz ediyor.
CallStage = Literal["kuyruk", "stt", "analiz"]

_STAGES: dict[str, CallStage] = {
    "beklemede": "kuyruk",
    "yaziya_cevriliyor": "stt",
    "isleniyor": "analiz",
}


def stage_of(state: str) -> CallStage | None:
    """Süren işlemin aşaması; işlem bittiyse (tamam, kismi, basarisiz) None."""
    return _STAGES.get(state)


Speaker = Literal["customer", "rep"]


# --- Filtreler (sorgu parametreleri) -------------------------------------------------------


class CallFilters(BaseModel):
    """`GET /calls` ve `GET /crm` sorgu parametreleri. Hepsi isteğe bağlıdır."""

    date_from: SaneDate | None = Field(
        default=None, description="Bu günden itibaren (dahil, Europe/Istanbul)."
    )
    date_to: SaneDate | None = Field(
        default=None, description="Bu güne kadar (dahil, Europe/Istanbul)."
    )
    call_type: CallType | None = None
    urgency: Urgency | None = None
    request_category: RequestCategory | None = None
    state: CallState | None = None
    status: CrmReviewStatus | None = Field(
        default=None,
        description="CRM inceleme durumu filtresi (bekliyor | onaylandi | reddedildi).",
    )
    marina: SafeStr | None = Field(
        default=None, max_length=200, description="Marina adına göre tam eşleşme filtresi."
    )
    q: SafeStr | None = Field(
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

    date_from: SaneDate | None = Field(
        default=None, description="Bu günden itibaren (dahil, Europe/Istanbul)."
    )
    date_to: SaneDate | None = Field(
        default=None, description="Bu güne kadar (dahil, Europe/Istanbul)."
    )
    marina: SafeStr | None = Field(
        default=None, max_length=200, description="Marina adına göre tam eşleşme filtresi."
    )

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
    stage: CallStage | None = Field(
        default=None, description="İşlem sürüyorsa aşaması (kuyruk, stt, analiz); bittiyse null."
    )
    updated_at: datetime | None = Field(
        default=None,
        description="Durumun son değiştiği an; sürüyorsa aşamanın başlama zamanıdır.",
    )
    call_type: CallType | None = None
    request_category: RequestCategory | None = None
    urgency: Urgency | None = None
    sales_outcome: SalesOutcomeType | None = None
    loss_reason: LossReason | None = Field(
        default=None, description="Kaybedilme nedeni (yalnızca kaybedildi iken)."
    )
    sentiment: Sentiment | None = Field(
        default=None, description="Müşterinin duygu durumu (duygu analizi yoksa null)."
    )
    complaint: bool | None = Field(
        default=None, description="Müşteri açıkça şikâyet ediyorsa true (duygu analizi yoksa null)."
    )
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
    sentiment: CustomerSentiment | None = None
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
    stage: CallStage | None = Field(
        default=None, description="İşlem sürüyorsa aşaması (kuyruk, stt, analiz); bittiyse null."
    )
    updated_at: datetime | None = Field(
        default=None,
        description="Durumun son değiştiği an; sürüyorsa aşamanın başlama zamanıdır.",
    )
    error: str | None = Field(default=None, description="state=basarisiz ise nedeni.")
    match_method: MatchMethod | None = Field(
        default=None, description="Çağrının müşteri/tekne eşleştirme yöntemi (#119)."
    )
    transcript: TranscriptOut | None = None
    analysis: AnalysisOut | None = None


class LoginIn(BaseModel):
    """`POST /auth/login` istek gövdesi (#369). `role` hangi hesap tablosuna bakılacağını seçer."""

    role: Literal["admin", "owner"] = Field(
        description="Giriş sekmesi: yönetici veya tekne sahibi."
    )
    username: Annotated[SafeStr, Field(min_length=1, max_length=100)]
    password: Annotated[SafeStr, Field(min_length=1, max_length=200)]


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
_PHONE_RE = re.compile(r"^(?:\+90|0)?(5\d{9})$")


def normalize_phone(raw: str) -> str:
    """TR cep numarasını `+905xxxxxxxxx` biçimine çevirir; geçersizse ValueError."""
    compact = re.sub(r"[\s().-]", "", raw)
    match = _PHONE_RE.match(compact)
    if not match:
        raise ValueError("Geçerli bir cep telefonu girin (ör. 0532 123 45 67).")
    return f"+90{match.group(1)}"


class RegisterIn(BaseModel):
    """`POST /auth/register` gövdesi (#382): müşteri bilgileri + parola (doğum tarihi alınmaz)."""

    first_name: Annotated[SafeStr, Field(min_length=1, max_length=80)]
    last_name: Annotated[SafeStr, Field(min_length=1, max_length=80)]
    phone: Annotated[SafeStr, Field(min_length=1, max_length=30)]
    email: Annotated[SafeStr, Field(min_length=3, max_length=120)]
    password: Annotated[SafeStr, Field(min_length=1, max_length=200)]
    password_confirm: Annotated[SafeStr, Field(min_length=1, max_length=200)]

    @model_validator(mode="after")
    def _check(self) -> "RegisterIn":
        self.first_name, self.last_name = self.first_name.strip(), self.last_name.strip()
        if not self.first_name or not self.last_name:
            raise ValueError("Ad ve soyad boş olamaz.")
        self.email = self.email.strip().lower()
        if not _EMAIL_RE.match(self.email):
            raise ValueError("Geçerli bir e-posta adresi girin.")
        self.phone = normalize_phone(self.phone)
        if len(self.password) < MIN_PASSWORD_LENGTH:
            raise ValueError(f"Parola en az {MIN_PASSWORD_LENGTH} karakter olmalı.")
        if self.password != self.password_confirm:
            raise ValueError("Parola ve tekrarı aynı olmalı.")
        return self


class LoginOut(BaseModel):
    """Başarılı girişin sonucu; oturumu Next sunucusu kurar, parola/karma asla dönmez."""

    role: Literal["admin", "owner"]
    account_id: UUID
    customer_id: UUID | None = Field(
        default=None, description="Tekne sahibi için müşteri kimliği, yönetici için boş."
    )
    display_name: str


class CallMatchIn(BaseModel):
    """`PUT /calls/{id}/match` istek gövdesi (#119)."""

    customer_id: UUID = Field(description="Eşleştirilecek müşteri kimliği.")
    boat_id: UUID | None = Field(
        default=None, description="Eşleştirilecek tekne kimliği (isteğe bağlı)."
    )


class CustomerBoatOut(BaseModel):
    """Müşteri aramasında müşterinin teknesi (#209)."""

    id: UUID
    name: str
    model: str | None = None


class CustomerSearchItem(BaseModel):
    """`GET /customers` satırı: müşteri ve tekneleri; elle eşleştirme için seçilir (#209)."""

    id: UUID
    name: str
    phone: str | None = Field(default=None, description="Yalnızca admin görür.")
    boats: list[CustomerBoatOut] = Field(default_factory=list)


# --- CRM kayıt önerileri (#51) ------------------------------------------------------------


class CrmRecordItem(BaseModel):
    """CRM ekranındaki bir öneri: hocanın 7 alanı + kaynağı olan çağrı."""

    call_id: UUID
    started_at: datetime
    customer_name: str | None = None
    boat_name: str | None = None
    match_method: MatchMethod | None = Field(
        default=None,
        description=(
            "Çağrının müşteri/tekne eşleştirme yöntemi (telefon, ad_tekne, elle, yok); "
            "null: eşleştirme henüz denenmedi. Onay için müşteri eşleşmiş olmalıdır (#209)."
        ),
    )
    matched_customer_name: str | None = Field(
        default=None,
        description="Eşleşmişse bağlı müşterinin kayıtlı adı (`customer_name` çağrı ipucudur).",
    )
    matched_boat_name: str | None = Field(
        default=None, description="Eşleşmişse çağrıya bağlı teknenin kayıtlı adı."
    )
    analysis_version: int = Field(ge=1)
    request_category: RequestCategory | None = None
    location: str | None = None
    problem: str | None = None
    service_mode: ServiceMode | None = None
    urgency: Urgency | None = None
    potential_job: str | None = None
    next_action: NextAction | None = None
    evidence: dict[str, str] = Field(default_factory=dict)
    review_status: CrmReviewStatus = Field(default=CrmReviewStatus.BEKLIYOR)
    edited_fields: dict[str, Any] = Field(default_factory=dict)
    service_order_id: UUID | None = None


class CrmApproveIn(BaseModel):
    """`POST /crm/{call_id}/approve`: isteğe bağlı düzenlenmiş 7 alan ve onay notu (#106)."""

    request_category: RequestCategory | None = None
    location: SafeStr | None = None
    problem: SafeStr | None = None
    service_mode: ServiceMode | None = None
    urgency: Urgency | None = None
    potential_job: SafeStr | None = None
    next_action: NextAction | None = None
    note: SafeStr | None = Field(default=None, description="İsteğe bağlı onay notu.")


class CrmRejectIn(BaseModel):
    """`POST /crm/{call_id}/reject`: red nedeni veya not (#106)."""

    note: SafeStr | None = Field(default=None, description="Red nedeni veya not.")


class CrmReviewOut(BaseModel):
    """`POST /crm/{call_id}/approve` ve `POST /crm/{call_id}/reject` yanıtı (#106)."""

    id: UUID
    call_id: UUID
    analysis_id: UUID
    status: CrmReviewStatus
    edited_fields: dict[str, Any] = Field(default_factory=dict)
    note: str | None = None
    reviewed_at: datetime | None = None
    service_order_id: UUID | None = None


# --- Çağrı alma ve analiz (#48, #49) ------------------------------------------------------


class SegmentIn(BaseModel):
    speaker: Speaker
    text: SafeStr = Field(min_length=1)
    start_ms: Millis | None = None
    end_ms: Millis | None = None


class CallCreate(BaseModel):
    """`POST /calls`: sesi olmayan çağrı (transkript metniyle). Ses için `POST /calls/audio`.

    `transcript` veya `segments`ten en az biri gerekir. Analiz hemen kuyruğa alınır.
    """

    started_at: SaneDateTime
    duration_s: Seconds | None = None
    answer_delay_s: Seconds | None = None
    switchboard_outcome: SwitchboardOutcome | None = None
    customer_name: NameStr | None = None
    customer_phone: NameStr | None = None
    boat_name: NameStr | None = None
    boat_model: NameStr | None = None
    marina: NameStr | None = None
    transcript: SafeStr | None = Field(
        default=None, description="Düz metin; satır başında konuşmacı."
    )
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

    started_at: SaneDateTime
    duration_s: Seconds | None = None
    answer_delay_s: Seconds | None = None
    switchboard_outcome: SwitchboardOutcome | None = None
    customer_name: NameStr | None = None
    customer_phone: NameStr | None = None
    boat_name: NameStr | None = None
    boat_model: NameStr | None = None
    marina: NameStr | None = None


class CallAccepted(BaseModel):
    """`POST /calls`, `POST /calls/audio` ve `POST /calls/{id}/analyze` yanıtı (202)."""

    call_id: UUID
    state: CallState
    task_id: str | None = Field(default=None, description="Arka plan görevinin kimliği.")
    already_running: bool = Field(
        default=False,
        description=(
            "True: çağrı zaten işleniyordu, yeni görev açılmadı; state mevcut durumdur (#218). "
            "Bu bir hata değildir; arayüz mevcut ilerlemeyi göstermeye devam eder."
        ),
    )
    stage: CallStage | None = Field(
        default=None, description="Süren işlemin aşaması (yalnızca already_running iken dolu)."
    )
    updated_at: datetime | None = Field(
        default=None, description="Durumun son değiştiği an (yalnızca already_running iken dolu)."
    )


class CallStatus(BaseModel):
    """`GET /calls/{id}/status`: arayüz bunu birkaç saniyede bir sorar."""

    call_id: UUID
    state: CallState
    stage: CallStage | None = Field(
        default=None, description="İşlem sürüyorsa aşaması (kuyruk, stt, analiz); bittiyse null."
    )
    analysis_version: int | None = Field(default=None, description="Biten son analiz sürümü.")
    error: str | None = None
    updated_at: datetime = Field(
        description="Durumun son değiştiği an; sürüyorsa aşamanın başlama zamanıdır."
    )


# --- Miço AI sohbeti (#28) ----------------------------------------------------------------


class ChatQuestion(BaseModel):
    """`POST /chat/messages`. `session_id` boşsa yeni oturum açılır."""

    question: SafeStr = Field(min_length=1, max_length=5000)
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


# --- Servis emirleri (#118) ---------------------------------------------------------------


class ServiceOrderFilters(BaseModel):
    """`GET /service-orders` sorgu parametreleri. Hepsi isteğe bağlıdır."""

    status: ServiceOrderStatus | None = Field(
        default=None, description="Servis emri durumu filtresi."
    )
    date_from: SaneDate | None = Field(
        default=None, description="Bu tarihten itibaren (dahil, Europe/Istanbul)."
    )
    date_to: SaneDate | None = Field(
        default=None, description="Bu tarihe kadar (dahil, Europe/Istanbul)."
    )
    marina: SafeStr | None = Field(
        default=None, max_length=200, description="Marina adına göre tam eşleşme filtresi."
    )
    q: SafeStr | None = Field(
        default=None,
        max_length=100,
        description="Müşteri adı, tekne adı, usta adı veya açıklamada arama.",
    )
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    @model_validator(mode="after")
    def _dates_ordered(self) -> "ServiceOrderFilters":
        if self.date_from and self.date_to and self.date_to < self.date_from:
            raise ValueError("date_to, date_from'dan önce olamaz.")
        return self


class ServiceOrderListItem(BaseModel):
    """Sayfalı servis emirleri listesindeki bir satır."""

    id: UUID
    status: ServiceOrderStatus
    category: RequestCategory | str | None = None
    description: str | None = None
    scheduled_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    customer_id: UUID
    customer_name: str
    customer_phone: str | None = None
    boat_id: UUID
    boat_name: str
    boat_model: str | None = None
    marina: str | None = None
    craftsman_id: UUID | None = None
    craftsman_name: str | None = None
    source_call_id: UUID | None = None


class ServiceOrderCustomerOut(BaseModel):
    """Servis emrindeki müşteri bilgisi."""

    id: UUID
    full_name: str
    phone: str | None = None
    email: str | None = None
    marina: str | None = None


class ServiceOrderBoatOut(BaseModel):
    """Servis emrindeki tekne bilgisi."""

    id: UUID
    name: str
    model: str | None = None
    year: int | None = None
    marina: str | None = None


class ServiceOrderCraftsmanOut(BaseModel):
    """Servis emrine atanan usta bilgisi."""

    id: UUID
    full_name: str
    specialty: str | None = None
    phone: str | None = None


class ServiceOrderSourceCallOut(BaseModel):
    """Servis emrinin kaynak çağrısı ve CRM önerisi özeti (#106)."""

    call_id: UUID
    started_at: datetime
    customer_name: str | None = None
    boat_name: str | None = None
    switchboard_outcome: SwitchboardOutcome | str | None = None
    request_category: RequestCategory | str | None = None
    location: str | None = None
    problem: str | None = None
    service_mode: ServiceMode | str | None = None
    urgency: Urgency | str | None = None
    potential_job: str | None = None
    next_action: NextAction | str | None = None
    summary: str | None = None
    crm_review_status: CrmReviewStatus | str | None = None
    crm_review_note: str | None = None
    crm_reviewed_at: datetime | None = None


class ServiceOrderDetail(BaseModel):
    """`GET /service-orders/{id}` yanıtı."""

    id: UUID
    status: ServiceOrderStatus
    category: RequestCategory | str | None = None
    description: str | None = None
    scheduled_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    customer: ServiceOrderCustomerOut
    boat: ServiceOrderBoatOut
    craftsman: ServiceOrderCraftsmanOut | None = None
    source_call: ServiceOrderSourceCallOut | None = None


class ServiceOrderStatusUpdate(BaseModel):
    """`PATCH /service-orders/{id}/status` istek gövdesi."""

    status: ServiceOrderStatus = Field(description="Geçilmek istenen yeni durum.")
