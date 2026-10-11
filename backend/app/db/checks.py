"""CHECK kısıtlarını enum listelerinden üretir; değerler elle tekrar yazılmaz (kaynak enums.py)."""

from collections.abc import Iterable
from enum import StrEnum

from sqlalchemy import CheckConstraint


def in_values(
    column: str, values: Iterable[str], *, nullable: bool = True, name: str
) -> CheckConstraint:
    """`column IN (...)` kısıtı; `nullable` ise NULL'a da izin verir."""
    quoted = ", ".join(f"'{v}'" for v in values)
    expr = f"{column} IN ({quoted})"
    if nullable:
        expr = f"{column} IS NULL OR {expr}"
    return CheckConstraint(expr, name=name)


def in_enum(
    column: str, enum_cls: type[StrEnum], *, nullable: bool = True, name: str | None = None
) -> CheckConstraint:
    return in_values(column, (m.value for m in enum_cls), nullable=nullable, name=name or column)
