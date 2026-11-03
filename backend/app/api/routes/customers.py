"""Müşteri arama ucu (#209): çağrıyı elle eşleştirmek için müşteri ve tekne bulur (Admin).

Sözleşme: docs/api.md. Eşleştirmenin kendisi `PUT /calls/{id}/match`'tir (girdi biçimi değişmedi).
"""

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import ServiceCallerDep, SessionDep
from app.schemas.api import CustomerSearchItem
from app.schemas.common import ErrorResponse
from app.services import customer_search

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get(
    "",
    response_model=list[CustomerSearchItem],
    summary="Müşteri ve tekne ara",
    operation_id="searchCustomers",
    responses={401: {"model": ErrorResponse}},
)
async def search_customers(
    _: ServiceCallerDep,
    session: SessionDep,
    q: Annotated[
        str | None,
        Query(max_length=100, description="Ad, telefon veya tekne adı; boşsa ilk müşteriler."),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=50, description="En çok kaç müşteri.")] = 20,
) -> list[CustomerSearchItem]:
    """Ada (Türkçe karakter/harf duyarsız, kısmi), telefona (rakam bazlı) veya tekneye göre arar."""
    return await customer_search.search_customers(session, q, limit)
