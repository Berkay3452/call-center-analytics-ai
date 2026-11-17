"""Kullanıcı hesapları, gerçek veritabanı testleri (#278).

Yalnızca `RUN_DB_TESTS=1` iken çalışır. Her test geri alınan bir işlemde çalışır; ortak
geliştirme veritabanına kalıcı satır yazılmaz. Yerel seed dosyası geçici klasöre yazılır.
"""

import csv
import os
import secrets
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings
from app.db.models.accounts import UserAccount
from app.db.models.external import Customer
from app.domain.accounts import MAX_FAILED_ATTEMPTS, AccountRole
from app.services.accounts import LoginFailure, create_account, verify_credentials
from scripts.seed_accounts import ADMIN_USERNAMES, seed_accounts

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_DB_TESTS") != "1", reason="RUN_DB_TESTS=1 değil (gerçek veritabanı gerekir)"
)

GOOD = secrets.token_urlsafe(16)  # çalışma zamanında üretilir; sabit parola yok
WRONG = secrets.token_urlsafe(16)


@pytest.fixture
async def conn() -> AsyncIterator[AsyncConnection]:
    engine = create_async_engine(Settings().database_url)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        try:
            yield connection
        finally:
            await transaction.rollback()
    await engine.dispose()


@pytest.fixture
def factory(conn: AsyncConnection) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )


async def test_seed_creates_account_for_every_owner_and_two_admins(
    factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    path = tmp_path / "seed_credentials.csv"
    async with factory() as session:
        before = await session.scalar(select(func.count(UserAccount.id)))
        owners, admins = await seed_accounts(session, path)
        await session.commit()
        customer_ids = set((await session.scalars(select(Customer.id))).all())
        accounts = (await session.scalars(select(UserAccount))).all()

    assert set(ADMIN_USERNAMES) <= {a.username for a in accounts}  # en az 2 yönetici
    assert {a.customer_id for a in accounts if a.role == "owner"} == customer_ids
    # Daha önce hesap varsa yalnızca eksikler eklenir (yeni hesap = müşteri + yönetici - mevcut).
    assert owners + admins == len(accounts) - (before or 0)


async def test_database_holds_only_argon2id_hashes_never_plaintext(
    factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    path = tmp_path / "seed_credentials.csv"
    async with factory() as session:
        await seed_accounts(session, path)
        await session.commit()
        hashes = list((await session.scalars(select(UserAccount.password_hash))).all())
        # Tablonun her sütunu metin olarak taranır: düz parola hiçbir yerde olmamalı.
        dump = (await session.execute(text("SELECT t::text FROM user_accounts t"))).scalars().all()

    assert hashes and all(h.startswith("$argon2id$") for h in hashes)
    passwords = [row["password"] for row in csv.DictReader(path.open(encoding="utf-8"))]
    blob = "\n".join(dump)
    assert all(p not in blob for p in passwords)


async def test_seed_is_idempotent_and_does_not_rewrite_passwords(
    factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    path = tmp_path / "seed_credentials.csv"
    async with factory() as session:
        await seed_accounts(session, path)
        first = path.read_text(encoding="utf-8")
        again = await seed_accounts(session, path)
    assert again == (0, 0)
    assert path.read_text(encoding="utf-8") == first


async def test_seeded_credentials_actually_work_and_lock(
    factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    path = tmp_path / "seed_credentials.csv"
    async with factory() as session:
        await seed_accounts(session, path)
        row = next(csv.DictReader(path.open(encoding="utf-8")))
        ok = await verify_credentials(session, row["username"].upper(), row["password"])
        assert ok.ok and ok.role is AccountRole(row["role"])
        for _ in range(MAX_FAILED_ATTEMPTS):
            await verify_credentials(session, row["username"], WRONG)
        locked = await verify_credentials(session, row["username"], row["password"])
        assert not locked.ok and locked.failure is LoginFailure.LOCKED


async def test_database_rejects_inconsistent_role_customer_pairs(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    async with factory() as session:
        with pytest.raises(IntegrityError):
            await create_account(
                session,
                username="sahipsiz",
                password=GOOD,
                role=AccountRole.OWNER,
                customer_id=None,
            )
    async with factory() as session:
        with pytest.raises(IntegrityError):
            await create_account(
                session,
                username="adminli-sahip",
                password=GOOD,
                role=AccountRole.ADMIN,
                customer_id=uuid4(),
            )


async def test_username_must_be_unique_and_lowercase(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    async with factory() as session:
        await create_account(session, username="Tekrar", password=GOOD, role=AccountRole.ADMIN)
        with pytest.raises(IntegrityError):
            await create_account(session, username="tekrar", password=GOOD, role=AccountRole.ADMIN)
