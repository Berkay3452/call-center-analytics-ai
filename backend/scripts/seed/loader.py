"""Sentetik veriyi PostgreSQL veritabanına idempotent olarak yükler (#23).

Tablolar Alembic migration'ı (#6, `uv run alembic upgrade head`) ile oluşturulur.
Bu modül hem Miço Usta tablolarını (`customers`, `boats`, `craftsmen`, `service_orders`,
`boat_notes`, `expenses`, `subscriptions`, `rag_chunks`) hem de Berkay'ın çağrı
verisini (`calls`, `transcripts`, `transcript_segments`, `analysis_results`)
doldurur. İkinci ve sonraki çalıştırmalarda `ON CONFLICT DO UPDATE` sayesinde
hata vermez ve kayıt sayısını bozmaz.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

import asyncpg

from app.core.config import get_settings
from app.services.audio_ingest import storage_dir
from scripts.seed.audio import load_seed_audio
from scripts.seed.generator import (
    DATA_DIR,
    SEED,
    deterministic_uuid,
    generate_dataset,
    load_calls_bundle,
)

ALL_TABLES: tuple[str, ...] = (
    "chat_messages",
    "chat_sessions",
    "agent_runs",
    "analysis_results",
    "transcript_segments",
    "transcripts",
    "calls",
    "rag_chunks",
    "expenses",
    "subscriptions",
    "boat_notes",
    "service_orders",
    "boats",
    "craftsmen",
    "customers",
)


def _asyncpg_dsn(database_url: str) -> str:
    """SQLAlchemy URL'sini (`postgresql+asyncpg://...`) `asyncpg` biçimine çevirir."""
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _dt(val: str | None) -> datetime | None:
    return datetime.fromisoformat(val) if val else None


def _d(val: str | None) -> date | None:
    return date.fromisoformat(val) if val else None


async def reset_tables(conn: asyncpg.Connection) -> None:
    """Tüm hedef tabloları FK sırasına takılmadan temizler."""
    joined = ", ".join(ALL_TABLES)
    await conn.execute(f"TRUNCATE TABLE {joined} CASCADE;")


async def seed_database(
    database_url: str,
    *,
    data_dir: Path = DATA_DIR,
    seed: int = SEED,
    reset: bool = False,
    audio_dir: Path | None = None,
) -> dict[str, int]:
    """Sentetik veriyi veritabanına yazar ve tablo başına kayıt sayılarını döner.

    `audio_dir`: `scripts/generate_audio.py`'nin sesleri yazdığı klasör (boşsa `AUDIO_STORAGE_DIR`).
    İçinde `seed/<call_id>.wav` olan çağrılara ses bağlanır; olmayanlar sessiz kalır.
    """
    if audio_dir is None:
        audio_dir = storage_dir(get_settings())
    dataset = generate_dataset(seed=seed)
    calls_bundle = load_calls_bundle(data_dir=data_dir)

    conn = await asyncpg.connect(
        _asyncpg_dsn(database_url),
        statement_cache_size=0,
    )
    try:
        has_customers = await conn.fetchval(
            "SELECT EXISTS ("
            "SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'customers'"
            ");"
        )
        if not has_customers:
            raise RuntimeError(
                "Veritabanı tabloları bulunamadı. "
                "Önce `uv run alembic upgrade head` komutunu çalıştırın."
            )

        async with conn.transaction():
            if reset:
                await reset_tables(conn)

            # 1. customers
            for c in dataset["customers"]:
                await conn.execute(
                    """
                    INSERT INTO customers (id, full_name, phone, email, marina, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (id) DO UPDATE SET
                        full_name = EXCLUDED.full_name,
                        phone = EXCLUDED.phone,
                        email = EXCLUDED.email,
                        marina = EXCLUDED.marina
                    """,
                    UUID(c["id"]),
                    c["full_name"],
                    c["phone"],
                    c["email"],
                    c["marina"],
                    _dt(c["created_at"]),
                )

            # 2. boats
            for b in dataset["boats"]:
                await conn.execute(
                    """
                    INSERT INTO boats (id, owner_id, name, model, year, marina, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT (id) DO UPDATE SET
                        owner_id = EXCLUDED.owner_id,
                        name = EXCLUDED.name,
                        model = EXCLUDED.model,
                        year = EXCLUDED.year,
                        marina = EXCLUDED.marina
                    """,
                    UUID(b["id"]),
                    UUID(b["owner_id"]),
                    b["name"],
                    b["model"],
                    int(b["year"]),
                    b["marina"],
                    _dt(b["created_at"]),
                )

            # 3. craftsmen
            for cr in dataset["craftsmen"]:
                await conn.execute(
                    """
                    INSERT INTO craftsmen (id, full_name, specialty, phone, created_at)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (id) DO UPDATE SET
                        full_name = EXCLUDED.full_name,
                        specialty = EXCLUDED.specialty,
                        phone = EXCLUDED.phone
                    """,
                    UUID(cr["id"]),
                    cr["full_name"],
                    cr["specialty"],
                    cr["phone"],
                    _dt(cr["created_at"]),
                )

            # 4. service_orders
            for srv in dataset["service_orders"]:
                await conn.execute(
                    """
                    INSERT INTO service_orders (
                        id, boat_id, customer_id, craftsman_id, category,
                        description, status, scheduled_at, completed_at, created_at
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    ON CONFLICT (id) DO UPDATE SET
                        boat_id = EXCLUDED.boat_id,
                        customer_id = EXCLUDED.customer_id,
                        craftsman_id = EXCLUDED.craftsman_id,
                        category = EXCLUDED.category,
                        description = EXCLUDED.description,
                        status = EXCLUDED.status,
                        scheduled_at = EXCLUDED.scheduled_at,
                        completed_at = EXCLUDED.completed_at
                    """,
                    UUID(srv["id"]),
                    UUID(srv["boat_id"]),
                    UUID(srv["customer_id"]),
                    UUID(srv["craftsman_id"]),
                    srv["category"],
                    srv["description"],
                    srv["status"],
                    _dt(srv["scheduled_at"]),
                    _dt(srv["completed_at"]),
                    _dt(srv["created_at"]),
                )

            # 5. boat_notes
            for note in dataset["boat_notes"]:
                await conn.execute(
                    """
                    INSERT INTO boat_notes (
                        id, boat_id, author_id, content, note_date, created_at
                    )
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (id) DO UPDATE SET
                        boat_id = EXCLUDED.boat_id,
                        author_id = EXCLUDED.author_id,
                        content = EXCLUDED.content,
                        note_date = EXCLUDED.note_date
                    """,
                    UUID(note["id"]),
                    UUID(note["boat_id"]),
                    UUID(note["author_id"]),
                    note["content"],
                    _d(note["note_date"]),
                    _dt(note["created_at"]),
                )

            # 6. expenses
            for exp in dataset["expenses"]:
                await conn.execute(
                    """
                    INSERT INTO expenses (
                        id, boat_id, service_order_id, amount, currency,
                        description, expense_date, created_at
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ON CONFLICT (id) DO UPDATE SET
                        boat_id = EXCLUDED.boat_id,
                        service_order_id = EXCLUDED.service_order_id,
                        amount = EXCLUDED.amount,
                        currency = EXCLUDED.currency,
                        description = EXCLUDED.description,
                        expense_date = EXCLUDED.expense_date
                    """,
                    UUID(exp["id"]),
                    UUID(exp["boat_id"]),
                    UUID(exp["service_order_id"]) if exp["service_order_id"] else None,
                    Decimal(str(exp["amount"])),
                    exp["currency"],
                    exp["description"],
                    _d(exp["expense_date"]),
                    _dt(exp["created_at"]),
                )

            # 7. subscriptions
            for sub in dataset["subscriptions"]:
                await conn.execute(
                    """
                    INSERT INTO subscriptions (
                        id, customer_id, boat_id, plan_name, total_services,
                        used_services, starts_at, expires_at, created_at
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    ON CONFLICT (id) DO UPDATE SET
                        customer_id = EXCLUDED.customer_id,
                        boat_id = EXCLUDED.boat_id,
                        plan_name = EXCLUDED.plan_name,
                        total_services = EXCLUDED.total_services,
                        used_services = EXCLUDED.used_services,
                        starts_at = EXCLUDED.starts_at,
                        expires_at = EXCLUDED.expires_at
                    """,
                    UUID(sub["id"]),
                    UUID(sub["customer_id"]),
                    UUID(sub["boat_id"]) if sub["boat_id"] else None,
                    sub["plan_name"],
                    int(sub["total_services"]),
                    int(sub["used_services"]),
                    _d(sub["starts_at"]),
                    _d(sub["expires_at"]),
                    _dt(sub["created_at"]),
                )

            # 8. rag_chunks (usta notları ve servis kayıtlarından tam metin arama parçaları)
            for note in dataset["boat_notes"]:
                chunk_id = UUID(deterministic_uuid("rag_chunk_note", note["code"]))
                await conn.execute(
                    """
                    INSERT INTO rag_chunks (
                        id, source_kind, source_id, boat_id, owner_id,
                        chunk_index, content, created_at
                    )
                    VALUES ($1, 'boat_note', $2, $3, $4, 0, $5, $6)
                    ON CONFLICT (source_kind, source_id, chunk_index) DO UPDATE SET
                        boat_id = EXCLUDED.boat_id,
                        owner_id = EXCLUDED.owner_id,
                        content = EXCLUDED.content
                    """,
                    chunk_id,
                    UUID(note["id"]),
                    UUID(note["boat_id"]),
                    UUID(note["owner_id"]),
                    note["content"],
                    _dt(note["created_at"]),
                )

            for srv in dataset["service_orders"]:
                chunk_id = UUID(deterministic_uuid("rag_chunk_srv", srv["code"]))
                srv_text = (
                    f"{srv['boat_name']} servis kaydı ({srv['category']}): "
                    f"{srv['description']}. Usta: {srv['craftsman_name']}."
                )
                await conn.execute(
                    """
                    INSERT INTO rag_chunks (
                        id, source_kind, source_id, boat_id, owner_id,
                        chunk_index, content, created_at
                    )
                    VALUES ($1, 'service_record', $2, $3, $4, 0, $5, $6)
                    ON CONFLICT (source_kind, source_id, chunk_index) DO UPDATE SET
                        boat_id = EXCLUDED.boat_id,
                        owner_id = EXCLUDED.owner_id,
                        content = EXCLUDED.content
                    """,
                    chunk_id,
                    UUID(srv["id"]),
                    UUID(srv["boat_id"]),
                    UUID(srv["customer_id"]),
                    srv_text,
                    _dt(srv["created_at"]),
                )

            # 9. Berkay'ın çağrı verisi: calls, transcripts, transcript_segments, analysis_results
            customer_by_name = {c["full_name"]: c for c in dataset["customers"]}
            boat_by_pair = {(b["owner_name"], b["name"]): b for b in dataset["boats"]}

            for item in calls_bundle:
                cid: str = item["call_id"]
                call_uuid: UUID = item["uuid"]
                meta = item["meta"]
                cref = meta["customer_ref"]

                cust = customer_by_name.get(cref["customer"])
                boat = boat_by_pair.get((cref["customer"], cref["boat"]))
                # Ses yalnızca `scripts/generate_audio.py` ile üretilmişse bağlanır. Var olmayan
                # bir dosyaya işaret etmek arayüzde "oynat" düğmesini kırar; yoksa boş kalır.
                audio = load_seed_audio(audio_dir, cid)
                audio_rel = audio.relative_path if audio else None
                audio_hash = audio.sha256 if audio else None
                # Ses varsa süre ve segment zamanları sesin gerçek değerleridir.
                duration_s = audio.duration_s if audio else meta["duration_s"]

                await conn.execute(
                    """
                    INSERT INTO calls (
                        id, started_at, answer_delay_s, duration_s, switchboard_outcome,
                        audio_path, audio_sha256, customer_id, boat_id,
                        customer_name, customer_phone, boat_name, boat_model, marina
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                    ON CONFLICT (id) DO UPDATE SET
                        started_at = EXCLUDED.started_at,
                        answer_delay_s = EXCLUDED.answer_delay_s,
                        duration_s = EXCLUDED.duration_s,
                        switchboard_outcome = EXCLUDED.switchboard_outcome,
                        audio_path = EXCLUDED.audio_path,
                        audio_sha256 = EXCLUDED.audio_sha256,
                        customer_id = EXCLUDED.customer_id,
                        boat_id = EXCLUDED.boat_id,
                        customer_name = EXCLUDED.customer_name,
                        customer_phone = EXCLUDED.customer_phone,
                        boat_name = EXCLUDED.boat_name,
                        boat_model = EXCLUDED.boat_model,
                        marina = EXCLUDED.marina,
                        updated_at = now()
                    """,
                    call_uuid,
                    _dt(meta["started_at"]),
                    meta["answer_delay_s"],
                    duration_s,
                    meta["switchboard_outcome"],
                    audio_rel,
                    audio_hash,
                    UUID(cust["id"]) if cust else None,
                    UUID(boat["id"]) if boat else None,
                    cref["customer"],
                    cust["phone"] if cust else None,
                    cref["boat"],
                    cref["boat_model"],
                    cref["marina"],
                )

                turns = item["turns"]
                full_text = "\n".join(f"{t['speaker']}: {t['text']}" for t in turns)
                transcript_uuid = uuid5(NAMESPACE_URL, f"synthetic/transcript/{cid}")

                await conn.execute(
                    """
                    INSERT INTO transcripts (id, call_id, full_text, masked_text)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (call_id) DO UPDATE SET
                        full_text = EXCLUDED.full_text,
                        masked_text = EXCLUDED.masked_text
                    """,
                    transcript_uuid,
                    call_uuid,
                    full_text,
                    full_text,
                )

                real_timing = audio.timing if audio and audio.timing else None
                if real_timing is not None and len(real_timing) != len(turns):
                    real_timing = None  # ses ve metin uyuşmuyorsa tahmini süreler kullanılır
                t_ms = 0
                for seg_idx, turn in enumerate(turns):
                    dur_ms = max(1000, len(turn["text"]) * 65)
                    if real_timing is not None:
                        seg_start, seg_end = real_timing[seg_idx]
                    else:
                        seg_start, seg_end = t_ms, t_ms + dur_ms
                    seg_uuid = uuid5(NAMESPACE_URL, f"synthetic/segment/{cid}/{seg_idx}")
                    await conn.execute(
                        """
                        INSERT INTO transcript_segments (
                            id, transcript_id, segment_index, speaker,
                            start_ms, end_ms, text, masked_text
                        )
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                        ON CONFLICT (transcript_id, segment_index) DO UPDATE SET
                            speaker = EXCLUDED.speaker,
                            start_ms = EXCLUDED.start_ms,
                            end_ms = EXCLUDED.end_ms,
                            text = EXCLUDED.text,
                            masked_text = EXCLUDED.masked_text
                        """,
                        seg_uuid,
                        transcript_uuid,
                        seg_idx,
                        turn["speaker"],
                        seg_start,
                        seg_end,
                        turn["text"],
                        turn["text"],
                    )
                    t_ms += dur_ms

                truth = item["truth"]
                if truth:
                    analysis_uuid = uuid5(NAMESPACE_URL, f"synthetic/analysis/{cid}/v1")
                    crm = truth["crm"]
                    sales = truth["sales"]
                    summary_text = (
                        f"{cref['marina']} lokasyonundaki {cref['boat']} teknesi için "
                        f"{truth['call_type']} görüşmesi ({sales['outcome']})."
                    )
                    await conn.execute(
                        """
                        INSERT INTO analysis_results (
                            id, call_id, version, status,
                            call_type, call_type_confidence, call_type_reason,
                            request_category, location, problem, service_mode,
                            urgency, potential_job, next_action, crm_evidence,
                            sales_outcome, loss_reason, sales_evidence, sales_confidence,
                            summary, key_points, errors
                        )
                        VALUES (
                            $1, $2, 1, 'tamam',
                            $3, 1.0, $4,
                            $5, $6, $7, $8,
                            $9, $10, $11, '{}'::jsonb,
                            $12, $13, $14, 1.0,
                            $15, '[]'::jsonb, '{}'::jsonb
                        )
                        ON CONFLICT (call_id, version) DO UPDATE SET
                            status = EXCLUDED.status,
                            call_type = EXCLUDED.call_type,
                            call_type_reason = EXCLUDED.call_type_reason,
                            request_category = EXCLUDED.request_category,
                            location = EXCLUDED.location,
                            problem = EXCLUDED.problem,
                            service_mode = EXCLUDED.service_mode,
                            urgency = EXCLUDED.urgency,
                            potential_job = EXCLUDED.potential_job,
                            next_action = EXCLUDED.next_action,
                            sales_outcome = EXCLUDED.sales_outcome,
                            loss_reason = EXCLUDED.loss_reason,
                            sales_evidence = EXCLUDED.sales_evidence,
                            summary = EXCLUDED.summary
                        """,
                        analysis_uuid,
                        call_uuid,
                        truth["call_type"],
                        "Sentetik doğru etiket (ground truth)",
                        crm["request_category"],
                        crm["location"],
                        crm["problem"],
                        crm["service_mode"],
                        crm["urgency"],
                        crm["potential_job"],
                        crm["next_action"],
                        sales["outcome"],
                        sales["loss_reason"],
                        None,  # kanıt alıntısı: etiket notları kullanıcıya gösterilmez
                        summary_text,
                    )
                    # Analizi olan çağrı "tamam" durumundadır (analizi olmayan "beklemede" kalır).
                    await conn.execute(
                        "UPDATE calls SET state = 'tamam', error = NULL WHERE id = $1", call_uuid
                    )

        counts: dict[str, int] = {}
        for tbl in (
            "customers",
            "boats",
            "craftsmen",
            "service_orders",
            "boat_notes",
            "expenses",
            "subscriptions",
            "rag_chunks",
            "calls",
            "transcripts",
            "transcript_segments",
            "analysis_results",
        ):
            val = await conn.fetchval(f"SELECT count(*) FROM {tbl};")
            counts[tbl] = int(val or 0)
        counts["calls_with_audio"] = int(
            await conn.fetchval("SELECT count(*) FROM calls WHERE audio_path IS NOT NULL;") or 0
        )
        return counts
    finally:
        await conn.close()
