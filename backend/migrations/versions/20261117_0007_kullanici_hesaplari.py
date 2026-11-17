"""Kullanıcı hesapları (#278): `user_accounts` tablosu.

- Tekne sahibi (`owner`, `customer_id` zorunlu) ve yönetici (`admin`, `customer_id` boş) hesabı.
- Parola yalnızca argon2id karması; düz parola hiçbir yerde tutulmaz.
- Başarısız deneme sayacı ve geçici kilit alanları (giriş ucu henüz açık değildir).

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_accounts",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("username", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("customer_id", sa.UUID(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("failed_attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "password_changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("role IN ('admin', 'owner')", name=op.f("ck_user_accounts_role")),
        sa.CheckConstraint(
            "username = lower(username) AND length(username) > 0",
            name=op.f("ck_user_accounts_username"),
        ),
        sa.CheckConstraint(
            "(role = 'owner' AND customer_id IS NOT NULL) "
            "OR (role = 'admin' AND customer_id IS NULL)",
            name=op.f("ck_user_accounts_role_customer"),
        ),
        sa.CheckConstraint("failed_attempts >= 0", name=op.f("ck_user_accounts_failed_attempts")),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_user_accounts_customer_id_customers"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_accounts")),
    )
    op.create_index("ix_user_accounts_username", "user_accounts", ["username"], unique=True)
    op.create_index("ix_user_accounts_customer_id", "user_accounts", ["customer_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_user_accounts_customer_id", table_name="user_accounts")
    op.drop_index("ix_user_accounts_username", table_name="user_accounts")
    op.drop_table("user_accounts")
