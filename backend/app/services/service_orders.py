"""Servis emirleri okuma ve durum güncelleme servisi (#118).

İş akışı:
- `yeni_atandi` -> `kesifte` -> `onaylandi` -> `devam_ediyor` -> `tamamlandi`
- Geçersiz geçişlerde 400 Bad Request fırlatılır.
- `tamamlandi` durumuna geçildiğinde `completed_at` doldurulur.
"""

from datetime import UTC, datetime, time
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, NotFoundError
from app.db.models.ai import AnalysisResult as AnalysisRow
from app.db.models.ai import Call, CrmReview
from app.db.models.external import Boat, Craftsman, Customer, ServiceOrder
from app.domain.enums import ServiceOrderStatus
from app.schemas.api import (
    ServiceOrderBoatOut,
    ServiceOrderCraftsmanOut,
    ServiceOrderCustomerOut,
    ServiceOrderDetail,
    ServiceOrderFilters,
    ServiceOrderListItem,
    ServiceOrderSourceCallOut,
)
from app.schemas.common import Page

ISTANBUL_TZ = ZoneInfo("Europe/Istanbul")

ALLOWED_STATUS_TRANSITIONS: dict[ServiceOrderStatus, set[ServiceOrderStatus]] = {
    ServiceOrderStatus.YENI_ATANDI: {ServiceOrderStatus.KESIFTE},
    ServiceOrderStatus.KESIFTE: {ServiceOrderStatus.ONAYLANDI},
    ServiceOrderStatus.ONAYLANDI: {ServiceOrderStatus.DEVAM_EDIYOR},
    ServiceOrderStatus.DEVAM_EDIYOR: {ServiceOrderStatus.TAMAMLANDI},
    ServiceOrderStatus.TAMAMLANDI: set(),
}


def _build_filter_conditions(filters: ServiceOrderFilters) -> list[Any]:
    conditions: list[Any] = []

    if filters.status:
        conditions.append(ServiceOrder.status == filters.status.value)

    if filters.date_from:
        start_dt = datetime.combine(filters.date_from, time.min, tzinfo=ISTANBUL_TZ)
        conditions.append(ServiceOrder.created_at >= start_dt)

    if filters.date_to:
        end_dt = datetime.combine(filters.date_to, time.max, tzinfo=ISTANBUL_TZ)
        conditions.append(ServiceOrder.created_at <= end_dt)

    if filters.marina and filters.marina.strip():
        marina_val = filters.marina.strip()
        conditions.append(or_(Boat.marina == marina_val, Customer.marina == marina_val))

    if filters.q and filters.q.strip():
        term = filters.q.strip().replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
        search = f"%{term}%"
        conditions.append(
            or_(
                Customer.full_name.ilike(search, escape="\\"),
                Boat.name.ilike(search, escape="\\"),
                Craftsman.full_name.ilike(search, escape="\\"),
                ServiceOrder.description.ilike(search, escape="\\"),
                ServiceOrder.category.ilike(search, escape="\\"),
            )
        )

    return conditions


async def list_service_orders(
    session: AsyncSession, filters: ServiceOrderFilters
) -> Page[ServiceOrderListItem]:
    """Sayfalı ve filtreli servis emirleri listesini döndürür."""
    conditions = _build_filter_conditions(filters)

    count_stmt = (
        select(func.count(ServiceOrder.id))
        .select_from(ServiceOrder)
        .join(Boat, ServiceOrder.boat_id == Boat.id)
        .join(Customer, ServiceOrder.customer_id == Customer.id)
        .outerjoin(Craftsman, ServiceOrder.craftsman_id == Craftsman.id)
    )
    if conditions:
        count_stmt = count_stmt.where(*conditions)

    total = (await session.execute(count_stmt)).scalar_one() or 0

    query = (
        select(
            ServiceOrder,
            Customer.full_name.label("customer_name"),
            Customer.phone.label("customer_phone"),
            Boat.name.label("boat_name"),
            Boat.model.label("boat_model"),
            Boat.marina.label("boat_marina"),
            Craftsman.full_name.label("craftsman_name"),
        )
        .join(Boat, ServiceOrder.boat_id == Boat.id)
        .join(Customer, ServiceOrder.customer_id == Customer.id)
        .outerjoin(Craftsman, ServiceOrder.craftsman_id == Craftsman.id)
    )
    if conditions:
        query = query.where(*conditions)

    offset = (filters.page - 1) * filters.page_size
    query = (
        query.order_by(ServiceOrder.created_at.desc(), ServiceOrder.id.desc())
        .offset(offset)
        .limit(filters.page_size)
    )

    rows = (await session.execute(query)).all()

    items = [
        ServiceOrderListItem(
            id=row[0].id,
            status=ServiceOrderStatus(row[0].status),
            category=row[0].category,
            description=row[0].description,
            scheduled_at=row[0].scheduled_at,
            completed_at=row[0].completed_at,
            created_at=row[0].created_at,
            customer_id=row[0].customer_id,
            customer_name=row.customer_name,
            customer_phone=row.customer_phone,
            boat_id=row[0].boat_id,
            boat_name=row.boat_name,
            boat_model=row.boat_model,
            marina=row.boat_marina,
            craftsman_id=row[0].craftsman_id,
            craftsman_name=row.craftsman_name,
            source_call_id=row[0].source_call_id,
        )
        for row in rows
    ]

    return Page(
        items=items,
        total=total,
        page=filters.page,
        page_size=filters.page_size,
    )


async def get_service_order_detail(session: AsyncSession, order_id: UUID) -> ServiceOrderDetail:
    """Tekil servis emri detayını, ilişkili müşteri, tekne, usta ve kaynak çağrıyla getirir."""
    stmt = (
        select(ServiceOrder, Customer, Boat, Craftsman)
        .join(Customer, ServiceOrder.customer_id == Customer.id)
        .join(Boat, ServiceOrder.boat_id == Boat.id)
        .outerjoin(Craftsman, ServiceOrder.craftsman_id == Craftsman.id)
        .where(ServiceOrder.id == order_id)
    )
    res = (await session.execute(stmt)).first()
    if res is None:
        raise NotFoundError("Servis emri bulunamadı.")

    order, customer, boat, craftsman = res

    source_call_out: ServiceOrderSourceCallOut | None = None
    if order.source_call_id is not None:
        call = await session.get(Call, order.source_call_id)
        if call is not None:
            # Servis emrini doğuran inceleme ve onun analiz sürümü esas alınır: çağrı onaydan
            # sonra yeniden analiz edilse de emir, onaylanan sürümün alanlarını göstermeli.
            review = await session.scalar(
                select(CrmReview).where(CrmReview.service_order_id == order.id).limit(1)
            )
            if review is not None:
                latest_analysis = await session.get(AnalysisRow, review.analysis_id)
            else:
                latest_analysis = (
                    await session.execute(
                        select(AnalysisRow)
                        .where(AnalysisRow.call_id == call.id)
                        .order_by(AnalysisRow.version.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()

            edited = review.edited_fields if review else {}
            source_call_out = ServiceOrderSourceCallOut(
                call_id=call.id,
                started_at=call.started_at,
                customer_name=call.customer_name or customer.full_name,
                boat_name=call.boat_name or boat.name,
                switchboard_outcome=call.switchboard_outcome,
                request_category=edited.get(
                    "request_category",
                    latest_analysis.request_category if latest_analysis else None,
                ),
                location=edited.get(
                    "location", latest_analysis.location if latest_analysis else None
                ),
                problem=edited.get("problem", latest_analysis.problem if latest_analysis else None),
                service_mode=edited.get(
                    "service_mode",
                    latest_analysis.service_mode if latest_analysis else None,
                ),
                urgency=edited.get("urgency", latest_analysis.urgency if latest_analysis else None),
                potential_job=edited.get(
                    "potential_job",
                    latest_analysis.potential_job if latest_analysis else None,
                ),
                next_action=edited.get(
                    "next_action",
                    latest_analysis.next_action if latest_analysis else None,
                ),
                summary=latest_analysis.summary if latest_analysis else None,
                crm_review_status=review.status if review else None,
                crm_review_note=review.note if review else None,
                crm_reviewed_at=review.reviewed_at if review else None,
            )

    return ServiceOrderDetail(
        id=order.id,
        status=ServiceOrderStatus(order.status),
        category=order.category,
        description=order.description,
        scheduled_at=order.scheduled_at,
        completed_at=order.completed_at,
        created_at=order.created_at,
        customer=ServiceOrderCustomerOut(
            id=customer.id,
            full_name=customer.full_name,
            phone=customer.phone,
            email=customer.email,
            marina=customer.marina,
        ),
        boat=ServiceOrderBoatOut(
            id=boat.id,
            name=boat.name,
            model=boat.model,
            year=boat.year,
            marina=boat.marina,
        ),
        craftsman=(
            ServiceOrderCraftsmanOut(
                id=craftsman.id,
                full_name=craftsman.full_name,
                specialty=craftsman.specialty,
                phone=craftsman.phone,
            )
            if craftsman
            else None
        ),
        source_call=source_call_out,
    )


async def update_service_order_status(
    session: AsyncSession, order_id: UUID, new_status: ServiceOrderStatus
) -> ServiceOrderDetail:
    """Servis emrinin durumunu günceller. Geçersiz geçişlerde 400 döner."""
    order = await session.get(ServiceOrder, order_id, with_for_update=True)
    if order is None:
        raise NotFoundError("Servis emri bulunamadı.")

    current_status = ServiceOrderStatus(order.status)
    valid_next = ALLOWED_STATUS_TRANSITIONS.get(current_status, set())
    if new_status not in valid_next:
        raise AppError(
            f"Geçersiz durum geçişi: '{current_status.value}' durumundan "
            f"'{new_status.value}' durumuna geçilemez.",
            details={"current_status": current_status.value, "target_status": new_status.value},
        )

    order.status = new_status.value
    if new_status == ServiceOrderStatus.TAMAMLANDI:
        order.completed_at = datetime.now(UTC)

    await session.flush()
    return await get_service_order_detail(session, order_id)
