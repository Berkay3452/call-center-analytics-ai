"""Duygu Analiz Agent'ı (#333): analiz sütunları ve agent adı listesi.

- `analysis_results`: sentiment (olumlu | notr | olumsuz), sentiment_complaint, sentiment_reason,
  sentiment_evidence, sentiment_confidence. Eski analizlerde NULL kalır (agent o zaman yoktu).
- `agent_runs.agent_name` kısıtına `sentiment_analyzer` eklenir.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_AGENTS = ("call_classifier", "crm_extraction", "sales_analyzer", "summarizer")
NEW_AGENTS = (*OLD_AGENTS, "sentiment_analyzer")
SENTIMENTS = ("olumlu", "notr", "olumsuz")


def _in(column: str, values: Sequence[str]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _swap_agent_check(agents: Sequence[str]) -> None:
    op.drop_constraint(op.f("ck_agent_runs_agent_name"), "agent_runs", type_="check")
    op.create_check_constraint(
        op.f("ck_agent_runs_agent_name"), "agent_runs", _in("agent_name", agents)
    )


def upgrade() -> None:
    op.add_column("analysis_results", sa.Column("sentiment", sa.Text(), nullable=True))
    op.add_column("analysis_results", sa.Column("sentiment_complaint", sa.Boolean(), nullable=True))
    op.add_column("analysis_results", sa.Column("sentiment_reason", sa.Text(), nullable=True))
    op.add_column("analysis_results", sa.Column("sentiment_evidence", sa.Text(), nullable=True))
    op.add_column("analysis_results", sa.Column("sentiment_confidence", sa.REAL(), nullable=True))
    op.create_check_constraint(
        op.f("ck_analysis_results_sentiment"),
        "analysis_results",
        f"sentiment IS NULL OR {_in('sentiment', SENTIMENTS)}",
    )
    op.create_check_constraint(
        op.f("ck_analysis_results_sentiment_confidence_range"),
        "analysis_results",
        "sentiment_confidence IS NULL OR (sentiment_confidence >= 0 AND sentiment_confidence <= 1)",
    )
    op.create_check_constraint(
        op.f("ck_analysis_results_sentiment_complaint_negative"),
        "analysis_results",
        "NOT COALESCE(sentiment_complaint, false) OR sentiment = 'olumsuz'",
    )
    op.create_index("ix_analysis_sentiment", "analysis_results", ["sentiment"], unique=False)
    _swap_agent_check(NEW_AGENTS)


def downgrade() -> None:
    # Duygu agent'ının kayıtları silinmeden eski kısıt konamaz.
    op.execute("DELETE FROM agent_runs WHERE agent_name = 'sentiment_analyzer'")
    _swap_agent_check(OLD_AGENTS)
    op.drop_index("ix_analysis_sentiment", table_name="analysis_results")
    for name in (
        "ck_analysis_results_sentiment_complaint_negative",
        "ck_analysis_results_sentiment_confidence_range",
        "ck_analysis_results_sentiment",
    ):
        op.drop_constraint(op.f(name), "analysis_results", type_="check")
    for column in (
        "sentiment_confidence",
        "sentiment_evidence",
        "sentiment_reason",
        "sentiment_complaint",
        "sentiment",
    ):
        op.drop_column("analysis_results", column)
