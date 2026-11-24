"""Ayrı hesap tabloları (#368): `admin_accounts` ve `owner_accounts`.

`user_accounts` (#278) iki tabloya bölünür; veri taşınır, eski tablo kaldırılır. Geri alınınca
(downgrade) tek tabloya birleştirilir.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SHARED = (
    "id, username, password_hash, is_active, failed_attempts, locked_until, "
    "password_changed_at, created_at"
)


def _common() -> list[sa.Column]:  # type: ignore[type-arg]
    return [
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("username", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
    ]


def _state() -> list[sa.Column]:  # type: ignore[type-arg]
    return [
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
    ]


def upgrade() -> None:
    op.create_table(
        "admin_accounts",
        *_common(),
        sa.Column("display_name", sa.Text(), nullable=False),
        *_state(),
        sa.CheckConstraint(
            "username = lower(username) AND length(username) > 0",
            name=op.f("ck_admin_accounts_username"),
        ),
        sa.CheckConstraint("failed_attempts >= 0", name=op.f("ck_admin_accounts_failed_attempts")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_accounts")),
    )
    op.create_index("ix_admin_accounts_username", "admin_accounts", ["username"], unique=True)
    op.create_table(
        "owner_accounts",
        *_common(),
        sa.Column("customer_id", sa.UUID(), nullable=False),
        *_state(),
        sa.CheckConstraint(
            "username = lower(username) AND length(username) > 0",
            name=op.f("ck_owner_accounts_username"),
        ),
        sa.CheckConstraint("failed_attempts >= 0", name=op.f("ck_owner_accounts_failed_attempts")),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_owner_accounts_customer_id_customers"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_owner_accounts")),
    )
    op.create_index("ix_owner_accounts_username", "owner_accounts", ["username"], unique=True)
    op.create_index("ix_owner_accounts_customer_id", "owner_accounts", ["customer_id"], unique=True)

    op.execute(
        f"INSERT INTO admin_accounts ({SHARED}, display_name) "
        f"SELECT {SHARED}, username FROM user_accounts WHERE role = 'admin'"
    )
    op.execute(
        f"INSERT INTO owner_accounts ({SHARED}, customer_id) "
        f"SELECT {SHARED}, customer_id FROM user_accounts WHERE role = 'owner'"
    )
    op.drop_index("ix_user_accounts_customer_id", table_name="user_accounts")
    op.drop_index("ix_user_accounts_username", table_name="user_accounts")
    op.drop_table("user_accounts")


def downgrade() -> None:
    op.create_table(
        "user_accounts",
        *_common(),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("customer_id", sa.UUID(), nullable=True),
        *_state(),
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
    op.execute(
        f"INSERT INTO user_accounts ({SHARED}, role) SELECT {SHARED}, 'admin' FROM admin_accounts"
    )
    op.execute(
        f"INSERT INTO user_accounts ({SHARED}, role, customer_id) "
        f"SELECT {SHARED}, 'owner', customer_id FROM owner_accounts"
    )
    op.drop_table("owner_accounts")
    op.drop_table("admin_accounts")
