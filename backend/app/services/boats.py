"""Tekne sahibinin kendi tekneleri (#383): listele ve ekle; `boats` tablosuna yazar."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError
from app.db.models.external import Boat

MAX_BOATS_PER_OWNER = 20  # kötüye kullanım sınırı


async def list_boats(session: AsyncSession, owner_id: UUID) -> list[Boat]:
    rows = await session.scalars(
        select(Boat).where(Boat.owner_id == owner_id).order_by(Boat.created_at, Boat.id)
    )
    return list(rows.all())


async def add_boat(
    session: AsyncSession,
    owner_id: UUID,
    *,
    name: str,
    model: str | None,
    year: int | None,
    marina: str | None,
) -> Boat:
    """Sahibin adına tekne ekler. Aynı adlı ikinci tekne ve 20'den fazla tekne reddedilir."""
    count = await session.scalar(
        select(func.count()).select_from(Boat).where(Boat.owner_id == owner_id)
    )
    if (count or 0) >= MAX_BOATS_PER_OWNER:
        raise ConflictError(f"En fazla {MAX_BOATS_PER_OWNER} tekne ekleyebilirsiniz.")
    same = await session.scalar(
        select(Boat.id).where(Boat.owner_id == owner_id, func.lower(Boat.name) == name.lower())
    )
    if same is not None:
        raise ConflictError("Bu adla kayıtlı bir tekneniz zaten var.")
    boat = Boat(owner_id=owner_id, name=name, model=model, year=year, marina=marina)
    session.add(boat)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError("Tekne eklenemedi.") from exc
    return boat
