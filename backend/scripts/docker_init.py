"""Docker ortamı için tek seferlik başlatıcı (init) servisi.

Sırayla:
1. Veritabanının hazır olduğunu doğrular.
2. Alembic migration'larını uygular (`alembic upgrade head`).
3. Veritabanı boşsa (calls tablosunda kayıt yoksa) sentetik veriyi seed'ler.
4. Varsa ve embedding servisi erişilebilirse RAG parçalarını indeksler.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
import time
from pathlib import Path

import asyncpg
from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.models.ai import RagChunk
from app.db.session import create_engine, create_session_factory
from app.rag.embedders import build_embedder
from app.rag.indexer import index_chunks
from app.services.audio_ingest import storage_dir
from scripts.seed.generator import DATA_DIR, SEED, write_synthetic_files
from scripts.seed.loader import _asyncpg_dsn, seed_database


def run_migrations() -> None:
    """Alembic migration'larını çalıştırır."""
    print("▶ [init] Alembic migration'ları uygulanıyor...", flush=True)
    backend_dir = Path(__file__).resolve().parents[1]
    res = subprocess.run(
        ["alembic", "upgrade", "head"],
        cwd=backend_dir,
        check=False,
    )
    if res.returncode != 0:
        print(
            f"✖ [init] Alembic migration başarısız oldu (çıkış kodu: {res.returncode})",
            file=sys.stderr,
            flush=True,
        )
        sys.exit(res.returncode)
    print("✔ [init] Migration'lar başarıyla tamamlandı.", flush=True)


def resolve_synthetic_data_dir() -> Path:
    """Sentetik verilerin okunacağı klasörü belirler."""
    candidate_dirs = [
        DATA_DIR,
        Path("/data/synthetic"),
        Path(__file__).resolve().parents[1].parent / "data" / "synthetic",
    ]
    data_dir = next((d for d in candidate_dirs if (d / "calls_meta.json").exists()), DATA_DIR)
    if not (data_dir / "customers.json").exists():
        try:
            data_dir.mkdir(parents=True, exist_ok=True)
            write_synthetic_files(out_dir=data_dir, seed=SEED)
        except OSError:
            pass
    return data_dir


async def wait_for_db(dsn: str, max_wait_seconds: float = 60.0) -> None:
    """Veritabanı bağlantısı kurulana kadar bekler."""
    deadline = time.monotonic() + max_wait_seconds
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        try:
            conn = await asyncpg.connect(dsn, statement_cache_size=0, timeout=3.0)
            await conn.close()
            return
        except Exception as exc:
            last_err = exc
            await asyncio.sleep(2.0)
    print(
        f"✖ [init] Veritabanı zaman aşımına uğradı ({max_wait_seconds}s): {last_err}",
        file=sys.stderr,
        flush=True,
    )
    sys.exit(1)


async def ensure_seed_and_rag(data_dir: Path) -> None:
    """Veritabanı boşsa seed verisini yükler ve RAG parçalarını indeksler."""
    settings = get_settings()
    dsn = _asyncpg_dsn(settings.database_url)

    await wait_for_db(dsn)

    conn = await asyncpg.connect(dsn, statement_cache_size=0)
    try:
        call_count = await conn.fetchval("SELECT count(*) FROM calls;")
    finally:
        await conn.close()

    if not call_count:
        print("▶ [init] Veritabanı boş, seed verisi yükleniyor...", flush=True)
        audio_path = storage_dir(settings)
        counts = await seed_database(
            settings.database_url,
            data_dir=data_dir,
            seed=SEED,
            reset=False,
            audio_dir=audio_path,
        )
        calls_count = counts.get("calls", 0)
        cust_count = counts.get("customers", 0)
        print(
            f"✔ [init] Seed tamamlandı ({calls_count} çağrı, {cust_count} müşteri).",
            flush=True,
        )
    else:
        print(f"ℹ [init] Veritabanında zaten {call_count} çağrı mevcut; seed atlandı.", flush=True)

    # RAG indeksi: embedding servisi ayaktaysa veya hash modundaysa
    try:
        engine = create_engine(settings, null_pool=True)
        embedder = build_embedder(settings)
        async with create_session_factory(engine)() as session, session.begin():
            unindexed = await session.scalar(
                select(func.count(RagChunk.id)).where(RagChunk.embedding.is_(None))
            )
            if unindexed and unindexed > 0:
                print(
                    f"▶ [init] {unindexed} RAG parçası indeksleniyor ({embedder.model_name})...",
                    flush=True,
                )
                indexed_count = await index_chunks(
                    session,
                    embedder,
                    reindex=False,
                    batch_size=settings.embedding_batch_size,
                )
                print(f"✔ [init] {indexed_count} parça indekslendi.", flush=True)
            else:
                print("ℹ [init] Tüm RAG parçaları zaten indeksli.", flush=True)
        await engine.dispose()
    except Exception as exc:
        print(f"⚠ [init] RAG indeksleme adımı atlandı ({exc}).", flush=True)


def main() -> None:
    print("========================================", flush=True)
    print("  Call Center AI — Docker Init Başlatıldı", flush=True)
    print("========================================", flush=True)
    run_migrations()
    data_dir = resolve_synthetic_data_dir()
    asyncio.run(ensure_seed_and_rag(data_dir))
    print("========================================", flush=True)
    print("✔ [init] Tüm hazırlık adımları tamamlandı.", flush=True)
    print("========================================", flush=True)


if __name__ == "__main__":
    main()
