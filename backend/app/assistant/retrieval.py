"""Tekne karnesi araması: servis kayıtları ve usta notlarında hibrit arama (#26, #50).

Vektör (bge-m3) ve Türkçe tam metin sonuçları RRF ile birleştirilir (`app.rag.search`). Kurallar
araçlarla aynıdır: `owner_id` zorunludur ve yalnızca o sahibin kayıtları aranır.
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant.tools import require_owner  # yetki kontrolü tek yerde yapılır
from app.core.config import Settings
from app.db.session import worker_session
from app.rag.base import Embedder
from app.rag.embedders import build_embedder
from app.rag.search import hybrid_search
from app.schemas.assistant import SourceRef

# Yalnızca vektörle gelen (tam metinde geçmeyen) parçalar için alt benzerlik sınırı: ilgisiz
# notların kaynak gösterilmesini önler. Seed verisinde bge-m3 ile ölçüldü (14 Ekim 2026):
# ilgisiz sorularda yalnızca-vektör eşleşmeleri en fazla 0,48; ilgili sorularda 0,5 üstü
# ya da tam metinle de eşleşiyor (tam metin eşleşmesi eşikten etkilenmez).
MIN_SIMILARITY = 0.5


@dataclass(frozen=True)
class Passage:
    """Aramadan dönen parça: cevabın dayanabileceği kayıt metni ve kaynak kartı."""

    source: SourceRef
    text: str


async def _search(
    session: AsyncSession, embedder: Embedder, owner_uuid: UUID, query: str, limit: int
) -> list[Passage]:
    hits = await hybrid_search(
        session, embedder, owner_uuid, query, limit=limit, min_similarity=MIN_SIMILARITY
    )
    return [Passage(source=h.source, text=h.text) for h in hits]


async def search_boat_notes(
    owner_id: str,
    query: str,
    *,
    limit: int = 3,
    session: AsyncSession | None = None,
    embedder: Embedder | None = None,
) -> list[Passage]:
    """Sorguyla en ilgili kayıtlar (en iyiden başlayarak); eşleşme veya geçerli sahip yoksa boş."""
    clean_owner = require_owner(owner_id)
    try:
        owner_uuid = UUID(clean_owner)
    except ValueError:
        return []  # tanınmayan sahip: kimsenin kaydı dönmez

    settings = Settings()
    embedder = embedder or build_embedder(settings)
    if session is not None:
        return await _search(session, embedder, owner_uuid, query, limit)
    async with worker_session(settings) as sess:
        return await _search(sess, embedder, owner_uuid, query, limit)
