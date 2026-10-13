"""Tekne karnesinde hibrit arama (#26): vektör (bge-m3, pgvector) + Türkçe tam metin, RRF ile.

Neden hibrit: vektör araması anlamı yakalar ("kışlama" ↔ "antifriz ile kışlandı"), tam metin
araması parça numarası, marka ve kesin terimleri yakalar. PostgreSQL'in `turkish` kök bulucusu
iyelik ekli kelimeleri eşleştiremediği için ("filtre" ≠ "filtresi") sorgu kelimeleri ön ek
olarak aranır (`filtr:*`).

Sıralama: Reciprocal Rank Fusion, puan = Σ 1 / (k + sıra). İki listede de üst sıradaki parça
öne çıkar; puanlar farklı ölçeklerde olduğu için toplanmaz, yalnızca sıralar kullanılır.

Yetki: her sorgu `owner_id` ile filtrelenir; başka bir sahibin parçası hiçbir koşulda dönmez.
"""

import re
from dataclasses import dataclass
from datetime import date
from typing import Literal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.rag.base import Embedder
from app.schemas.assistant import SourceRef

SearchMode = Literal["hybrid", "vector", "text"]
RRF_K = 60
CANDIDATES = 20  # her listeden alınan aday sayısı

# Aramada anlam taşımayan sık kelimeler.
STOPWORDS = frozenset(
    {"bir", "bu", "şu", "ve", "ile", "mi", "mı", "mu", "mü", "de", "da", "için", "ne", "neden"}
    | {"nasıl", "zaman", "hangi", "var", "yok", "son", "yapıldı", "yapmalıyım", "oldu", "olur"}
    | {"gerekir", "benim", "bana", "senin", "teknemin", "teknem", "tekne", "teknenin", "en"}
    | {"mıydı", "miydi", "muydu", "müydü", "durumda", "değişti", "ettim", "ediyor"}
)
_WORD = re.compile(r"\w+", re.UNICODE)
# Kesme işaretinden sonraki ek atılır: "Poyraz'ın" → "Poyraz", "akü'leri" → "akü".
_APOSTROPHE_SUFFIX = re.compile(r"['’]\w+")
# Çoğul eki ve ardından gelenler: "aküleri" → "akü", "filtreleri" → "filtre".
_PLURAL = re.compile(r"(?<=\w{3})(ler|lar)\w*$")
_PREFIX = 5


@dataclass(frozen=True)
class SearchHit:
    """Arama sonucu: kaynak kartı, parça metni ve sıralamanın açıklaması (hata ayıklama için)."""

    chunk_id: UUID
    source: SourceRef
    text: str
    score: float
    similarity: float | None  # vektör listesinde değilse None
    text_match: bool


def turkish_lower(value: str) -> str:
    return value.replace("I", "ı").replace("İ", "i").lower()


def build_tsquery(query: str) -> str | None:
    """Sorguyu ön ekli VEYA sorgusuna çevirir: "yakıt filtresi" → "yakıt:* | filtr:*".

    Yalnızca harf/rakamdan oluşan kelimeler alınır (tsquery söz dizimi hatası olmasın).
    Anlamlı kelime yoksa None.
    """
    terms: list[str] = []
    for word in _WORD.findall(_APOSTROPHE_SUFFIX.sub("", turkish_lower(query))):
        if len(word) < 3 or word in STOPWORDS or word.isdigit():
            continue
        term = f"{_PLURAL.sub('', word)[:_PREFIX]}:*"
        if term not in terms:
            terms.append(term)
    return " | ".join(terms) if terms else None


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{v:.6f}" for v in vector) + "]"


_SQL = """
WITH vec AS (
    SELECT id,
           row_number() OVER (ORDER BY embedding <=> CAST(:qvec AS vector)) AS rnk,
           1 - (embedding <=> CAST(:qvec AS vector)) AS sim
    FROM rag_chunks
    WHERE owner_id = :owner AND :use_vec AND embedding IS NOT NULL
    ORDER BY embedding <=> CAST(:qvec AS vector)
    LIMIT :cand
),
fts AS (
    SELECT id, row_number() OVER (ORDER BY ts_rank_cd(tsv, q) DESC, id) AS rnk
    FROM rag_chunks, to_tsquery('simple', :tsq) AS q
    WHERE owner_id = :owner AND :use_fts AND tsv @@ q
    ORDER BY ts_rank_cd(tsv, q) DESC, id
    LIMIT :cand
)
SELECT c.id, c.source_kind, c.source_id, c.content,
       COALESCE(1.0 / (:rrf + vec.rnk), 0) + COALESCE(1.0 / (:rrf + fts.rnk), 0) AS score,
       vec.sim AS sim,
       fts.id IS NOT NULL AS text_match,
       b.name AS boat_name,
       bn.note_date AS note_date,
       CAST(COALESCE(so.completed_at, so.created_at) AS date) AS service_date,
       so.category AS service_category
FROM rag_chunks c
LEFT JOIN vec ON vec.id = c.id
LEFT JOIN fts ON fts.id = c.id
LEFT JOIN boats b ON b.id = c.boat_id
LEFT JOIN boat_notes bn ON c.source_kind = 'boat_note' AND bn.id = c.source_id
LEFT JOIN service_orders so ON c.source_kind = 'service_record' AND so.id = c.source_id
WHERE c.owner_id = :owner AND (vec.id IS NOT NULL OR fts.id IS NOT NULL)
ORDER BY score DESC, c.id
LIMIT :limit
"""


def _source(row: object) -> SourceRef:
    kind = row.source_kind  # type: ignore[attr-defined]
    boat = row.boat_name  # type: ignore[attr-defined]
    on: date | None = row.note_date if kind == "boat_note" else row.service_date  # type: ignore[attr-defined]
    label = "usta notu" if kind == "boat_note" else "servis kaydı"
    parts = [on.strftime("%d.%m.%Y") if on else None, label, f"({boat})" if boat else None]
    title = " ".join(p for p in parts if p)
    content: str = row.content  # type: ignore[attr-defined]
    return SourceRef(
        kind=kind,
        record_id=str(row.source_id),  # type: ignore[attr-defined]
        title=title,
        date=on,
        excerpt=content if len(content) <= 300 else content[:297] + "...",
    )


async def hybrid_search(
    session: AsyncSession,
    embedder: Embedder,
    owner_id: UUID,
    query: str,
    *,
    limit: int = 3,
    min_similarity: float = 0.0,
    mode: SearchMode = "hybrid",
) -> list[SearchHit]:
    """Sahibin tekne karnesinde en ilgili parçalar (en iyiden başlayarak); yoksa boş liste.

    `min_similarity`: yalnızca vektör listesinden gelen (tam metinde eşleşmeyen) parçalar için
    alt sınır; ilgisiz notların kaynak gösterilmesini önler. Tam metin eşleşmesi her zaman kalır.
    `mode`: karşılaştırma için yalnızca `vector` veya yalnızca `text` listesi kullanılabilir.
    """
    if not query.strip():
        return []
    tsq = build_tsquery(query) if mode != "vector" else None
    use_vec = mode != "text"
    qvec = await embedder.embed_query(query) if use_vec else [0.0] * embedder.dim
    rows = (
        await session.execute(
            text(_SQL),
            {
                "qvec": _vector_literal(qvec),
                "owner": owner_id,
                "tsq": tsq or "x",  # kullanılmaz: use_fts=false
                "use_fts": tsq is not None,
                "use_vec": use_vec,
                "cand": CANDIDATES,
                "rrf": RRF_K,
                "limit": limit * 3,  # eşik sonrası yeterli sonuç kalsın
            },
        )
    ).all()

    hits: list[SearchHit] = []
    for row in rows:
        sim = float(row.sim) if row.sim is not None else None
        if not row.text_match and (sim is None or sim < min_similarity):
            continue
        hits.append(
            SearchHit(
                chunk_id=row.id,
                source=_source(row),
                text=row.content,
                score=float(row.score),
                similarity=sim,
                text_match=bool(row.text_match),
            )
        )
        if len(hits) == limit:
            break
    return hits
