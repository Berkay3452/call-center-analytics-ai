"""CRM önerisi inceleme servisi (#106): onayla, reddet, düzenle.

İş akışı:
- Analizden çıkan CRM önerisi admin tarafından onaylanır, reddedilir veya düzenlenerek onaylanır.
- Onayda çağrının customer_id ve boat_id değerleri varsa service_orders kaydı oluşur.
- Eşleşme yoksa (müşteri/tekne bilinmiyorsa) 409 Conflict döner ("Müşteri/tekne eşleşmedi").
- Onay <-> red geçişi serbesttir; servis emri yalnızca İLK onayda oluşur, sonraki onaylar
  aynı servis emrini döner (idempotent).
- Çağrı yeniden analiz edilirse yeni analiz sürümü henüz incelenmediği için durumu 'bekliyor' olur.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.db.models.ai import AnalysisResult as AnalysisRow
from app.db.models.ai import Call, CrmReview
from app.db.models.external import ServiceOrder
from app.domain.enums import CrmReviewStatus, ServiceOrderStatus
from app.schemas.api import CrmApproveIn, CrmRejectIn, CrmReviewOut

CRM_EDITABLE_FIELDS = {
    "request_category",
    "location",
    "problem",
    "service_mode",
    "urgency",
    "potential_job",
    "next_action",
}


def _format_service_order_description(problem: str | None, potential_job: str | None) -> str | None:
    parts: list[str] = []
    if problem and problem.strip():
        parts.append(problem.strip())
    if potential_job and potential_job.strip():
        parts.append(f"Potansiyel iş: {potential_job.strip()}" if parts else potential_job.strip())
    return " — ".join(parts) if parts else None


async def _get_latest_analysis_row(session: AsyncSession, call_id: UUID) -> AnalysisRow | None:
    return (
        await session.execute(
            select(AnalysisRow)
            .where(AnalysisRow.call_id == call_id)
            .order_by(AnalysisRow.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def approve_crm_record(
    session: AsyncSession,
    call_id: UUID,
    payload: CrmApproveIn,
) -> CrmReviewOut:
    """CRM önerisini onaylar (veya düzenleyerek onaylar) ve servis emri oluşturur (#106)."""
    call = await session.get(Call, call_id)
    if call is None:
        raise NotFoundError("Çağrı bulunamadı.")

    latest_analysis = await _get_latest_analysis_row(session, call_id)
    if latest_analysis is None:
        raise NotFoundError("Çağrıya ait analiz bulunamadı.")

    # Müşteri ve tekne eşleşmesi zorunludur (service_orders NOT NULL foreign keys)
    if call.customer_id is None or call.boat_id is None:
        raise ConflictError("Müşteri/tekne eşleşmedi")

    # Yalnızca gönderilen 7 alanı ayıkla
    raw_dict = payload.model_dump(exclude_unset=True)
    edited_fields: dict[str, Any] = {}
    for k in CRM_EDITABLE_FIELDS:
        if k in raw_dict:
            val = raw_dict[k]
            edited_fields[k] = val.value if hasattr(val, "value") else val

    note = raw_dict.get("note")

    # Mevcut inceleme kaydı var mı?
    review = await session.scalar(
        select(CrmReview).where(CrmReview.analysis_id == latest_analysis.id)
    )

    # Efektif değerler: düzenlenmiş alanlar varsa onlar, yoksa analiz çıktısı
    effective_category = edited_fields.get("request_category", latest_analysis.request_category)
    effective_problem = edited_fields.get("problem", latest_analysis.problem)
    effective_potential_job = edited_fields.get("potential_job", latest_analysis.potential_job)

    # Servis emri: Yalnızca ilk onayda oluşturulur (idempotent)
    service_order_id: UUID | None = None
    if review is not None and review.service_order_id is not None:
        service_order_id = review.service_order_id
    else:
        description = _format_service_order_description(effective_problem, effective_potential_job)
        new_order = ServiceOrder(
            customer_id=call.customer_id,
            boat_id=call.boat_id,
            status=ServiceOrderStatus.YENI_ATANDI.value,
            category=effective_category,
            description=description,
            source_call_id=call.id,
        )
        session.add(new_order)
        await session.flush()
        service_order_id = new_order.id

    now = datetime.now(UTC)
    if review is None:
        review = CrmReview(
            analysis_id=latest_analysis.id,
            call_id=call.id,
            status=CrmReviewStatus.ONAYLANDI.value,
            edited_fields=edited_fields,
            note=note,
            reviewed_at=now,
            service_order_id=service_order_id,
        )
        session.add(review)
    else:
        review.status = CrmReviewStatus.ONAYLANDI.value
        review.edited_fields = edited_fields
        if note is not None:
            review.note = note
        review.reviewed_at = now
        review.service_order_id = service_order_id

    # İstek oturumu commit etmez (get_db_session); yazma kararı servis katmanındadır.
    await session.commit()

    return CrmReviewOut(
        id=review.id,
        call_id=review.call_id,
        analysis_id=review.analysis_id,
        status=CrmReviewStatus(review.status),
        edited_fields=review.edited_fields,
        note=review.note,
        reviewed_at=review.reviewed_at,
        service_order_id=review.service_order_id,
    )


async def reject_crm_record(
    session: AsyncSession,
    call_id: UUID,
    payload: CrmRejectIn,
) -> CrmReviewOut:
    """CRM önerisini reddeder (#106)."""
    call = await session.get(Call, call_id)
    if call is None:
        raise NotFoundError("Çağrı bulunamadı.")

    latest_analysis = await _get_latest_analysis_row(session, call_id)
    if latest_analysis is None:
        raise NotFoundError("Çağrıya ait analiz bulunamadı.")

    review = await session.scalar(
        select(CrmReview).where(CrmReview.analysis_id == latest_analysis.id)
    )

    now = datetime.now(UTC)
    if review is None:
        review = CrmReview(
            analysis_id=latest_analysis.id,
            call_id=call.id,
            status=CrmReviewStatus.REDDEDILDI.value,
            edited_fields={},
            note=payload.note,
            reviewed_at=now,
            service_order_id=None,
        )
        session.add(review)
    else:
        review.status = CrmReviewStatus.REDDEDILDI.value
        if payload.note is not None:
            review.note = payload.note
        review.reviewed_at = now

    # İstek oturumu commit etmez (get_db_session); yazma kararı servis katmanındadır.
    await session.commit()

    return CrmReviewOut(
        id=review.id,
        call_id=review.call_id,
        analysis_id=review.analysis_id,
        status=CrmReviewStatus(review.status),
        edited_fields=review.edited_fields,
        note=review.note,
        reviewed_at=review.reviewed_at,
        service_order_id=review.service_order_id,
    )
