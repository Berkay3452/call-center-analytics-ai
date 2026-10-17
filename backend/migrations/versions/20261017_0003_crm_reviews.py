"""CRM önerisi inceleme tablosu ve servis emri kaynak çağrı bağı (#106).

- `crm_reviews`: analiz çıktısının admin tarafından onay/red/düzenleme kaydı.
- `service_orders.source_call_id`: onaylanan öneriden doğan servis emrinin kaynak çağrısı.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATUSES = ("bekliyor", "onaylandi", "reddedildi")


def upgrade() -> None:
    # 1. service_orders tablosuna kaynak çağrı bağlantısı
    op.add_column("service_orders", sa.Column("source_call_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f("fk_service_orders_source_call_id_calls"),
        "service_orders",
        "calls",
        ["source_call_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_orders_source_call_id"),
        "service_orders",
        ["source_call_id"],
        unique=False,
    )

    # 2. crm_reviews tablosu
    quoted_statuses = ", ".join(f"'{s}'" for s in STATUSES)
    op.create_table(
        "crm_reviews",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("analysis_id", sa.UUID(), nullable=False),
        sa.Column("call_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'bekliyor'"), nullable=False),
        sa.Column(
            "edited_fields",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("service_order_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_crm_reviews")),
        sa.UniqueConstraint("analysis_id", name=op.f("uq_crm_reviews_analysis_id")),
        sa.CheckConstraint(f"status IN ({quoted_statuses})", name=op.f("ck_crm_reviews_status")),
        sa.ForeignKeyConstraint(
            ["analysis_id"],
            ["analysis_results.id"],
            name=op.f("fk_crm_reviews_analysis_id_analysis_results"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["call_id"],
            ["calls.id"],
            name=op.f("fk_crm_reviews_call_id_calls"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["service_order_id"],
            ["service_orders.id"],
            name=op.f("fk_crm_reviews_service_order_id_service_orders"),
            ondelete="SET NULL",
        ),
    )
    op.create_index(op.f("ix_crm_reviews_call_id"), "crm_reviews", ["call_id"], unique=False)
    op.create_index(
        op.f("ix_crm_reviews_service_order_id"), "crm_reviews", ["service_order_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_crm_reviews_service_order_id"), table_name="crm_reviews", if_exists=True)
    op.drop_index(op.f("ix_crm_reviews_call_id"), table_name="crm_reviews", if_exists=True)
    op.drop_table("crm_reviews")
    op.execute("DROP INDEX IF EXISTS ix_orders_source_call_id")
    op.execute("DROP INDEX IF EXISTS ix_service_orders_source_call_id")
    op.drop_constraint(
        op.f("fk_service_orders_source_call_id_calls"), "service_orders", type_="foreignkey"
    )
    op.drop_column("service_orders", "source_call_id")
