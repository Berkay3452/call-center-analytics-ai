"""Çalışan bir API + Celery işçisine karşı uçtan uca duman testi (#157).

Konteynerde (`infra/docker-compose.smoke.yml`) ya da yerelde, LLM sahte sunucuyla
(`scripts/fake_llm.py`) çalıştırılır:

    python -m scripts.duman_testi --base-url http://localhost:18000 --key duman-test-anahtari

Adımlar: hazır olma → seed verisi var mı → seed çağrısının sesi (Range ile) oynatılabiliyor mu →
metinle çağrı yükleme → analiz bitti mi → sesle çağrı yükleme (STT) → analiz bitti mi. Her adım
PASS/FAIL yazar; herhangi biri başarısızsa çıkış kodu 1 olur.
"""

import argparse
import sys
import time
from datetime import UTC, datetime
from typing import Any

import httpx

FINAL = ("tamam", "kismi", "basarisiz")
TRANSCRIPT = [
    {"speaker": "rep", "text": "Miço Usta, buyurun."},
    {
        "speaker": "customer",
        "text": "Tuzla Marina'da teknemin motoru çalışmıyor, usta gelebilir mi?",
    },
]


class Smoke:
    def __init__(self, client: httpx.Client, timeout: float) -> None:
        self.client = client
        self.timeout = timeout
        self.results: list[tuple[str, bool, str]] = []

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        self.results.append((name, ok, detail))
        print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}", flush=True)
        return ok

    def wait_final(self, call_id: str) -> tuple[str, float, dict[str, Any]]:
        started = time.monotonic()
        while time.monotonic() - started < self.timeout:
            status = self.client.get(f"/api/v1/calls/{call_id}/status").json()
            if status["state"] in FINAL:
                return status["state"], time.monotonic() - started, status
            time.sleep(1.0)
        return "zaman_asimi", time.monotonic() - started, {}


def run(args: argparse.Namespace) -> int:
    headers = {"X-Service-Key": args.key} if args.key else {}
    with httpx.Client(base_url=args.base_url, headers=headers, timeout=60) as client:
        smoke = Smoke(client, args.timeout)

        ready = client.get("/health/ready")
        if not smoke.check("hazır olma (/health/ready)", ready.status_code == 200, ready.text[:80]):
            return 1

        seed_audio = b""
        if not args.no_seed:
            page = client.get("/api/v1/calls", params={"page_size": 50}).json()
            smoke.check(
                "seed çağrıları yüklü", page.get("total", 0) >= 50, f"toplam={page.get('total')}"
            )

            with_audio = next(
                (
                    c["id"]
                    for c in page["items"]
                    if client.get(f"/api/v1/calls/{c['id']}").json()["has_audio"]
                ),
                None,
            )
            smoke.check("seed çağrısının sesi var (has_audio)", with_audio is not None)
            if with_audio:
                part = client.get(
                    f"/api/v1/calls/{with_audio}/audio", headers={**headers, "Range": "bytes=0-99"}
                )
                smoke.check(
                    "seed sesi Range ile çalınabiliyor (206)",
                    part.status_code == 206
                    and part.headers.get("content-type", "").startswith("audio"),
                    f"{part.status_code} {part.headers.get('content-type')}",
                )
                seed_audio = client.get(f"/api/v1/calls/{with_audio}/audio").content

        # Metinle yükleme → analiz
        started_at = datetime.now(UTC).isoformat()
        accepted = client.post(
            "/api/v1/calls",
            json={"started_at": started_at, "marina": "Tuzla Marina", "segments": TRANSCRIPT},
        )
        if smoke.check("metin yükleme (202)", accepted.status_code == 202, accepted.text[:80]):
            state, secs, _ = smoke.wait_final(accepted.json()["call_id"])
            smoke.check(
                "metin çağrısı analizi bitti (tamam)", state == "tamam", f"{state} {secs:.0f} sn"
            )

        # Sesle yükleme → STT → analiz (gerçek konuşma: seed sesinin bir örneği değiştirilerek)
        if args.skip_audio_upload or not seed_audio:
            print("SKIP  sesle yükleme", flush=True)
        else:
            data = bytearray(seed_audio)
            data[-3] ^= 1  # tek örneğin en düşük biti: farklı özet (409 yinelenen ses olmasın)
            up = client.post(
                "/api/v1/calls/audio",
                files={"file": ("duman.wav", bytes(data), "audio/wav")},
                data={"started_at": started_at},
            )
            if smoke.check("ses yükleme (202)", up.status_code == 202, up.text[:80]):
                state, secs, status = smoke.wait_final(up.json()["call_id"])
                smoke.check(
                    "ses çağrısı STT + analiz bitti (tamam)",
                    state == "tamam",
                    f"{state} {secs:.0f} sn {status.get('error') or ''}"[:160],
                )

    failed = [name for name, ok, _ in smoke.results if not ok]
    print(f"\n{len(smoke.results) - len(failed)}/{len(smoke.results)} adım geçti.")
    return 1 if failed else 0


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--key", default=None, help="X-Service-Key (AUTH_DEV_BYPASS iken gerekmez)")
    parser.add_argument("--timeout", type=float, default=300, help="çağrı başına bekleme (sn)")
    parser.add_argument("--skip-audio-upload", action="store_true")
    parser.add_argument(
        "--no-seed", action="store_true", help="seed verisi/sesi kontrollerini atla"
    )
    return run(parser.parse_args())


if __name__ == "__main__":
    sys.exit(main())
