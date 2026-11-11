"""Belge ve kod tutarlılığı: bozuk bağlantı, eksik görsel, belgelenmemiş uç nokta ve tablo.

README, mimari belge ve `docs/` klasörü koddan ayrışırsa PR'da kırmızı olur.
"""

import re
from pathlib import Path

import pytest

from app.main import app

ROOT = Path(__file__).resolve().parents[2]
MARKDOWN = [
    ROOT / "README.md",
    ROOT / "README.en.md",
    ROOT / "Sistem_mimarisi_v5.md",
    ROOT / "backend" / "README.md",
    ROOT / "frontend" / "README.md",
    *sorted((ROOT / "docs").glob("*.md")),
]
LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)\)")


@pytest.mark.parametrize("path", MARKDOWN, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_relative_links_and_images_exist(path: Path) -> None:
    broken = []
    for target in LINK.findall(path.read_text(encoding="utf-8")):
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        file_part = target.split("#", 1)[0]
        if file_part and not (path.parent / file_part).exists():
            broken.append(target)
    assert not broken, f"{path.name}: bulunamayan bağlantı veya görsel: {broken}"


def test_diagrams_referenced_by_architecture_exist() -> None:
    text = (ROOT / "Sistem_mimarisi_v5.md").read_text(encoding="utf-8")
    images = re.findall(r"!\[[^\]]*\]\((docs/diagrams/[^)]+)\)", text)
    assert images, "mimari belgede diyagram yok"
    for image in images:
        assert (ROOT / image).is_file(), image


def test_every_api_route_is_documented() -> None:
    """Koddaki her uç nokta `docs/api.md` içinde geçmeli (yol, sürüm öneki olmadan)."""
    doc = (ROOT / "docs" / "api.md").read_text(encoding="utf-8")
    prefix = "/api/v1"
    api_paths = [p for p in app.openapi()["paths"] if p.startswith(prefix)]
    assert len(api_paths) > 20, "OpenAPI'de beklenen uç noktalar yok"
    documented = {
        re.sub(r"\{[^}]+\}", "{}", m)
        for m in re.findall(r"`(?:GET|POST|PUT|PATCH|DELETE) (/[^`\s?]*)", doc)
    }
    missing = [
        p.removeprefix(prefix)
        for p in api_paths
        if re.sub(r"\{[^}]+\}", "{}", p.removeprefix(prefix)) not in documented
    ]
    assert not missing, f"docs/api.md içinde olmayan uç noktalar: {sorted(missing)}"


def test_every_table_is_in_db_schema_doc() -> None:
    import app.db.models  # noqa: F401
    from app.db.base import Base

    doc = (ROOT / "docs" / "db_schema.md").read_text(encoding="utf-8")
    missing = [name for name in Base.metadata.tables if name not in doc]
    assert not missing, f"docs/db_schema.md içinde olmayan tablolar: {missing}"


def test_main_dependencies_are_listed_in_architecture() -> None:
    """Projenin ana çerçeveleri mimari belgenin teknoloji tablosunda yazılı olmalı."""
    text = (ROOT / "Sistem_mimarisi_v5.md").read_text(encoding="utf-8")
    for name in (
        "FastAPI",
        "Celery",
        "Redis",
        "PostgreSQL",
        "pgvector",
        "LangGraph",
        "faster-whisper",
        "bge-m3",
        "Next.js",
        "React",
        "Tailwind",
        "Playwright",
        "Alembic",
        "Docker",
    ):
        assert name in text, f"Sistem_mimarisi_v5.md teknoloji tablosunda {name} yok"
