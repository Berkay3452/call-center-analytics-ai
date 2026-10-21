"""Çağrı müşteri ve tekne eşleştirme yöntemi sütunu (#119).

- `calls.match_method`: telefon | ad_tekne | elle | yok.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

METHODS = ("telefon", "ad_tekne", "elle", "yok")


def upgrade() -> None:
    quoted = ", ".join(f"'{m}'" for m in METHODS)
    op.add_column("calls", sa.Column("match_method", sa.Text(), nullable=True))
    op.create_check_constraint(
        "match_method",
        "calls",
        f"match_method IS NULL OR match_method IN ({quoted})",
    )


def downgrade() -> None:
    op.drop_constraint("match_method", "calls", type_="check")
    op.drop_column("calls", "match_method")
