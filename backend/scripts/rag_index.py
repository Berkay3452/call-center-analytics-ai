"""Tekne karnesi parçalarının vektörlerini üretir (#26).

Kullanım (backend/ klasöründe; önce migration + seed, embedding servisi açık olmalı):

    docker compose -f ../infra/docker-compose.yml --profile rag up -d   # bge-m3 (TEI, CPU)
    python -m scripts.rag_index                      # vektörü olmayan parçalar
    python -m scripts.rag_index --reindex            # hepsi (model değişince)
    python -m scripts.rag_index --provider hash      # servis olmadan (yalnızca geliştirme)
"""

import argparse
import asyncio
import time

from app.core.config import Settings
from app.db.session import create_engine, create_session_factory
from app.rag.embedders import build_embedder
from app.rag.indexer import index_chunks


async def run(args: argparse.Namespace) -> None:
    settings = Settings()
    embedder = build_embedder(settings, args.provider)
    engine = create_engine(settings, null_pool=True)
    started = time.perf_counter()
    try:
        async with create_session_factory(engine)() as session, session.begin():
            count = await index_chunks(
                session, embedder, reindex=args.reindex, batch_size=settings.embedding_batch_size
            )
    finally:
        await engine.dispose()
    elapsed = time.perf_counter() - started
    print(f"{count} parça vektörlendi ({embedder.model_name}, {elapsed:.1f} sn).")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--reindex", action="store_true", help="Vektörü olanları da yeniden üret")
    parser.add_argument("--provider", choices=["tei", "openai_compatible", "hash"])
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
