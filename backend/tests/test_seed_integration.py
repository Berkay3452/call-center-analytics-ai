"""Seed script'inin gerçek PostgreSQL üzerindeki testi (#23).

Yalnızca `RUN_DB_TESTS=1` iken çalışır (CI'da migration'dan sonra). Seed veriyi KALICI yazar,
bu yüzden yalnızca CI'daki tek kullanımlık veritabanında veya yerelde `--reset` kabul edilerek
çalıştırılmalıdır.
"""

import os

import asyncpg
import pytest

from app.core.config import Settings
from scripts.seed.loader import _asyncpg_dsn, seed_database

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_DB_TESTS") != "1", reason="RUN_DB_TESTS=1 değil (gerçek veritabanı gerekir)"
)

EXPECTED_AT_LEAST = {
    "customers": 15,
    "boats": 20,
    "craftsmen": 5,
    "boat_notes": 60,
    "calls": 10,
    "transcripts": 10,
    "analysis_results": 10,
}


async def test_seed_fills_empty_database_and_is_idempotent() -> None:
    url = Settings().database_url

    first = await seed_database(url, reset=True)  # boş veritabanından başla
    second = await seed_database(url)  # ikinci çalıştırma: sayılar değişmemeli
    third = await seed_database(url)

    assert first == second == third
    for table, minimum in EXPECTED_AT_LEAST.items():
        assert first[table] >= minimum, (table, first[table])
    assert first["transcript_segments"] >= 10 * 15
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
        )
        assert row is not None
        assert (row["name"], row["request_category"], row["next_action"]) == (
            "Rüzgar",
            "makine",
            "servis_randevusu_olustur",
        )

        # Her çağrı bir müşteriye ve tekneye bağlanmış olmalı.
        unmatched = await conn.fetchval(
            "SELECT count(*) FROM calls WHERE customer_id IS NULL OR boat_id IS NULL"
        )
        assert unmatched == 0

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
