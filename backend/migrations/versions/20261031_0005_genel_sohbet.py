"""Soru tipine `genel_sohbet` eklenir (#177).

- `chat_messages.question_type` CHECK kısıtı: gecmis_oneri | sayisal | genel_sohbet | kapsam_disi.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-31
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD = ("gecmis_oneri", "sayisal", "kapsam_disi")
NEW = ("gecmis_oneri", "sayisal", "genel_sohbet", "kapsam_disi")


def _replace(values: tuple[str, ...]) -> None:
    quoted = ", ".join(f"'{v}'" for v in values)
    op.drop_constraint("question_type", "chat_messages", type_="check")
    op.create_check_constraint(
        "question_type",
        "chat_messages",
        f"question_type IS NULL OR question_type IN ({quoted})",
    )


def upgrade() -> None:
    _replace(NEW)


def downgrade() -> None:
    op.execute(
        "UPDATE chat_messages SET question_type = 'kapsam_disi' "
        "WHERE question_type = 'genel_sohbet'"
    )
    _replace(OLD)
