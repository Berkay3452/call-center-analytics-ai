"""Eşleme tablolarının doğruluğu: `docs/guvenlik_testi.md` içindeki her OWASP maddesi için kod ve
test yolu gösterilmiş ve gösterilen her dosya gerçekten var olmalı (kabul ölçütü #276).
"""

import re
from pathlib import Path

import pytest

from scripts.guvenlik_testi import SINIFLAR

ROOT = Path(__file__).parents[3]
DOC = (ROOT / "docs" / "guvenlik_testi.md").read_text(encoding="utf-8")
LLM_IDS = [f"LLM{i:02d}" for i in range(1, 11)]
API_IDS = [f"API{i}" for i in range(1, 11)]
PATH_RE = re.compile(r"`((?:backend|docs|\.github)/[^`\s]+)`")


def _row(item: str) -> str:
    # Madde kimliğiyle başlayan tablo satırı ("| LLM01 Prompt injection | ... |").
    match = re.search(rf"^\| {item} [^\n]*$", DOC, flags=re.MULTILINE)
    assert match, f"{item} için eşleme satırı yok"
    return match.group(0)


@pytest.mark.parametrize("item", LLM_IDS + API_IDS)
def test_every_owasp_item_has_code_and_test_paths(item: str) -> None:
    cells = [c.strip() for c in _row(item).strip("|").split("|")]
    assert len(cells) == 3, item
    code_paths = PATH_RE.findall(cells[1])
    test_paths = PATH_RE.findall(cells[2])

    assert code_paths, f"{item}: savunma (kod) yolu yok"
    assert any("/tests/" in p for p in test_paths), f"{item}: kanıt (test) yolu yok"


def test_every_referenced_path_exists() -> None:
    paths = set(PATH_RE.findall(DOC))
    missing = sorted(p for p in paths if not (ROOT / p.rstrip("/")).exists())

    assert len(paths) > 40
    assert missing == []


def test_every_security_module_is_mapped_and_documented() -> None:
    modules = {p.stem for p in (ROOT / "backend" / "tests" / "security").glob("test_*.py")}

    assert modules == set(SINIFLAR)
    for module in modules - {"test_owasp_eslesmesi"}:
        assert f"{module}.py" in DOC, module


def test_known_limitations_in_doc_match_xfail_tests() -> None:
    assert "BS-1" in DOC and "BS-2" in DOC and "BS-3" in DOC
