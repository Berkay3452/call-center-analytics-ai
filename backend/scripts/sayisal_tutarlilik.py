"""Miço AI sayısal soru tutarlılığı (#151): sohbet cevabı = bağımsız SQL sonucu mu?

Kullanım (backend/ klasöründe; .env'de LLM ve veritabanı ayarları dolu olmalı):

    python -m scripts.sayisal_tutarlilik --questions 20 --out sonuc.json

Gerçek tekne sahipleri için gider toplamı ve kalan bakım hakkı soruları sorulur. Sayılar kodla
hesaplanır (LLM yalnızca soruyu araca eşler); beklenen değer ise asistan koduna dokunmadan ham SQL
ile alınır. Veritabanında yalnızca okuma yapılır. Dönem sorularında `today` verilerin son
gider ayına sabitlenir, böylece sonuç ölçüm gününe bağlı kalmaz.
"""

import argparse
import asyncio
import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.assistant.assistant import answer_question
from app.core.config import Settings
from app.db.session import create_engine, create_session_factory
from app.schemas.assistant import AssistantRequest

MONEY = re.compile(r"(\d{1,3}(?:\.\d{3})*,\d{2}) TL")
RIGHTS = re.compile(r"(\d+) bakım hakkınız kaldı")

TOTAL_QUESTIONS = ["Toplam ne kadar harcadım?", "Tekne giderlerim toplam ne tutuyor?"]
MONTH_QUESTIONS = ["Bu ay ne kadar harcadım?", "Bu ayki toplam giderim nedir?"]
RIGHTS_QUESTIONS = ["Kaç bakım hakkım kaldı?", "Paketimde kalan bakım hakkı kaç?"]


@dataclass
class Case:
    owner_id: str
    kind: str  # toplam | ay | hak
    question: str
    expected: str
    today: date
    got: str | None = None
    answer: str = ""
    seconds: float = 0.0
    ok: bool = False


def parse_money(value: str) -> Decimal:
    return Decimal(value.replace(".", "").replace(",", "."))


def format_expected_money(amount: Decimal) -> str:
    return f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def extract_number(kind: str, answer: str) -> str | None:
    """Cevap metninden sayıyı çıkarır (para: '14.250,00'; hak: '3')."""
    match = (RIGHTS if kind == "hak" else MONEY).search(answer)
    return match.group(1) if match else None


async def build_cases(conn: Any, count: int) -> list[Case]:
    owners = (
        await conn.execute(
            text(
                "SELECT b.owner_id, MAX(e.expense_date) AS last_day, "
                "       (SELECT COUNT(*) FROM subscriptions s "
                "        WHERE s.customer_id = b.owner_id) AS subs "
                "FROM expenses e JOIN boats b ON b.id = e.boat_id "
                "WHERE e.expense_date IS NOT NULL GROUP BY b.owner_id ORDER BY b.owner_id"
            )
        )
    ).all()
    cases: list[Case] = []
    for i, (owner, last_day, subs) in enumerate(owners):
        total = (
            await conn.execute(
                text(
                    "SELECT COALESCE(SUM(e.amount), 0) FROM expenses e "
                    "JOIN boats b ON b.id = e.boat_id WHERE b.owner_id = :o"
                ),
                {"o": owner},
            )
        ).scalar_one()
        month = (
            await conn.execute(
                text(
                    "SELECT COALESCE(SUM(e.amount), 0) FROM expenses e "
                    "JOIN boats b ON b.id = e.boat_id WHERE b.owner_id = :o "
                    "AND date_trunc('month', e.expense_date) "
                    "= date_trunc('month', CAST(:d AS date))"
                ),
                {"o": owner, "d": last_day},
            )
        ).scalar_one()
        oid = str(owner)
        cases.append(
            Case(oid, "toplam", TOTAL_QUESTIONS[i % 2], format_expected_money(total), last_day)
        )
        cases.append(
            Case(oid, "ay", MONTH_QUESTIONS[i % 2], format_expected_money(month), last_day)
        )
        if subs:
            remaining = (
                await conn.execute(
                    text(
                        "SELECT total_services - used_services FROM subscriptions "
                        "WHERE customer_id = :o ORDER BY expires_at DESC NULLS LAST LIMIT 1"
                    ),
                    {"o": owner},
                )
            ).scalar_one()
            cases.append(Case(oid, "hak", RIGHTS_QUESTIONS[i % 2], str(remaining), last_day))
    return cases[:count]


async def run_case(case: Case, session_factory: Any) -> None:
    started = time.perf_counter()
    async with session_factory() as session:
        reply = await answer_question(
            AssistantRequest(question=case.question, owner_id=case.owner_id),
            today=case.today,
            session=session,
        )
    case.seconds = round(time.perf_counter() - started, 1)
    case.answer = reply.answer
    case.got = extract_number(case.kind, reply.answer)
    case.ok = case.got == case.expected


def render(cases: list[Case]) -> str:
    rows = [
        "| # | Tür | Soru | Beklenen (SQL) | Sohbet cevabı | Sonuç |",
        "|---|---|---|---|---|---|",
    ]
    for i, c in enumerate(cases, 1):
        rows.append(
            f"| {i} | {c.kind} | {c.question} | {c.expected} | {c.got or '—'} | "
            f"{'✓' if c.ok else '✗'} |"
        )
    ok = sum(c.ok for c in cases)
    rows.append(f"\nTutarlı: {ok}/{len(cases)} (%{100 * ok / len(cases):.0f})")
    return "\n".join(rows)


async def main_async(args: argparse.Namespace) -> int:
    settings = Settings()
    engine = create_engine(settings, null_pool=True)
    factory = create_session_factory(engine)
    try:
        async with engine.connect() as conn:
            cases = await build_cases(conn, args.questions)
        for case in cases:
            await run_case(case, factory)
            print(
                f"  {case.kind} {case.question!r}: {case.got} ({'ok' if case.ok else 'FARKLI'})",
                file=sys.stderr,
            )
            await asyncio.sleep(args.gap)
    finally:
        await engine.dispose()
    print(render(cases))
    if args.out:
        await asyncio.to_thread(
            Path(args.out).write_text,
            json.dumps([c.__dict__ for c in cases], ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    return 0 if all(c.ok for c in cases) else 1


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=int, default=20)
    parser.add_argument("--gap", type=float, default=1.0, help="sorular arası bekleme (sn)")
    parser.add_argument("--out", default=None)
    return asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
