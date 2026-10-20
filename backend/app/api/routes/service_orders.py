"""Servis emirleri API uçları (#118): liste, detay ve durum güncelleme.

Sözleşme: docs/api.md.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import ServiceCallerDep, SessionDep
from app.schemas.api import (
    ServiceOrderDetail,
    ServiceOrderFilters,
    ServiceOrderListItem,
    ServiceOrderStatusUpdate,
)
from app.schemas.common import ErrorResponse, Page
from app.services import service_orders

router = APIRouter(prefix="/service-orders", tags=["service-orders"])


@router.get(
    "",
    response_model=Page[ServiceOrderListItem],
    summary="Servis emirleri listesi",
    operation_id="listServiceOrders",
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
    },
)
async def list_service_orders(
    _: ServiceCallerDep,
    session: SessionDep,
    filters: Annotated[ServiceOrderFilters, Query()],
) -> Page[ServiceOrderListItem]:
    """Filtrelere göre sayfalı servis emirleri listesi döndürür."""
    return await service_orders.list_service_orders(session, filters)


@router.get(
    "/{order_id}",
    response_model=ServiceOrderDetail,
    summary="Servis emri detayı",
    operation_id="getServiceOrderById",
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
async def get_service_order(
    order_id: UUID,
    _: ServiceCallerDep,
    session: SessionDep,
) -> ServiceOrderDetail:
    """Belirli bir servis emrinin müşteri, tekne, usta ve kaynak çağrı detaylarını getirir."""
    return await service_orders.get_service_order_detail(session, order_id)


@router.patch(
    "/{order_id}/status",
    response_model=ServiceOrderDetail,
    summary="Servis emri durumunu güncelle",
    operation_id="updateServiceOrderStatus",
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
async def update_service_order_status(
    order_id: UUID,
    payload: ServiceOrderStatusUpdate,
    _: ServiceCallerDep,
    session: SessionDep,
) -> ServiceOrderDetail:
    """Servis emrinin durumunu iş akışına göre günceller.

    İş akışı:
    yeni_atandi -> kesifte -> onaylandi -> devam_ediyor -> tamamlandi.
    Geçersiz bir durum geçişinde 400 Bad Request döner.
    tamamlandi durumuna geçildiğinde completed_at zamanı otomatik kaydedilir.
    """
    async with session.begin():
        return await service_orders.update_service_order_status(session, order_id, payload.status)
