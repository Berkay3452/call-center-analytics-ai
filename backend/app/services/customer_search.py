"""Müşteri ve tekne arama (#209): çağrıyı elle eşleştirirken doğru müşteriyi bulmak için.

Arama Türkçe karakter ve büyük/küçük harf duyarsızdır ("ismail çelik" = "İSMAİL CELIK"); eşleşme
`call_matching.normalize_text` ile aynı kurallarla veritabanında yapılır, bu yüzden tüm müşteriler
belleğe çekilmez. Telefon yalnızca rakamlar üzerinden aranır ("0532 123" = "+90 532 123 45 67").
Müşterinin teknelerinden birinin adı da eşleşirse müşteri bulunur.
"""

import re
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.external import Boat, Customer
from app.schemas.api import CustomerBoatOut, CustomerSearchItem
from app.services.call_matching import normalize_text

MIN_PHONE_DIGITS = 3


def fold(column: Any) -> ColumnElement[str]:
    """`normalize_text`'in SQL karşılığı: Türkçe I/İ, küçük harf, ASCII, noktalama."""
    folded = func.replace(func.replace(column, "İ", "i"), "I", "ı")
    folded = func.translate(func.lower(folded), "ığüşöçâîû", "igusocaiu")
    folded = func.regexp_replace(folded, r"[^[:alnum:][:space:]]", " ", "g")
    return func.trim(func.regexp_replace(folded, r"\s+", " ", "g"))


def digits_of(column: Any) -> ColumnElement[str]:
    return func.regexp_replace(column, r"\D", "", "g")


def build_condition(query: str) -> ColumnElement[bool] | None:
    """Arama ifadesinden koşul üretir. Aranabilir hiçbir şey yoksa `None`."""
    normalized = normalize_text(query)
    digits = re.sub(r"\D", "", query)
    conditions: list[ColumnElement[bool]] = []

    if normalized:
        tokens = normalized.split()
        conditions.append(
            and_(*[fold(Customer.full_name).contains(token, autoescape=True) for token in tokens])
        )
        conditions.append(
            exists().where(
                Boat.owner_id == Customer.id,
                fold(Boat.name).contains(normalized, autoescape=True),
            )
        )
    if len(digits) >= MIN_PHONE_DIGITS:
        conditions.append(digits_of(Customer.phone).contains(digits, autoescape=True))
    return or_(*conditions) if conditions else None


async def search_customers(
    session: AsyncSession, query: str | None, limit: int = 20
) -> list[CustomerSearchItem]:
    """Ada, telefona veya tekne adına göre müşteri arar; `query` boşsa ilk `limit` müşteri."""
    stmt = select(Customer).order_by(Customer.full_name, Customer.id).limit(limit)
    if query and query.strip():
        condition = build_condition(query)
        if condition is None:
            return []
        stmt = stmt.where(condition)
    customers = (await session.execute(stmt)).scalars().all()
    if not customers:
        return []

    boats_by_owner: dict[UUID, list[CustomerBoatOut]] = {c.id: [] for c in customers}
    boats = (
        await session.execute(
            select(Boat).where(Boat.owner_id.in_(boats_by_owner)).order_by(Boat.name, Boat.id)
        )
    ).scalars()
    for boat in boats:
        boats_by_owner[boat.owner_id].append(
            CustomerBoatOut(id=boat.id, name=boat.name, model=boat.model)
        )
    return [
        CustomerSearchItem(id=c.id, name=c.full_name, phone=c.phone, boats=boats_by_owner[c.id])
        for c in customers
    ]
