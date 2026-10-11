"""Veritabanı şeması testleri (veritabanı gerektirmez).

- Modeller docs/db_schema.md ile tablo tablo, sütun sütun aynı mı?
- İlk migration'ın SQL'i modellerdeki tüm tabloları ve güncel enum CHECK'lerini içeriyor mu?
  Alembic `check` CHECK kısıtlarını karşılaştırmaz; enum değişip migration yazılmazsa
  bu test yakalar.
"""

import io
import re
from argparse import Namespace
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import CheckConstraint

from app.db.models import Base

BACKEND = Path(__file__).parents[1]
DB_SCHEMA = BACKEND.parent / "docs" / "db_schema.md"


def documented_tables() -> dict[str, set[str]]:
    """db_schema.md'deki '### x.y `tablo`' bölümleri ve tablolarındaki '| `sütun` |' satırları."""
    text = DB_SCHEMA.read_text(encoding="utf-8")
    sections = re.split(r"^### \d+\.\d+ (?:🔶 )?`([a-z_]+)`\s*$", text, flags=re.M)
    tables: dict[str, set[str]] = {}
    for name, body in zip(sections[1::2], sections[2::2], strict=True):
        body = body.split("\n---")[0]
        tables[name] = set(re.findall(r"^\| `([a-z_0-9]+)` \|", body, flags=re.M))
    return tables


def offline_sql() -> str:
    buffer = io.StringIO()
    cfg = Config(str(BACKEND / "alembic.ini"), output_buffer=buffer)
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    cfg.cmd_opts = Namespace(x=["url=postgresql+asyncpg://kullanici:sifre@localhost/sema"])
    command.upgrade(cfg, "head", sql=True)
    return buffer.getvalue()


def test_models_cover_exactly_the_documented_tables() -> None:
    assert set(Base.metadata.tables) == set(documented_tables())


@pytest.mark.parametrize("table", sorted(Base.metadata.tables))
def test_model_columns_match_documentation(table: str) -> None:
    model_columns = {c.name for c in Base.metadata.tables[table].columns}

    assert model_columns == documented_tables()[table]


@pytest.fixture(scope="module")
def ddl() -> str:
    return offline_sql()


def test_migration_creates_every_table_and_extension(ddl: str) -> None:
    for table in Base.metadata.tables:
        assert f"CREATE TABLE {table} (" in ddl, table
    assert "CREATE EXTENSION IF NOT EXISTS vector" in ddl
    assert "USING hnsw (embedding vector_cosine_ops)" in ddl
    assert "GENERATED ALWAYS AS (to_tsvector('turkish', content)) STORED" in ddl


def test_migration_checks_match_current_enums(ddl: str) -> None:
    """Modellerdeki her CHECK (enum'dan üretilir) migration SQL'inde birebir olmalı."""
    missing = [
        f"{table.name}.{c.name}: {c.sqltext}"
        for table in Base.metadata.tables.values()
        for c in table.constraints
        if isinstance(c, CheckConstraint) and str(c.sqltext) not in ddl
    ]
    assert not missing, "Enum/CHECK değişmiş ama migration yazılmamış:\n" + "\n".join(missing)
