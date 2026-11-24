"""Seed kullanıcı hesapları (#278, #381): her tekne sahibi için bir hesap + 2 yönetici.

Çalıştırma: `uv run python -m scripts.seed_accounts` (veritabanı ve migration hazır olmalı).

Giriş kimliği **e-postadır** (`username` sütununda küçük harfle): müşterinin `customers.email`
adresi, yoksa sentetik `ad.soyad@micousta.test`; yöneticiler `yonetici1@micousta.test`,
`yonetici2@micousta.test`. Eski kullanıcı adlarıyla açılmış hesaplar e-postaya taşınır (parola
karması korunur, yerel CSV'deki kullanıcı adı da güncellenir).

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
    EMAIL_DOMAIN,
    create_account,
    derive_email,
    generate_password,
    normalize_username,
)

CREDENTIALS_PATH = Path(__file__).resolve().parents[1] / ".local" / "seed_credentials.csv"
LEGACY_ADMIN_USERNAMES = ("yonetici1", "yonetici2")
ADMIN_USERNAMES = tuple(f"{name}@{EMAIL_DOMAIN}" for name in LEGACY_ADMIN_USERNAMES)


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


def _rename_in_credentials(path: Path, renames: dict[tuple[str, str], str]) -> None:
    """CSV'deki (eski kullanıcı adı, rol) satırlarını yeni kullanıcı adıyla günceller."""
    if not renames or not path.exists():
        return
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    changed = False
    for row in rows[1:]:
        key = (row[0], row[1]) if len(row) >= 2 else None
        if key in renames:
            row[0] = renames[key]
            changed = True
    if changed:
        with path.open("w", newline="", encoding="utf-8") as fh:
            csv.writer(fh).writerows(rows)


def _owner_email(customer: Customer, taken: set[str]) -> str:
    """Müşterinin e-postası (küçük harf, tekil); yoksa ya da başkasındaysa sentetik üretilir."""
    email = normalize_username(customer.email) if customer.email else ""
    if email and email not in taken:
        taken.add(email)
        return email
    return derive_email(customer.full_name, taken)


async def seed_accounts(
    session: AsyncSession, credentials_path: Path = CREDENTIALS_PATH
) -> tuple[int, int]:
    """Eksik hesapları oluşturur; (yeni sahip hesabı, yeni yönetici hesabı) sayısını döner.

    Eski kullanıcı adlı hesaplar e-postaya taşınır (sayıya girmez). Düz parolalar önce yerel
    dosyaya yazılır, sonra veritabanı işlemi çağıran tarafından onaylanır.
    """
    owners_existing = list((await session.scalars(select(OwnerAccount))).all())
    admins_existing = list((await session.scalars(select(AdminAccount))).all())
    customers = (
        await session.scalars(select(Customer).order_by(Customer.created_at, Customer.id))
    ).all()
    by_id = {c.id: c for c in customers}

    # 1) Eski kullanıcı adlarını e-postaya taşı (parola karması aynı kalır).
    taken = {a.username for a in owners_existing} | {a.username for a in admins_existing}
    renames: dict[tuple[str, str], str] = {}
    for admin in admins_existing:
        if admin.username in LEGACY_ADMIN_USERNAMES:
            new = f"{admin.username}@{EMAIL_DOMAIN}"
            if new not in taken:
                renames[(admin.username, AccountRole.ADMIN.value)] = new
                taken.discard(admin.username)
                taken.add(new)
                admin.username = new
    for owner in owners_existing:
        customer = by_id.get(owner.customer_id)
        if customer is None or "@" in owner.username:
            continue
        taken.discard(owner.username)
        new = _owner_email(customer, taken)
        renames[(owner.username, AccountRole.OWNER.value)] = new
        owner.username = new
    if renames:
        await session.flush()
        _rename_in_credentials(credentials_path, renames)

    # 2) Eksik hesapları oluştur.
    has_account = {a.customer_id for a in owners_existing}
    admin_taken = {a.username for a in admins_existing}
    plan: list[tuple[str, str, AccountRole, UUID | None]] = []
    for customer in customers:
        if customer.id in has_account:
            continue
        plan.append(
            (_owner_email(customer, taken), generate_password(), AccountRole.OWNER, customer.id)
        )
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
            display_name=username.split("@")[0] if role is AccountRole.ADMIN else None,
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
