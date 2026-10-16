"""Seed script'inin gerçek PostgreSQL üzerindeki testi (#23).

Yalnızca `RUN_DB_TESTS=1` iken çalışır (CI'da migration'dan sonra). Seed veriyi KALICI yazar,
bu yüzden yalnızca CI'daki tek kullanımlık veritabanında veya yerelde `--reset` kabul edilerek
çalıştırılmalıdır.
"""

import hashlib
import json
import os
from array import array
from pathlib import Path

import asyncpg
import pytest

from app.core.config import Settings
from scripts.seed.audio import build_wav, write_seed_audio
from scripts.seed.generator import DATA_DIR, generate_dataset, load_calls_bundle
from scripts.seed.loader import _asyncpg_dsn, seed_database

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_DB_TESTS") != "1", reason="RUN_DB_TESTS=1 değil (gerçek veritabanı gerekir)"
)

EXPECTED_AT_LEAST = {
    "customers": 15,
    "boats": 20,
    "craftsmen": 5,
    "boat_notes": 60,
    "service_orders": 50,
    "expenses": 50,
    "subscriptions": 10,
    "calls": 30,
    "transcripts": 30,
    "analysis_results": 30,
}


async def test_seed_fills_empty_database_and_is_idempotent() -> None:
    url = Settings().database_url

    first = await seed_database(url, reset=True)  # boş veritabanından başla
    second = await seed_database(url)  # ikinci çalıştırma: sayılar değişmemeli
    third = await seed_database(url)

    assert first == second == third
    for table, minimum in EXPECTED_AT_LEAST.items():
        assert first[table] >= minimum, (table, first[table])
    assert first["transcript_segments"] >= 30 * 15
    assert first["rag_chunks"] >= first["boat_notes"]


async def test_seeded_data_is_consistent() -> None:
    conn = await asyncpg.connect(_asyncpg_dsn(Settings().database_url), statement_cache_size=0)
    try:
        # Hocanın örnek çağrısı: Tuzla Marina'daki Rüzgar teknesi ve sahibiyle eşleşmiş olmalı.
        row = await conn.fetchrow(
            "SELECT b.name, c.full_name, a.request_category, a.next_action"
            " FROM calls ca JOIN boats b ON b.id = ca.boat_id"
            " JOIN customers c ON c.id = ca.customer_id"
            " JOIN analysis_results a ON a.call_id = ca.id"
            " WHERE ca.marina = 'Tuzla Marina' AND ca.customer_name = 'Burak Çelik'"
            " AND b.name = 'Rüzgar'"
        )
        assert row is not None
        assert (row["name"], row["request_category"], row["next_action"]) == (
            "Rüzgar",
            "makine",
            "servis_randevusu_olustur",
        )

        # Kayıtlı müşteriler çağrılarına bağlanmış olmalı; yalnızca ilk kez arayan üç kişi
        # (yeni müşteri senaryoları) eşleşmemiş kalır.
        unmatched = {
            r["customer_name"]
            for r in await conn.fetch(
                "SELECT customer_name FROM calls WHERE customer_id IS NULL OR boat_id IS NULL"
            )
        }
        assert unmatched == {"Volkan Tekin", "Ece Aksoy", "Tuncay Erdem"}

        # RAG parçalarının sahibi, teknenin sahibiyle aynı olmalı (yetkilendirme verisi).
        wrong_owner = await conn.fetchval(
            "SELECT count(*) FROM rag_chunks r JOIN boats b ON b.id = r.boat_id"
            " WHERE r.owner_id <> b.owner_id"
        )
        assert wrong_owner == 0

        # Servis emri durumları: Miço Usta iş akışının tamamı temsil edilmeli.
        statuses = {
            r["status"] for r in await conn.fetch("SELECT DISTINCT status FROM service_orders")
        }
        assert statuses == {"yeni_atandi", "kesifte", "onaylandi", "devam_ediyor", "tamamlandi"}

        # Giderler yalnızca tamamlanmış işlere bağlı olmalı; abonelik hakları tutarlı.
        open_with_expense = await conn.fetchval(
            "SELECT count(*) FROM expenses e JOIN service_orders s ON s.id = e.service_order_id"
            " WHERE s.status <> 'tamamlandi'"
        )
        assert open_with_expense == 0
    finally:
        await conn.close()


async def test_seed_attaches_generated_audio_with_real_timing(tmp_path: Path) -> None:
    """Ses klasöründe `seed/call_001.wav` varsa yalnızca o çağrıya bağlanır (#85).

    Süre ve segment zamanları sesin gerçek değerleridir; ses olmayan çağrılar sessiz kalır.
    Test sonunda seed varsayılan ses klasörüyle yeniden yüklenir (yerel sesler geri bağlanır).
    """
    url = Settings().database_url
    call_json = json.loads((DATA_DIR / "calls" / "call_001.json").read_text(encoding="utf-8"))
    turns = call_json["turns"]
    wav, timing = build_wav(
        turns, lambda text: (array("h", [500] * (100 * len(text))).tobytes(), 1000)
    )
    write_seed_audio(tmp_path, "call_001", wav, timing)

    try:
        counts = await seed_database(url, audio_dir=tmp_path)
        assert counts["calls_with_audio"] == 1

        conn = await asyncpg.connect(_asyncpg_dsn(url), statement_cache_size=0)
        try:
            call = await conn.fetchrow(
                "SELECT id, audio_path, audio_sha256, duration_s FROM calls"
                " WHERE audio_path IS NOT NULL"
            )
            assert call["audio_path"] == "seed/call_001.wav"
            assert call["audio_sha256"] == hashlib.sha256(wav).hexdigest()
            assert call["duration_s"] == round(
                sum(e - s for s, e in timing) / 1000 + 0.5 * len(turns)
            )
            segs = await conn.fetch(
                "SELECT ts.start_ms, ts.end_ms FROM transcript_segments ts"
                " JOIN transcripts t ON t.id = ts.transcript_id WHERE t.call_id = $1"
                " ORDER BY ts.segment_index",
                call["id"],
            )
            assert [(r["start_ms"], r["end_ms"]) for r in segs] == timing
        finally:
            await conn.close()

    finally:
        await seed_database(url)  # varsayılan ses klasörüyle eski durumu geri yükle


async def test_seeded_table_counts_match_readme_and_synthetic_files() -> None:
    """Yüklenen kayıt sayıları generator ve JSON dosyalarıyla birebir eşleşmeli (#82).

    Veritabanının bu dosyadaki ilk testle (`reset=True`) yüklenmiş temiz seed durumunda olmasını
    bekler; elle eklenmiş çağrılar olan bir yerel veritabanında tek başına çalıştırılırsa düşer.
    """
    ds = generate_dataset()
    bundle = load_calls_bundle(data_dir=DATA_DIR)
    expected = {
        "customers": len(ds["customers"]),
        "boats": len(ds["boats"]),
        "craftsmen": len(ds["craftsmen"]),
        "service_orders": len(ds["service_orders"]),
        "boat_notes": len(ds["boat_notes"]),
        "expenses": len(ds["expenses"]),
        "subscriptions": len(ds["subscriptions"]),
        "calls": len(bundle),
        "transcripts": len(bundle),
        "transcript_segments": sum(len(item["turns"]) for item in bundle),
        "analysis_results": sum(1 for item in bundle if item["truth"]),
    }
    conn = await asyncpg.connect(_asyncpg_dsn(Settings().database_url), statement_cache_size=0)
    try:
        for table, count in expected.items():
            assert await conn.fetchval(f"SELECT count(*) FROM {table}") == count, table
    finally:
        await conn.close()
