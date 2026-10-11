"""Enum değerlerinin kod, veritabanı dokümanı ve frontend tipleri arasında aynı kalmasını denetler.

Bir değer yalnızca bir yerde değiştirilirse (ör. enums.py'ye kategori eklenip frontend'e
eklenmezse) bu test kırılır. Ayrıntı: docs/enums.md "Bir değeri değiştirirken".
"""

import re
from enum import StrEnum
from pathlib import Path

import pytest

from app.domain import enums

ROOT = Path(__file__).parents[2]
TYPES_TS = ROOT / "frontend" / "lib" / "types.ts"
DB_SCHEMA = ROOT / "docs" / "db_schema.md"
ENUMS_DOC = ROOT / "docs" / "enums.md"

# Frontend'de aynı adla tanımlı birleşim tipleri.
SHARED_WITH_FRONTEND: list[type[StrEnum]] = [
    enums.CallType,
    enums.RequestCategory,
    enums.ServiceMode,
    enums.Urgency,
    enums.NextAction,
    enums.SalesOutcomeType,
    enums.LossReason,
]


def values(enum_cls: type[StrEnum]) -> set[str]:
    return {m.value for m in enum_cls}


def ts_union(name: str) -> set[str]:
    src = TYPES_TS.read_text(encoding="utf-8")
    match = re.search(rf"export type {name} =([^;]+);", src)
    assert match, f"frontend/lib/types.ts içinde '{name}' tipi yok"
    return set(re.findall(r'"([a-z_]+)"', match.group(1)))


def db_check(column: str) -> list[set[str]]:
    """db_schema.md'deki `CHECK (<column> ... IN (...))` listeleri.

    Aynı sütun adı birden çok tabloda olabileceği için liste döner.
    """
    text = DB_SCHEMA.read_text(encoding="utf-8")
    found = re.findall(rf"CHECK \({column}(?: IS NULL OR {column})? IN \(([^)]*)\)\)", text)
    return [set(re.findall(r"'([a-z_]+)'", f)) for f in found]


@pytest.mark.parametrize("enum_cls", SHARED_WITH_FRONTEND, ids=lambda e: e.__name__)
def test_frontend_types_match_backend_enums(enum_cls: type[StrEnum]) -> None:
    assert ts_union(enum_cls.__name__) == values(enum_cls)


@pytest.mark.parametrize(
    ("column", "enum_cls"),
    [
        ("call_type", enums.CallType),
        ("request_category", enums.RequestCategory),
        ("category", enums.RequestCategory),  # service_orders.category
        ("service_mode", enums.ServiceMode),
        ("urgency", enums.Urgency),
        ("next_action", enums.NextAction),
        ("sales_outcome", enums.SalesOutcomeType),
        ("loss_reason", enums.LossReason),
        ("status", enums.ServiceOrderStatus),  # service_orders.status
    ],
)
def test_db_schema_checks_match_backend_enums(column: str, enum_cls: type[StrEnum]) -> None:
    checks = db_check(column)
    assert checks, f"db_schema.md'de {column} için CHECK yok"
    assert values(enum_cls) in checks, (column, checks)


def test_switchboard_outcome_documented_in_db_schema() -> None:
    text = DB_SCHEMA.read_text(encoding="utf-8")
    for value in values(enums.SwitchboardOutcome):
        assert f"`{value}`" in text, value


@pytest.mark.parametrize(
    "enum_cls",
    [*SHARED_WITH_FRONTEND, enums.ServiceOrderStatus, enums.SwitchboardOutcome],
    ids=lambda e: e.__name__,
)
def test_every_value_is_documented_in_enums_md(enum_cls: type[StrEnum]) -> None:
    text = ENUMS_DOC.read_text(encoding="utf-8")
    for value in values(enum_cls):
        assert f"| `{value}` |" in text, value
