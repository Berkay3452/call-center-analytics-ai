"""Tekne karnesi parçalarının vektörlerini üretir (#26).

Parçalar (`rag_chunks`) seed ve ileride Miço Usta'dan gelen kayıtlarla yazılır; metin ve tam
metin indeksi (`tsv`) veritabanında hazırdır. Bu modül yalnızca `embedding` sütununu doldurur:
varsayılan olarak vektörü olmayanları, `reindex=True` ile hepsini (model değişince).

Çalıştırma: `python -m scripts.rag_index` (bkz. README).
"""

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.ai import RagChunk
from app.rag.base import Embedder

log = structlog.get_logger(__name__)


async def index_chunks(
    session: AsyncSession, embedder: Embedder, *, reindex: bool = False, batch_size: int = 32
) -> int:
    """Parçaları vektörler; işlenen parça sayısını döner. Commit çağıranındır."""
    stmt = select(RagChunk.id, RagChunk.content).order_by(RagChunk.id)
    if not reindex:
        stmt = stmt.where(RagChunk.embedding.is_(None))
    rows = (await session.execute(stmt)).all()

    done = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        vectors = await embedder.embed_documents([r.content for r in batch])
        await session.execute(
            update(RagChunk),
            [{"id": r.id, "embedding": v} for r, v in zip(batch, vectors, strict=True)],
        )
        done += len(batch)
        log.info("rag.indexed", done=done, total=len(rows), model=embedder.model_name)
    return done
