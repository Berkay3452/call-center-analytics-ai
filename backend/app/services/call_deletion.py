"""Çağrı silme ve saklama süresi temizliği (#269, KVKK silme/yok etme hakkı).

Bir çağrı silinince:
- `calls` satırı gider; `ON DELETE CASCADE` ile `transcripts` (ve `transcript_segments`: ham ve
  maskeli metin), `analysis_results` (`agent_runs` dahil) ve `crm_reviews` de gider;
- ses dosyası depodan silinir;
- `service_orders.source_call_id` `NULL` olur (`ON DELETE SET NULL`): servis emri işletmenin iş
  kaydıdır, çağrı silinince emir kalır ama çağrıyla bağı kopar;
- `rag_chunks` çağrıdan üretilmez (yalnızca servis kaydı, tekne notu, gider, abonelik), bu yüzden
  çağrı silmekle ilgili embedding yoktur;
- `audit_log` eklemeli tutulur ve kişisel veri içermez (yalnızca çağrı kimliği ve sabit değerler);
  silme olayı (`cagri_silindi`) buraya yazılır.

Sıra: veritabanı işlemi (silme + denetim kaydı) commit edilir, ardından dosya silinir. Dosya
silinemezse kayıt zaten gitmiştir; kalan dosya `orphan` olarak günlüğe yazılır (içerik özetli ad,
çağrıyla bağı yok) ve `ses_silindi=False` döner.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import ConflictError, NotFoundError
from app.core.security import ServiceCaller
from app.db.models.ai import Call
from app.domain.audit import AuditAction
from app.services.audit import record_audit_event
from app.storage.base import AudioStorage

log = structlog.get_logger(__name__)

# İşlenmekte olan çağrı silinmez (STT/analiz görevi yarışır); önce bitmesi veya zaman aşımı gerekir.
IN_FLIGHT_STATES = ("yaziya_cevriliyor", "isleniyor")


@dataclass(frozen=True)
class DeletionResult:
    call_id: UUID
    had_audio: bool
    audio_deleted: bool


async def delete_call(
    session: AsyncSession,
    storage: AudioStorage,
    call_id: UUID,
    *,
    actor: ServiceCaller | None = None,
    reason: str = "talep",
) -> DeletionResult:
    """Çağrıyı ve ses dosyasını siler; `cagri_silindi` denetim olayını aynı işlemde yazar."""
    call = await session.get(Call, call_id)
    if call is None:
        raise NotFoundError("Çağrı bulunamadı.")
    if call.state in IN_FLIGHT_STATES:
        raise ConflictError("Çağrı şu an işleniyor; işlem bitince tekrar deneyin.")
    audio_path = call.audio_path

    await record_audit_event(
        session,
        action=AuditAction.CAGRI_SILINDI,
        actor=actor,
        target_type="call",
        target_id=call_id,
        details={"neden": reason, "ses_vardi": audio_path is not None},
    )
    await session.execute(delete(Call).where(Call.id == call_id))
    await session.commit()

    audio_deleted = False
    if audio_path:
        try:
            audio_deleted = storage.delete(audio_path)
        except Exception:
            log.exception("call.delete.audio_failed", call_id=str(call_id))
        if not audio_deleted:
            log.warning("call.delete.audio_orphan", call_id=str(call_id))
    log.info("call.deleted", call_id=str(call_id), reason=reason)
    return DeletionResult(call_id, audio_path is not None, audio_deleted)


async def purge_expired_calls(
    session_factory: async_sessionmaker[AsyncSession],
    storage: AudioStorage,
    *,
    retention_days: int,
    batch_size: int = 200,
    now: datetime | None = None,
) -> dict[str, int]:
    """Saklama süresini aşan çağrıları siler. `retention_days <= 0` kapalıdır, hiçbir şey silmez.

    Süre çağrının `started_at` tarihinden sayılır. İşlenmekte olanlar atlanır (sonraki çalışmada
    alınır). Bir çağrının silinememesi diğerlerini durdurmaz.
    """
    if retention_days <= 0:
        return {"silinen": 0, "hata": 0, "atlanan_ses": 0}
    cutoff = (now or datetime.now(UTC)) - timedelta(days=retention_days)
    async with session_factory() as session:
        ids = list(
            await session.scalars(
                select(Call.id)
                .where(Call.started_at < cutoff, Call.state.notin_(IN_FLIGHT_STATES))
                .order_by(Call.started_at)
                .limit(batch_size)
            )
        )
    deleted = failed = audio_left = 0
    for call_id in ids:
        try:
            async with session_factory() as session:
                result = await delete_call(session, storage, call_id, reason="saklama_suresi")
            deleted += 1
            if result.had_audio and not result.audio_deleted:
                audio_left += 1
        except (NotFoundError, ConflictError):
            continue  # yarışta silindi veya işlenmeye başladı
        except Exception:
            failed += 1
            log.exception("call.retention.failed", call_id=str(call_id))
    log.info("call.retention.done", deleted=deleted, failed=failed, retention_days=retention_days)
    return {"silinen": deleted, "hata": failed, "atlanan_ses": audio_left}
