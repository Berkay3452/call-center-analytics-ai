"""Hafif yük testi (#158): eşzamanlı isteklerde liste, KPI ve sohbet uçlarının gecikmesi.

Çalışan bir API'ye karşı (ayrı/seed'li bir veritabanında; sohbet uçları kayıt yazar):

    python -m scripts.yuk_testi --base-url http://127.0.0.1:8100 --owner-id <müşteri UUID>

Uçlar: `GET /calls` (liste), `GET /analytics/summary` (KPI), `POST /chat/messages` ("selam":
LLM'siz hazır cevap; yani API + veritabanı yolunu ölçer, LLM kotasını yemez). LLM'li sohbet
soruları sağlayıcıya bağlıdır (bkz. docs/dayaniklilik.md), bu betikte ölçülmez.
Servis anahtarı `.env`'den okunur ve çıktıya yazılmaz.
"""

import argparse
import asyncio
import statistics
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import httpx

from scripts.dayaniklilik import fmt, md_table, percentile


@dataclass
class Result:
    name: str
    concurrency: int
    durations: list[float] = field(default_factory=list)
    errors: int = 0
    statuses: dict[int, int] = field(default_factory=dict)
    wall_s: float = 0.0

    def row(self) -> list[object]:
        total = len(self.durations) + self.errors
        ms = [d * 1000 for d in self.durations]
        return [
            self.name,
            self.concurrency,
            total,
            f"{total / self.wall_s:.1f}" if self.wall_s else "—",
            fmt(percentile(ms, 50), 0),
            fmt(percentile(ms, 95), 0),
            fmt(max(ms) if ms else None, 0),
            f"{statistics.fmean(ms):.0f}" if ms else "—",
            self.errors,
        ]


async def run_level(
    name: str, send: Callable[[], Awaitable[httpx.Response]], concurrency: int, requests: int
) -> Result:
    result = Result(name, concurrency)
    sem = asyncio.Semaphore(concurrency)

    async def one() -> None:
        async with sem:
            started = time.perf_counter()
            try:
                resp = await send()
                result.statuses[resp.status_code] = result.statuses.get(resp.status_code, 0) + 1
                if resp.status_code == 200:
                    result.durations.append(time.perf_counter() - started)
                else:
                    result.errors += 1
            except Exception:
                result.errors += 1

    started = time.perf_counter()
    await asyncio.gather(*[one() for _ in range(requests)])
    result.wall_s = time.perf_counter() - started
    return result


async def main_async(args: argparse.Namespace) -> int:
    from app.core.config import Settings

    configured = Settings().service_api_key
    key = args.service_key or (configured.get_secret_value() if configured else "")
    async with httpx.AsyncClient(
        base_url=args.base_url,
        headers={"X-Service-Key": key},
        timeout=60,
        limits=httpx.Limits(max_connections=200),
    ) as client:
        endpoints = {
            "GET /calls": lambda: client.get("/api/v1/calls", params={"page_size": 20}),
            "GET /analytics/summary": lambda: client.get("/api/v1/analytics/summary"),
        }
        if args.owner_id:
            endpoints["POST /chat/messages (selam)"] = lambda: client.post(
                "/api/v1/chat/messages",
                json={"question": "selam"},
                headers={"X-User-Id": args.owner_id},
            )
        else:
            print("--owner-id verilmedi: sohbet ucu atlandı.", file=sys.stderr)
        await client.get("/api/v1/calls")  # ısınma (bağlantı havuzu, ilk sorgu)
        results: list[Result] = []
        for level in [int(x) for x in args.concurrency.split(",")]:
            for name, send in endpoints.items():
                results.append(await run_level(name, send, level, args.requests))
                print(f"  {name} @{level}: {results[-1].statuses}", file=sys.stderr)
    print(
        md_table(
            [
                "Uç",
                "Eşzamanlı",
                "İstek",
                "İstek/sn",
                "p50 ms",
                "p95 ms",
                "maks ms",
                "ort ms",
                "Hata",
            ],
            [r.row() for r in results],
        )
    )
    return 1 if any(r.errors for r in results) else 0


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--service-key", default=None)
    parser.add_argument(
        "--owner-id", default=None, help="sohbet için var olan müşteri kimliği (UUID)"
    )
    parser.add_argument("--concurrency", default="20,30", help="virgülle eşzamanlılık düzeyleri")
    parser.add_argument("--requests", type=int, default=200, help="uç ve düzey başına istek")
    return asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
