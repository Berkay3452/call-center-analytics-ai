"""Çağrıya işlenme durumu ve hata sütunları (#48).

`calls.state`: beklemede → yaziya_cevriliyor → isleniyor → tamam | kismi | basarisiz.
Mevcut çağrılar için durum, en son analiz sürümünün durumundan türetilir; analizi olmayanlar
`beklemede` kalır.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATES = ("beklemede", "yaziya_cevriliyor", "isleniyor", "tamam", "kismi", "basarisiz")


def upgrade() -> None:
    op.add_column(
        "calls",
        sa.Column("state", sa.Text(), server_default=sa.text("'beklemede'"), nullable=False),
    )
    op.add_column("calls", sa.Column("error", sa.Text(), nullable=True))
    op.execute(
        """
        UPDATE calls SET state = latest.status
        FROM (
            SELECT DISTINCT ON (call_id) call_id, status
            FROM analysis_results ORDER BY call_id, version DESC
        ) AS latest
        WHERE latest.call_id = calls.id
        """
    )
    quoted = ", ".join(f"'{v}'" for v in STATES)
    op.create_check_constraint(op.f("ck_calls_state"), "calls", f"state IN ({quoted})")


def downgrade() -> None:
    op.drop_constraint(op.f("ck_calls_state"), "calls", type_="check")
    op.drop_column("calls", "error")
    op.drop_column("calls", "state")
