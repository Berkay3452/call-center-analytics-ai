"""AI servisi tabloları (docs/db_schema.md §3). CHECK değerleri enums.py'den üretilir."""

import uuid
from datetime import datetime
from typing import Any, get_args

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    REAL,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.agents.names import CALL_CLASSIFIER, CRM_EXTRACTION, SALES_ANALYZER, SUMMARIZER
from app.db.base import Base, UUIDPrimaryKeyMixin
from app.db.checks import in_enum, in_values
from app.domain.enums import (
    CallType,
    CrmReviewStatus,
    LossReason,
    NextAction,
    RequestCategory,
    SalesOutcomeType,
    ServiceMode,
    SwitchboardOutcome,
    Urgency,
)
from app.schemas.api import CallState
from app.schemas.assistant import QuestionType

ANALYSIS_STATUSES = ("tamam", "kismi", "basarisiz")
# Çağrının işlenme durumu (API sözleşmesindeki CallState ile aynı liste).
CALL_STATES = get_args(CallState)
AGENT_NAMES = (CALL_CLASSIFIER, CRM_EXTRACTION, SALES_ANALYZER, SUMMARIZER)
AGENT_STATUSES = ("ok", "failed", "skipped")
AGENT_ERROR_KINDS = ("validation", "runtime", "timeout")
SPEAKERS = ("customer", "rep")
SOURCE_KINDS = ("service_record", "boat_note", "expense", "subscription")
# bge-m3 vektör boyutu. Şema sabit olmalı; model değişirse yeni migration gerekir
# (EMBEDDING_DIM ayarıyla da aynı tutulmalı).
EMBEDDING_DIM = 1024


def _now(*, onupdate: bool = False) -> Any:
    return mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now() if onupdate else None,
        nullable=False,
    )


def _uuid_fk(target: str, *, nullable: bool = False, ondelete: str | None = None) -> Any:
    return mapped_column(
        PG_UUID(as_uuid=True), ForeignKey(target, ondelete=ondelete), nullable=nullable
    )


# --- Çağrı ve transkript ----------------------------------------------------------------------


class Call(UUIDPrimaryKeyMixin, Base):
    """Çağrı meta verisi (santral bilgisi); ses dosyası yüklendikten sonra oluşturulur."""

    __tablename__ = "calls"
    __table_args__ = (
        in_enum("switchboard_outcome", SwitchboardOutcome),
        in_values("state", CALL_STATES, nullable=False, name="state"),
        UniqueConstraint("audio_sha256", name="uq_calls_audio_sha256"),
        Index("ix_calls_started_at", "started_at"),
        Index("ix_calls_customer_id", "customer_id"),
    )

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    answer_delay_s: Mapped[int | None] = mapped_column(Integer)
    duration_s: Mapped[int | None] = mapped_column(Integer)
    switchboard_outcome: Mapped[str | None] = mapped_column(Text)
    audio_path: Mapped[str | None] = mapped_column(Text)
    audio_sha256: Mapped[str | None] = mapped_column(String(64))
    # Müşteri/tekne eşleşince dolar; eşleşme yoksa NULL (CRM önerisi için).
    customer_id: Mapped[uuid.UUID | None] = _uuid_fk(
        "customers.id", nullable=True, ondelete="SET NULL"
    )
    boat_id: Mapped[uuid.UUID | None] = _uuid_fk("boats.id", nullable=True, ondelete="SET NULL")
    customer_name: Mapped[str | None] = mapped_column(Text)
    customer_phone: Mapped[str | None] = mapped_column(Text)
    boat_name: Mapped[str | None] = mapped_column(Text)
    boat_model: Mapped[str | None] = mapped_column(Text)
    marina: Mapped[str | None] = mapped_column(Text)
    # İşlenme durumu: beklemede → yaziya_cevriliyor → isleniyor → tamam | kismi | basarisiz.
    state: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'beklemede'"))
    error: Mapped[str | None] = mapped_column(Text)  # state=basarisiz ise nedeni
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _now(onupdate=True)


class Transcript(UUIDPrimaryKeyMixin, Base):
    """Çağrının tam transkripti; her çağrının en fazla bir transkripti olur."""

    __tablename__ = "transcripts"
    __table_args__ = (UniqueConstraint("call_id", name="uq_transcripts_call_id"),)

    call_id: Mapped[uuid.UUID] = _uuid_fk("calls.id", ondelete="CASCADE")
    full_text: Mapped[str] = mapped_column(Text, nullable=False)
    masked_text: Mapped[str | None] = mapped_column(Text)  # LLM ve RAG yalnızca bunu görür
    created_at: Mapped[datetime] = _now()


class TranscriptSegment(UUIDPrimaryKeyMixin, Base):
    """Konuşmacıya göre ayrılmış konuşma parçaları."""

    __tablename__ = "transcript_segments"
    __table_args__ = (
        UniqueConstraint("transcript_id", "segment_index", name="uq_segments_transcript_index"),
        in_values("speaker", SPEAKERS, nullable=False, name="speaker"),
        CheckConstraint(
            "start_ms IS NULL OR end_ms IS NULL OR end_ms >= start_ms", name="time_order"
        ),
        Index("ix_segments_transcript_id", "transcript_id"),
    )

    transcript_id: Mapped[uuid.UUID] = _uuid_fk("transcripts.id", ondelete="CASCADE")
    segment_index: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    speaker: Mapped[str] = mapped_column(Text, nullable=False)
    start_ms: Mapped[int | None] = mapped_column(Integer)
    end_ms: Mapped[int | None] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    masked_text: Mapped[str | None] = mapped_column(Text)


# --- Analiz -------------------------------------------------------------------------------------


class AnalysisResult(UUIDPrimaryKeyMixin, Base):
    """Dört agent'ın birleşik çıktısı; yeniden analiz aynı çağrı için yeni sürüm satırı ekler."""

    __tablename__ = "analysis_results"
    __table_args__ = (
        UniqueConstraint("call_id", "version", name="uq_analysis_call_version"),
        in_values("status", ANALYSIS_STATUSES, nullable=False, name="status"),
        in_enum("call_type", CallType),
        in_enum("request_category", RequestCategory),
        in_enum("service_mode", ServiceMode),
        in_enum("urgency", Urgency),
        in_enum("next_action", NextAction),
        in_enum("sales_outcome", SalesOutcomeType),
        in_enum("loss_reason", LossReason),
        # SalesAnalysis kuralı: kayıp nedeni yalnızca kaybedildi iken dolu, o zaman zorunlu.
        CheckConstraint(
            "loss_reason IS NULL OR sales_outcome = 'kaybedildi'", name="loss_reason_only_lost"
        ),
        CheckConstraint(
            "sales_outcome IS DISTINCT FROM 'kaybedildi' OR loss_reason IS NOT NULL",
            name="loss_reason_required_when_lost",
        ),
        CheckConstraint(
            "call_type_confidence IS NULL OR "
            "(call_type_confidence >= 0 AND call_type_confidence <= 1)",
            name="call_type_confidence_range",
        ),
        CheckConstraint(
            "sales_confidence IS NULL OR (sales_confidence >= 0 AND sales_confidence <= 1)",
            name="sales_confidence_range",
        ),
        Index("ix_analysis_call_id", "call_id"),
        Index("ix_analysis_call_type", "call_type"),
        Index("ix_analysis_sales_outcome", "sales_outcome"),
    )

    call_id: Mapped[uuid.UUID] = _uuid_fk("calls.id", ondelete="CASCADE")
    version: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("1"))
    status: Mapped[str] = mapped_column(Text, nullable=False)
    # Çağrı Sınıflandırma
    call_type: Mapped[str | None] = mapped_column(Text)
    call_type_confidence: Mapped[float | None] = mapped_column(REAL)
    call_type_reason: Mapped[str | None] = mapped_column(Text)
    # CRM Bilgi Çıkarım (7 alan); konuşmada geçmeyen alan NULL kalır
    request_category: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(Text)
    problem: Mapped[str | None] = mapped_column(Text)
    service_mode: Mapped[str | None] = mapped_column(Text)
    urgency: Mapped[str | None] = mapped_column(Text)
    potential_job: Mapped[str | None] = mapped_column(Text)
    next_action: Mapped[str | None] = mapped_column(Text)
    crm_evidence: Mapped[dict[str, str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    # Satış Analiz
    sales_outcome: Mapped[str | None] = mapped_column(Text)
    loss_reason: Mapped[str | None] = mapped_column(Text)
    sales_evidence: Mapped[str | None] = mapped_column(Text)
    sales_confidence: Mapped[float | None] = mapped_column(REAL)
    # Özetleme
    summary: Mapped[str | None] = mapped_column(Text)
    key_points: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    # Meta
    errors: Mapped[dict[str, str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = _now()


class AgentRun(UUIDPrimaryKeyMixin, Base):
    """Her agent çalışmasının kaydı (orkestratör yazar): süre, maliyet ve hata izleme."""

    __tablename__ = "agent_runs"
    __table_args__ = (
        in_values("agent_name", AGENT_NAMES, nullable=False, name="agent_name"),
        in_values("status", AGENT_STATUSES, nullable=False, name="status"),
        in_values("error_kind", AGENT_ERROR_KINDS, name="error_kind"),
        Index("ix_runs_analysis_id", "analysis_id"),
    )

    analysis_id: Mapped[uuid.UUID] = _uuid_fk("analysis_results.id", ondelete="CASCADE")
    agent_name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("1"))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    error_kind: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(Text)
    tokens_in: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    tokens_out: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = _now()


class CrmReview(UUIDPrimaryKeyMixin, Base):
    """CRM önerisi inceleme kaydı (#106): onayla, reddet, düzenle."""

    __tablename__ = "crm_reviews"
    __table_args__ = (
        UniqueConstraint("analysis_id", name="uq_crm_reviews_analysis_id"),
        in_enum("status", CrmReviewStatus, nullable=False),
        Index("ix_crm_reviews_call_id", "call_id"),
        Index("ix_crm_reviews_service_order_id", "service_order_id"),
    )

    analysis_id: Mapped[uuid.UUID] = _uuid_fk("analysis_results.id", ondelete="CASCADE")
    call_id: Mapped[uuid.UUID] = _uuid_fk("calls.id", ondelete="CASCADE")
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'bekliyor'"))
    edited_fields: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    note: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    service_order_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("service_orders.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _now(onupdate=True)


# --- Miço AI sohbeti ----------------------------------------------------------------------------


class ChatSession(UUIDPrimaryKeyMixin, Base):
    """Miço AI sohbet oturumu; yetkilendirme `owner_id` ile yapılır."""

    __tablename__ = "chat_sessions"
    __table_args__ = (Index("ix_sessions_owner_id", "owner_id"),)

    owner_id: Mapped[uuid.UUID] = _uuid_fk("customers.id")
    title: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _now(onupdate=True)


class ChatMessage(UUIDPrimaryKeyMixin, Base):
    """Sohbet mesajı ve kaynak referansları (SourceRef listesi)."""

    __tablename__ = "chat_messages"
    __table_args__ = (
        in_values("role", ("user", "assistant"), nullable=False, name="role"),
        in_enum("question_type", QuestionType),
        Index("ix_messages_session_id", "session_id"),
    )

    session_id: Mapped[uuid.UUID] = _uuid_fk("chat_sessions.id", ondelete="CASCADE")
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    question_type: Mapped[str | None] = mapped_column(Text)
    sources: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    found: Mapped[bool] = mapped_column(nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = _now()


# --- RAG ----------------------------------------------------------------------------------------


class RagChunk(UUIDPrimaryKeyMixin, Base):
    """Tekne karnesi parçaları: vektör (bge-m3) + Türkçe tam metin; hibrit arama için (#26).

    `source_id` kaynak türüne göre farklı tablolara işaret ettiği için FK tanımlanmaz.
    """

    __tablename__ = "rag_chunks"
    __table_args__ = (
        UniqueConstraint("source_kind", "source_id", "chunk_index", name="uq_chunks_source_chunk"),
        in_values("source_kind", SOURCE_KINDS, nullable=False, name="source_kind"),
        Index("ix_chunks_owner_id", "owner_id"),
        Index("ix_chunks_boat_id", "boat_id"),
        Index(
            "ix_chunks_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_chunks_tsv", "tsv", postgresql_using="gin"),
    )

    source_kind: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    boat_id: Mapped[uuid.UUID | None] = _uuid_fk("boats.id", nullable=True)
    owner_id: Mapped[uuid.UUID] = _uuid_fk("customers.id")
    chunk_index: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("0"))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    # Uygulama yazmaz; veritabanı içerikten üretir.
    tsv: Mapped[Any] = mapped_column(
        TSVECTOR, Computed("to_tsvector('turkish', content)", persisted=True)
    )
    created_at: Mapped[datetime] = _now()
