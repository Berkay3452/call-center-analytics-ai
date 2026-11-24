"""Tekne ekleme/listeleme servisi, gerçek veritabanı (#383). Yalnızca `RUN_DB_TESTS=1`.

Her test geri alınan işlemde çalışır; ortak geliştirme veritabanına kalıcı satır yazılmaz.
"""

import os
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, create_async_engine

from app.core.config import Settings
from app.core.errors import ConflictError
from app.db.models.external import Customer
from app.services.boats import MAX_BOATS_PER_OWNER, add_boat, list_boats

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_DB_TESTS") != "1", reason="RUN_DB_TESTS=1 değil (gerçek veritabanı gerekir)"
)


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(Settings().database_url)
    conn: AsyncConnection
    async with engine.connect() as conn:
        transaction = await conn.begin()
        async with AsyncSession(bind=conn, expire_on_commit=False) as s:
            yield s
        await transaction.rollback()
    await engine.dispose()


async def _customer(session: AsyncSession, name: str) -> Customer:
    c = Customer(full_name=name)
    session.add(c)
    await session.flush()
    return c


async def test_owner_sees_only_own_boats(session: AsyncSession) -> None:
    a, b = await _customer(session, "Sahip A"), await _customer(session, "Sahip B")
    await add_boat(session, a.id, name="Rüzgar", model="Jeanneau", year=2020, marina="Göcek")
    await add_boat(session, b.id, name="Fırtına", model=None, year=None, marina=None)
    mine = await list_boats(session, a.id)
    assert [x.name for x in mine] == ["Rüzgar"] and mine[0].marina == "Göcek"


async def test_duplicate_name_is_rejected_case_insensitively(session: AsyncSession) -> None:
    a = await _customer(session, "Sahip A")
    await add_boat(session, a.id, name="Rüzgar", model=None, year=None, marina=None)
    with pytest.raises(ConflictError):
        await add_boat(session, a.id, name="rüzgar", model=None, year=None, marina=None)


async def test_boat_limit_per_owner(session: AsyncSession) -> None:
    a = await _customer(session, "Sahip A")
    for i in range(MAX_BOATS_PER_OWNER):
        await add_boat(session, a.id, name=f"Tekne {i}", model=None, year=None, marina=None)
    with pytest.raises(ConflictError):
        await add_boat(session, a.id, name="Fazla", model=None, year=None, marina=None)
