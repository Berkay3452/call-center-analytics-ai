"""Docker ortamı için tek seferlik başlatıcı (init) servisi.

Sırayla:
1. Veritabanının hazır olduğunu doğrular.
2. Alembic migration'larını uygular (`alembic upgrade head`).
3. Veritabanı boşsa (calls tablosunda kayıt yoksa) sentetik veriyi seed'ler.
4. Seed çağrılarının sesini üretir (Piper, `SEED_AUDIO=generate`) ve çağrılara bağlar (#157).
5. Varsa ve embedding servisi erişilebilirse RAG parçalarını indeksler.

`SEED_AUDIO`: `generate` (varsayılan) ses dosyaları yoksa üretir; `skip` hiç dokunmaz (sessiz
çağrılarla çalışır). Üretim ilk açılışta birkaç dakika sürer; sesler `audio-storage` volume'unda
kalır, sonraki açılışlarda atlanır. Üretim başarısız olursa init durmaz (uyarı verir).
"""

from __future__ import annotations

import asyncio
import os
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


PIPER_TARGET = Path("/tmp/piper-site")


def count_seed_audio(audio_dir: Path) -> int:
    seed_dir = audio_dir / "seed"
    return len(list(seed_dir.glob("call_*.wav"))) if seed_dir.is_dir() else 0


def ensure_seed_audio(data_dir: Path, audio_dir: Path) -> int:
    """Seed çağrılarının sesi yoksa Piper ile üretir; kaç ses dosyası olduğunu döner (#157).

    Piper projenin bağımlılığı değildir (bkz. `scripts/generate_audio.py`): imajdaki sistem
    Python'unun pip'iyle geçici klasöre kurulur. Hata verirse init durmaz.
    """
    expected = len(list((data_dir / "calls").glob("call_*.json")))
    have = count_seed_audio(audio_dir)
    mode = os.environ.get("SEED_AUDIO", "generate").lower()
    if mode == "skip" or have >= expected or expected == 0:
        return have
    print(f"▶ [init] Seed sesleri üretiliyor ({have}/{expected} var, Piper)...", flush=True)
    base_python = Path(sys.base_prefix) / "bin" / "python"
    try:
        subprocess.run(
            [str(base_python), "-m", "pip", "install", "-q", "--target", str(PIPER_TARGET),
             "piper-tts"],
            check=True,
            timeout=600,
        )  # fmt: skip
        env = {**os.environ, "PYTHONPATH": f"{os.environ.get('PYTHONPATH', '')}:{PIPER_TARGET}"}
        voice_dir = Path(os.environ.get("TTS_VOICE_DIR", "/app/storage/models/tts"))
        subprocess.run(
            [sys.executable, "-m", "scripts.generate_audio", "--audio-dir", str(audio_dir),
             "--voice-dir", str(voice_dir)],
            check=True,
            env=env,
            timeout=1800,
        )  # fmt: skip
    except Exception as exc:
        print(f"⚠ [init] Seed sesleri üretilemedi, sessiz devam ediliyor ({exc}).", flush=True)
    have = count_seed_audio(audio_dir)
    print(f"ℹ [init] Seed ses dosyası sayısı: {have}/{expected}.", flush=True)
    return have


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

    audio_path = storage_dir(settings)
    # Sesler seed'den ÖNCE hazırlanır ki seed çağrılara bağlayabilsin.
    audio_files = await asyncio.to_thread(ensure_seed_audio, data_dir, audio_path)

    if not call_count:
        print("▶ [init] Veritabanı boş, seed verisi yükleniyor...", flush=True)
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
        # Ses sonradan üretildiyse seed çağrılarına bağla (seed idempotent: ON CONFLICT günceller).
        conn = await asyncpg.connect(dsn, statement_cache_size=0)
        try:
            linked = await conn.fetchval("SELECT count(*) FROM calls WHERE audio_path IS NOT NULL;")
        finally:
            await conn.close()
        if audio_files and (linked or 0) < audio_files:
            print("▶ [init] Seed sesleri çağrılara bağlanıyor...", flush=True)
            await seed_database(
                settings.database_url, data_dir=data_dir, seed=SEED, reset=False,
                audio_dir=audio_path,
            )  # fmt: skip

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
