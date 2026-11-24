"""Seed kullanıcı hesapları (#278): her tekne sahibi için bir hesap + 2 yönetici.

Çalıştırma: `uv run python -m scripts.seed_accounts` (veritabanı ve migration hazır olmalı).

Parolalar rastgele üretilir ve YALNIZCA git'e girmeyen yerel dosyaya yazılır
(`backend/.local/seed_credentials.csv`, `.gitignore`'da). Repoya, belgeye, günlüğe veya çıktıya
yazılmaz; bu betik de parolayı ekrana basmaz. İdempotent: hesabı olan müşteri/yönetici atlanır
(yeniden çalıştırınca yeni parola üretilmez, yalnızca eksikler eklenir).
"""

import asyncio
import contextlib
import csv
import os
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.models.accounts import AdminAccount, OwnerAccount
from app.db.models.external import Customer
from app.db.session import worker_session
from app.domain.accounts import AccountRole
from app.services.accounts import (
    create_account,
    derive_username,
    generate_password,
)

CREDENTIALS_PATH = Path(__file__).resolve().parents[1] / ".local" / "seed_credentials.csv"
ADMIN_USERNAMES = ("yonetici1", "yonetici2")


def _append_credentials(path: Path, rows: list[tuple[str, str, str]]) -> None:
    """Yeni (kullanıcı adı, rol, parola) satırlarını ekler; dosya yalnızca sahibine açıktır."""
    path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        if new_file:
            writer.writerow(["username", "role", "password"])
        writer.writerows(rows)
    with contextlib.suppress(OSError):
        os.chmod(path, 0o600)  # Windows'ta etkisizdir, sorun değil


async def seed_accounts(
    session: AsyncSession, credentials_path: Path = CREDENTIALS_PATH
) -> tuple[int, int]:
    """Eksik hesapları oluşturur; (yeni sahip hesabı, yeni yönetici hesabı) sayısını döner.

    Düz parolalar önce yerel dosyaya yazılır, sonra veritabanı işlemi çağıran tarafından
    onaylanır (işlem başarısız olursa dosyada fazladan satır kalabilir; zararsızdır).
    """
    owners_existing = list((await session.scalars(select(OwnerAccount))).all())
    admins_existing = list((await session.scalars(select(AdminAccount))).all())
    taken = {a.username for a in owners_existing} | {a.username for a in admins_existing}
    has_account = {a.customer_id for a in owners_existing}
    admin_taken = {a.username for a in admins_existing}

    customers = (
        await session.scalars(select(Customer).order_by(Customer.created_at, Customer.id))
    ).all()
    plan: list[tuple[str, str, AccountRole, UUID | None]] = []
    for customer in customers:
        if customer.id in has_account:
            continue
        username = derive_username(customer.full_name, taken)
        plan.append((username, generate_password(), AccountRole.OWNER, customer.id))
    for admin_name in ADMIN_USERNAMES:
        if admin_name not in admin_taken:
            admin_taken.add(admin_name)
            plan.append((admin_name, generate_password(), AccountRole.ADMIN, None))

    if not plan:
        return 0, 0
    _append_credentials(credentials_path, [(u, r.value, p) for u, p, r, _ in plan])
    for username, password, role, customer_id in plan:
        await create_account(
            session,
            username=username,
            password=password,
            role=role,
            customer_id=customer_id,
            display_name=username if role is AccountRole.ADMIN else None,
        )
    owners = sum(1 for _, _, role, _ in plan if role is AccountRole.OWNER)
    return owners, len(plan) - owners


async def main() -> None:
    settings = Settings()
    async with worker_session(settings) as session:
        owners, admins = await seed_accounts(session)
        await session.commit()
    where = CREDENTIALS_PATH if (owners or admins) else "(yeni hesap yok)"
    print(f"Hesaplar: {owners} tekne sahibi, {admins} yönetici eklendi. Parolalar: {where}")


if __name__ == "__main__":
    asyncio.run(main())
