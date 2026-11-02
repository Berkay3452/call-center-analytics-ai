"""Ajan ve LLM dayanıklılık ölçümü (#216, #151): toplu yükleme, hata senaryoları, kota sondası.

Üç alt komut vardır (backend/ klasöründe çalıştırılır; sonuç tablosu `docs/dayaniklilik.md`):

    # 1) Toplu çalıştırma: çalışan API + Celery işçisine sentetik çağrıları yükler, bitene dek
    #    izler, aşama sürelerini ve agent_runs hatalarını toplar (HTTP üzerinden; gerçek hat).
    python -m scripts.dayaniklilik batch --base-url http://localhost:8100 --text 30 --audio 5 \
        --audio-dir ../backend/storage/audio/seed --parallel 8 --out sonuc.json

    # 2) Hata senaryoları (süreç içinde; sahte OpenAI-uyumlu sunucu + birkaç gerçek sağlayıcı
    #    denemesi). Çağrılar AYRI bir veritabanına yazılır (DATABASE_URL adında "loadtest" geçmeli).
    python -m scripts.dayaniklilik senaryo --only hang,429,json

    # 3) Gerçek sağlayıcıda kota sondası: ilk 429 kaçıncı istekte, hangi başlıklarla geliyor?
    python -m scripts.dayaniklilik kota --seconds 90 --concurrency 4

    # 4) Takılı çağrı kurtarma (#107) benzetimi: durum geçişleri ve yeniden analiz çakışması.
    python -m scripts.dayaniklilik kurtarma

Gizli anahtar hiçbir çıktıya yazılmaz. `batch` ve `senaryo` ortak veritabanını kirletmesin diye
ayrı bir veritabanı (ör. call_center_loadtest) ve ayrı Redis veritabanı kullanılmalıdır.
"""

import argparse
import asyncio
import json
import statistics
import sys
import threading
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from uuid import UUID

DATA = Path(__file__).parents[2] / "data" / "synthetic"
FINAL_STATES = ("tamam", "kismi", "basarisiz")

# --- Ortak yardımcılar ------------------------------------------------------------------------


def percentile(values: list[float], p: float) -> float | None:
    """Doğrusal aradeğerlemeli yüzdelik (0-100). Boş listede None."""
    if not values:
        return None
    ordered = sorted(values)
    pos = (len(ordered) - 1) * p / 100
    low, high = int(pos), min(int(pos) + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (pos - low)


def fmt(value: float | None, digits: int = 1) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def _write(path: str, payload: str) -> None:
    Path(path).write_text(payload, encoding="utf-8")


def md_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(str(c).replace("|", "/") for c in row) + " |" for row in rows]
    return "\n".join(lines)


def synthetic_ids() -> list[str]:
    return sorted(p.stem for p in (DATA / "calls").glob("call_*.json"))


def load_call(call_id: str) -> tuple[dict[str, Any], list[dict[str, str]]]:
    meta = next(
        m
        for m in json.loads((DATA / "calls_meta.json").read_text(encoding="utf-8"))
        if m["call_id"] == call_id
    )
    doc = json.loads((DATA / "calls" / f"{call_id}.json").read_text(encoding="utf-8"))
    return meta, [{"speaker": t["speaker"], "text": t["text"]} for t in doc["turns"]]


# --- 1) Toplu çalıştırma (HTTP) --------------------------------------------------------------


@dataclass
class CallRun:
    """Bir çağrının yüklemeden sonuca yolculuğu."""

    ref: str
    kind: str  # metin | ses | bozuk_ses
    call_id: str | None = None
    submit_error: str | None = None
    final_state: str | None = None  # tamam | kismi | basarisiz | zaman_asimi
    error: str | None = None
    total_s: float | None = None
    # Durumun ilk görüldüğü an (yüklemeden itibaren sn): {"yaziya_cevriliyor": 3.1, ...}
    seen_s: dict[str, float] = field(default_factory=dict)
    runs: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.final_state == "tamam"


def stage_seconds(run: CallRun) -> dict[str, float | None]:
    """Gözlenen durum geçişlerinden aşama süreleri (yoklama çözünürlüğü kadar kaba)."""
    seen = run.seen_s
    if run.total_s is None:
        return {"kuyruk": None, "stt": None, "analiz": None}
    stt_at, ana_at = seen.get("yaziya_cevriliyor"), seen.get("isleniyor")
    first_active = min((v for v in (stt_at, ana_at) if v is not None), default=run.total_s)
    stt = None if stt_at is None else (ana_at if ana_at is not None else run.total_s) - stt_at
    analiz = None if ana_at is None else run.total_s - ana_at
    return {"kuyruk": first_active, "stt": stt, "analiz": analiz}


def summarize_batch(runs: list[CallRun]) -> dict[str, Any]:
    """Toplu çalıştırma özeti: başarı oranı, süre dağılımı, hata türleri, yeniden denemeler."""
    total = len(runs)
    states = Counter(r.final_state or "gonderilemedi" for r in runs)
    totals = [r.total_s for r in runs if r.total_s is not None and r.final_state in FINAL_STATES]
    agent_ms: dict[str, list[float]] = {}
    kinds: Counter[str] = Counter()
    retried = fallbacks = timeouts = 0
    tokens = 0
    for r in runs:
        for run in r.runs:
            agent_ms.setdefault(run["agent"], []).append(run["latency_ms"] / 1000)
            tokens += run.get("tokens_in", 0) + run.get("tokens_out", 0)
            if run["attempts"] > 1:
                retried += 1
            if run.get("fallback_from"):
                fallbacks += 1
            if run.get("error_kind"):
                kinds[run["error_kind"]] += 1
            if run.get("error_kind") == "timeout":
                timeouts += 1
    return {
        "toplam": total,
        "durumlar": dict(states),
        "tamam_orani": round(100 * states["tamam"] / total, 1) if total else None,
        "kismi_dahil_orani": round(100 * (states["tamam"] + states["kismi"]) / total, 1)
        if total
        else None,
        "toplam_sure_s": {
            "ort": round(statistics.fmean(totals), 1) if totals else None,
            "p50": percentile(totals, 50),
            "p95": percentile(totals, 95),
            "maks": max(totals) if totals else None,
        },
        "agent_sure_s": {
            name: {"p50": percentile(v, 50), "p95": percentile(v, 95), "maks": max(v)}
            for name, v in agent_ms.items()
        },
        "hata_turleri": dict(kinds),
        "yeniden_denenen_agent": retried,
        "yedek_modele_gecen_agent": fallbacks,
        "zaman_asimi_agent": timeouts,
        "token": tokens,
    }


def render_batch(runs: list[CallRun], summary: dict[str, Any]) -> str:
    out = [
        f"Çağrı: {summary['toplam']} · durumlar: {summary['durumlar']} · "
        f"hatasız (tamam): %{summary['tamam_orani']} · "
        f"kısmi dahil: %{summary['kismi_dahil_orani']}",
        "",
    ]
    by_kind: dict[str, list[CallRun]] = {}
    for r in runs:
        by_kind.setdefault(r.kind, []).append(r)
    rows = []
    for kind, items in by_kind.items():
        done = [r.total_s for r in items if r.total_s is not None]
        stages = [stage_seconds(r) for r in items]
        rows.append(
            [
                kind,
                len(items),
                sum(1 for r in items if r.ok),
                fmt(percentile(done, 50)),
                fmt(percentile(done, 95)),
                fmt(max(done) if done else None),
                fmt(percentile([s["kuyruk"] for s in stages if s["kuyruk"] is not None], 50)),
                fmt(percentile([s["stt"] for s in stages if s["stt"] is not None], 50)),
                fmt(percentile([s["analiz"] for s in stages if s["analiz"] is not None], 50)),
            ]
        )
    out.append(
        md_table(
            [
                "Tür",
                "Adet",
                "Tamam",
                "Toplam p50 sn",
                "p95",
                "maks",
                "Kuyruk p50",
                "STT p50",
                "Analiz p50",
            ],
            rows,
        )
    )
    out.append("")
    ag = summary["agent_sure_s"]
    out.append(
        md_table(
            ["Agent", "p50 sn", "p95", "maks"],
            [[n, fmt(v["p50"]), fmt(v["p95"]), fmt(v["maks"])] for n, v in sorted(ag.items())],
        )
    )
    out.append("")
    out.append(
        f"Yeniden denenen agent: {summary['yeniden_denenen_agent']} · yedek modele geçen: "
        f"{summary['yedek_modele_gecen_agent']} · zaman aşımı: {summary['zaman_asimi_agent']} · "
        f"hata türleri: {summary['hata_turleri'] or '—'} · token: {summary['token']}"
    )
    failed = [r for r in runs if not r.ok]
    if failed:
        out += ["", "Tam tamamlanmayanlar:"]
        for r in failed:
            errs = [
                f"{x['agent']}: {x['error_kind']} {x.get('error')!s:.90}"
                for x in r.runs
                if x.get("error_kind")
            ]
            out.append(
                f"- {r.ref} ({r.kind}) → {r.final_state}; {r.submit_error or r.error}; "
                f"{'; '.join(errs)}"
            )
    return "\n".join(out)


async def _track(
    client: Any, run: CallRun, started: float, timeout_s: float, poll_s: float
) -> None:
    """Durumu bitene kadar yoklar; geçişlerin ilk görüldüğü anı not eder."""
    while time.perf_counter() - started < timeout_s:
        resp = await client.get(f"/api/v1/calls/{run.call_id}/status")
        resp.raise_for_status()
        status = resp.json()
        state = status["state"]
        run.seen_s.setdefault(state, round(time.perf_counter() - started, 2))
        if state in FINAL_STATES:
            run.final_state = state
            run.error = status.get("error")
            run.total_s = round(time.perf_counter() - started, 2)
            return
        await asyncio.sleep(poll_s)
    run.final_state = "zaman_asimi"
    run.total_s = round(time.perf_counter() - started, 2)


async def _one_call(
    client: Any,
    run: CallRun,
    sem: asyncio.Semaphore,
    args: argparse.Namespace,
    audio_dir: Path | None,
) -> None:
    async with sem:
        started = time.perf_counter()
        try:
            if run.kind == "metin":
                meta, segments = load_call(run.ref)
                resp = await client.post(
                    "/api/v1/calls",
                    json={
                        "started_at": meta["started_at"],
                        "duration_s": meta["duration_s"],
                        "answer_delay_s": meta["answer_delay_s"],
                        "switchboard_outcome": meta["switchboard_outcome"],
                        "customer_name": meta["customer_ref"]["customer"],
                        "boat_name": meta["customer_ref"]["boat"],
                        "boat_model": meta["customer_ref"]["boat_model"],
                        "marina": meta["customer_ref"]["marina"],
                        "segments": segments,
                    },
                )
            else:
                assert audio_dir is not None
                path = audio_dir / f"{run.ref}.wav"
                content = path.read_bytes()
                if run.kind == "bozuk_ses":
                    content = b"RIFF" + b"\x00" * 64  # başlığı olan ama çözülemeyen sahte wav
                resp = await client.post(
                    "/api/v1/calls/audio",
                    files={"file": (f"{run.ref}.wav", content, "audio/wav")},
                    data={"started_at": datetime.now(UTC).isoformat()},
                )
            if resp.status_code == 409 and resp.json()["error"]["code"] == "duplicate_audio":
                # Aynı ses daha önce yüklenmiş (tekrar koşu): mevcut çağrıyı yeniden işleme al.
                existing = resp.json()["error"]["details"]["call_id"]
                resp = await client.post(f"/api/v1/calls/{existing}/analyze")
            if resp.status_code != 202:
                run.submit_error = f"HTTP {resp.status_code}: {resp.text[:120]}"
                return
            run.call_id = resp.json()["call_id"]
            await _track(client, run, started, args.timeout, args.poll)
            detail = (await client.get(f"/api/v1/calls/{run.call_id}")).json()
            run.runs = (detail.get("analysis") or {}).get("runs", [])
            print(f"  {run.ref} ({run.kind}): {run.final_state} {run.total_s} sn", file=sys.stderr)
        except Exception as exc:
            run.submit_error = f"{type(exc).__name__}: {exc}"


async def cmd_batch(args: argparse.Namespace) -> int:
    import httpx

    key = args.service_key or _env_key()
    ids = synthetic_ids()
    audio_dir = Path(args.audio_dir) if args.audio_dir else None
    runs = [CallRun(ref=i, kind="metin") for i in ids[: args.text]]
    if args.audio:
        if audio_dir is None:
            print("--audio için --audio-dir gerekli.", file=sys.stderr)
            return 2
        runs += [CallRun(ref=i, kind="ses") for i in ids[args.text : args.text + args.audio]]
    if args.bozuk_ses:
        runs.append(CallRun(ref=ids[0], kind="bozuk_ses"))
    sem = asyncio.Semaphore(args.parallel)
    started = time.perf_counter()
    async with httpx.AsyncClient(
        base_url=args.base_url, headers={"X-Service-Key": key}, timeout=60
    ) as client:
        await asyncio.gather(*[_one_call(client, r, sem, args, audio_dir) for r in runs])
    wall = time.perf_counter() - started
    summary = summarize_batch(runs)
    summary["duvar_saati_s"] = round(wall, 1)
    print(render_batch(runs, summary))
    print(f"\nToplam duvar saati: {wall:.0f} sn · paralel istemci: {args.parallel}")
    if args.out:
        _write(
            args.out,
            json.dumps(
                {"ozet": summary, "calls": [r.__dict__ for r in runs]},
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
        )
    return 0 if summary["tamam_orani"] is not None and summary["tamam_orani"] >= 95 else 1


def _env_key() -> str:
    from app.core.config import Settings

    key = Settings().service_api_key
    return key.get_secret_value() if key else ""


# --- 2) Hata senaryoları ----------------------------------------------------------------------

OK_CLASSIFICATION = json.dumps(
    {"call_type": "servis", "confidence": 0.9, "reason": "Müşteri arıza bildiriyor."},
    ensure_ascii=False,
)


class FakeLLM:
    """Yerel OpenAI-uyumlu sahte sunucu; yol `/<mod>/chat/completions` ile davranış seçilir.

    Modlar: ok · hang · 429[:retry_after_s[:ilk_n]] · 500 · 404 · prose · truncated · wrongshape
    · empty. `429:2:3` = ilk 3 isteğe 429 (Retry-After 2), sonrası ok.
    """

    def __init__(self, hang_s: float = 300.0) -> None:
        self.hang_s = hang_s
        self.hits: list[tuple[float, str]] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_: Any) -> None:  # sessiz
                pass

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                self.rfile.read(length)
                mode = self.path.strip("/").split("/")[0]
                with fake._lock:
                    fake.hits.append((time.perf_counter(), mode))
                    seq = sum(1 for _, m in fake.hits if m == mode)
                fake._respond(self, mode, seq)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def base_url(self, mode: str) -> str:
        return f"http://127.0.0.1:{self.port}/{mode}"

    def close(self) -> None:
        self._stop.set()
        self.server.shutdown()
        self.server.server_close()

    def _respond(self, h: BaseHTTPRequestHandler, mode: str, seq: int) -> None:
        name, *params = mode.split(":")
        if name == "429":
            retry_after = params[0] if params else "1"
            first_n = int(params[1]) if len(params) > 1 else None
            if first_n is None or seq <= first_n:
                body = {"error": {"message": "Rate limit exceeded", "type": "rate_limit_error"}}
                return self._send(h, 429, body, {"Retry-After": retry_after})
            name = "ok"
        if name == "hang":
            self._stop.wait(self.hang_s)
            return
        if name in ("500", "404"):
            return self._send(h, int(name), {"error": {"message": f"sahte {name}"}})
        content = {
            "ok": OK_CLASSIFICATION,
            "prose": "Elbette! Bu çağrı bir servis talebidir, ayrıca müşteri memnun görünüyor.",
            "truncated": OK_CLASSIFICATION[:30],
            "wrongshape": json.dumps({"tip": "servis"}),
            "empty": "",
        }[name]
        completion = {
            "id": "x", "object": "chat.completion", "created": 0, "model": "sahte",
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
        }  # fmt: skip
        self._send(h, 200, completion)

    @staticmethod
    def _send(
        h: BaseHTTPRequestHandler,
        status: int,
        body: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> None:
        data = json.dumps(body).encode()
        h.send_response(status)
        h.send_header("Content-Type", "application/json")
        h.send_header("Content-Length", str(len(data)))
        for k, v in (headers or {}).items():
            h.send_header(k, v)
        h.end_headers()
        h.wfile.write(data)


@dataclass
class Scenario:
    key: str
    title: str
    # (fake, settings) → (settings, transkript_metni) ; fake None = gerçek sağlayıcı
    build: Callable[[FakeLLM, Any], tuple[Any, str | None]]
    uses_fake: bool = True
    timeout_s: float = 400.0


def _fake_settings(base: Any, fake: FakeLLM, mode: str, **over: Any) -> Any:
    from pydantic import SecretStr

    update = {
        "llm_provider": "openai_compatible",
        "llm_base_url": fake.base_url(mode),
        "llm_api_key": SecretStr("sahte"),
        "llm_fast_model": "sahte-hizli",
        "llm_smart_model": "sahte-guclu",
        "llm_fallback_model": None,
        "llm_requests_per_minute": 0,
        **over,
    }
    return base.model_copy(update=update)


def _real(base: Any, **over: Any) -> Any:
    return base.model_copy(update=over)


def scenarios() -> list[Scenario]:
    from pydantic import SecretStr

    def s(
        key: str,
        title: str,
        build: Callable[..., Any],
        uses_fake: bool = True,
        timeout_s: float = 400.0,
    ) -> Scenario:
        return Scenario(key, title, build, uses_fake, timeout_s)

    long_text = "Müşteri: Motorda ses var, devir yükselmiyor, marinada bekliyorum. " * 450
    huge_text = "Müşteri: Motorda ses var, devir yükselmiyor, marinada bekliyorum. " * 9000
    return [
        s(
            "hang",
            "Model yanıt vermiyor (varsayılan zaman aşımları)",
            lambda f, b: (_fake_settings(b, f, "hang"), None),
        ),
        s(
            "429",
            "429, Retry-After: 1, hep (sağlayıcı kotayı bitirdi)",
            lambda f, b: (_fake_settings(b, f, "429:1"), None),
        ),
        s(
            "429-uzun",
            "429, Retry-After: 30, hep",
            lambda f, b: (_fake_settings(b, f, "429:30"), None),
        ),
        s(
            "429-gecici",
            "429 ilk 2 istekte, sonra normal (Retry-After: 2)",
            lambda f, b: (_fake_settings(b, f, "429:2:2"), None),
        ),
        s("500", "Sağlayıcı 500 veriyor", lambda f, b: (_fake_settings(b, f, "500"), None)),
        s("404", "Model sağlayıcıda yok (404)", lambda f, b: (_fake_settings(b, f, "404"), None)),
        s(
            "json",
            "LLM düz yazı döndürüyor (JSON yok)",
            lambda f, b: (_fake_settings(b, f, "prose"), None),
        ),
        s(
            "json-kesik",
            "LLM yarım JSON döndürüyor",
            lambda f, b: (_fake_settings(b, f, "truncated"), None),
        ),
        s(
            "sema",
            "LLM geçerli JSON ama şemaya uymuyor",
            lambda f, b: (_fake_settings(b, f, "wrongshape"), None),
        ),
        s("bos", "LLM boş cevap döndürüyor", lambda f, b: (_fake_settings(b, f, "empty"), None)),
        s(
            "ag-yok",
            "Ağ kesintisi: bağlantı reddediliyor",
            lambda f, b: (_fake_settings(b, f, "ok", llm_base_url="http://127.0.0.1:9/v1"), None),
        ),
        s(
            "ag-kara-delik",
            "Ağ kesintisi: paketler düşüyor (yanıt hiç gelmiyor)",
            lambda f, b: (
                _fake_settings(b, f, "ok", llm_base_url="http://10.255.255.1:9/v1"),
                None,
            ),
            timeout_s=300,
        ),
        s(
            "anahtar-gecersiz",
            "Geçersiz API anahtarı (gerçek sağlayıcı)",
            lambda f, b: (_real(b, llm_api_key=SecretStr("nvapi-gecersiz-anahtar-0000")), None),
            uses_fake=False,
        ),
        s(
            "anahtar-bos",
            "Boş API anahtarı",
            lambda f, b: (_real(b, llm_api_key=None), None),
            uses_fake=False,
        ),
        s(
            "uzun",
            "Çok uzun transkript (~30 bin karakter, gerçek sağlayıcı)",
            lambda f, b: (b, long_text),
            uses_fake=False,
        ),
        s(
            "asiri-uzun",
            "Aşırı uzun transkript (~600 bin karakter, gerçek sağlayıcı)",
            lambda f, b: (b, huge_text),
            uses_fake=False,
        ),
    ]


@dataclass
class ScenarioResult:
    key: str
    title: str
    elapsed_s: float
    call_state: str
    call_error: str | None
    agents: list[dict[str, Any]]
    provider_hits: int | None

    def row(self) -> list[Any]:
        kinds = Counter(a["error_kind"] or "ok" for a in self.agents)
        attempts = max((a["attempts"] for a in self.agents), default=0)
        fallback = sum(1 for a in self.agents if a.get("fallback_from"))
        return [
            self.title,
            f"{self.elapsed_s:.1f}",
            self.call_state,
            ", ".join(f"{k}×{v}" for k, v in kinds.items()),
            attempts,
            fallback,
            "—" if self.provider_hits is None else self.provider_hits,
            (self.call_error or "—")[:110],
        ]


async def run_scenario(sc: Scenario, base_settings: Any, factory: Any) -> ScenarioResult:
    from app.agents.registry import build_default_orchestrator
    from app.schemas.api import CallCreate
    from app.services.call_ingest import create_call, get_status, run_call_analysis

    fake = FakeLLM()
    try:
        settings, text = sc.build(fake, base_settings)
        body = (
            text or "Müşteri: Merhaba, teknemin motoru çalışmıyor.\nTemsilci: Usta yönlendirelim."
        )
        async with factory() as session, session.begin():
            call_id = await create_call(
                session, CallCreate(started_at=datetime.now(UTC), transcript=body)
            )
        orchestrator = build_default_orchestrator(settings=settings)
        started = time.perf_counter()
        try:
            await asyncio.wait_for(
                run_call_analysis(call_id, factory, orchestrator=orchestrator), sc.timeout_s
            )
        except TimeoutError:
            print(f"  {sc.key}: {sc.timeout_s} sn içinde bitmedi", file=sys.stderr)
        elapsed = time.perf_counter() - started
        async with factory() as session:
            status = await get_status(session, call_id)
        agents = await _agent_runs(factory, call_id)
        hits = len(fake.hits) if sc.uses_fake else None
        print(f"  {sc.key}: {status.state} {elapsed:.1f} sn", file=sys.stderr)
        return ScenarioResult(sc.key, sc.title, elapsed, status.state, status.error, agents, hits)
    finally:
        fake.close()


async def _agent_runs(factory: Any, call_id: UUID) -> list[dict[str, Any]]:
    from app.services.analysis_store import get_latest_analysis

    async with factory() as session:
        analysis = await get_latest_analysis(session, call_id)
    return [r.model_dump() for r in analysis.runs] if analysis else []


def _guard_database(settings: Any, allow_shared: bool) -> None:
    name = settings.database_url.rsplit("/", 1)[-1].split("?")[0]
    if "loadtest" not in name and not allow_shared:
        print(
            f"Veritabanı '{name}' ölçüm veritabanı gibi görünmüyor (adında 'loadtest' yok). "
            "Ortak veritabanını kirletmemek için çıkılıyor; bilerek istiyorsan --ortak-db ver.",
            file=sys.stderr,
        )
        raise SystemExit(2)


async def cmd_senaryo(args: argparse.Namespace) -> int:
    from app.core.config import Settings
    from app.db.session import create_engine, create_session_factory

    base = Settings()
    _guard_database(base, args.ortak_db)
    only = set(args.only.split(",")) if args.only else None
    chosen = [sc for sc in scenarios() if only is None or sc.key in only]
    engine = create_engine(base, null_pool=True)
    factory = create_session_factory(engine)
    results = []
    try:
        for sc in chosen:
            results.append(await run_scenario(sc, base, factory))
    finally:
        await engine.dispose()
    print(
        md_table(
            [
                "Senaryo",
                "Süre sn",
                "Çağrı durumu",
                "Agent sonuçları",
                "En çok deneme",
                "Yedek",
                "Sahte sunucuya istek",
                "Kullanıcıya görünen hata (calls.error)",
            ],
            [r.row() for r in results],
        )
    )
    if args.out:
        _write(
            args.out,
            json.dumps([r.__dict__ for r in results], ensure_ascii=False, indent=2, default=str),
        )
    return 0


# --- 3) Kota sondası (gerçek sağlayıcı) -----------------------------------------------------


async def cmd_kota(args: argparse.Namespace) -> int:
    import httpx

    from app.core.config import Settings
    from app.llm.client import _resolve_base_url

    cfg = Settings()
    if cfg.llm_api_key is None or not cfg.llm_fast_model:
        print("LLM_API_KEY / LLM_FAST_MODEL tanımlı değil.", file=sys.stderr)
        return 2
    url = _resolve_base_url(cfg).rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {cfg.llm_api_key.get_secret_value()}"}
    payload: dict[str, Any] = {
        "model": cfg.llm_fast_model,
        "messages": [{"role": "user", "content": "Sadece 'tamam' yaz."}],
        "max_tokens": 5,
    }
    if cfg.llm_disable_thinking and cfg.llm_provider == "nvidia":
        payload["chat_template_kwargs"] = {"enable_thinking": False}
    events: list[tuple[float, int, float, dict[str, str]]] = []  # (t, durum, süre, başlıklar)
    t0 = time.perf_counter()
    stop = asyncio.Event()

    async def worker(client: httpx.AsyncClient) -> None:
        while not stop.is_set() and time.perf_counter() - t0 < args.seconds:
            started = time.perf_counter()
            try:
                resp = await client.post(url, headers=headers, json=payload)
                status = resp.status_code
                hdr = {
                    k: v
                    for k, v in resp.headers.items()
                    if k.lower().startswith(("retry-after", "x-ratelimit", "ratelimit"))
                }
            except Exception as exc:
                status, hdr = 0, {"hata": type(exc).__name__}
            events.append((started - t0, status, time.perf_counter() - started, hdr))
            if status == 429 and args.stop_on_429:
                stop.set()
            await asyncio.sleep(args.gap)

    async with httpx.AsyncClient(timeout=40) as client:
        await asyncio.gather(*[worker(client) for _ in range(args.concurrency)])
    codes = Counter(e[1] for e in events)
    first_429 = next((i + 1 for i, e in enumerate(events) if e[1] == 429), None)
    ok_lat = [e[2] for e in events if e[1] == 200]
    print(
        f"Sağlayıcı: {cfg.llm_provider} · model: {cfg.llm_fast_model} · eşzamanlı: "
        f"{args.concurrency} · süre: {args.seconds} sn"
    )
    print(f"İstek: {len(events)} · durum kodları: {dict(codes)} · ilk 429: {first_429}. istek")
    print(
        f"Başarılı istek gecikmesi p50/p95: {fmt(percentile(ok_lat, 50), 2)} / "
        f"{fmt(percentile(ok_lat, 95), 2)} sn"
    )
    minute_buckets = Counter(int(e[0] // 60) for e in events if e[1] == 200)
    print(f"Dakika başına başarılı istek: {dict(minute_buckets)}")
    headers_seen = {k: v for e in events if e[1] == 429 for k, v in e[3].items()}
    print(f"429 yanıt başlıkları: {headers_seen or '—'}")
    return 0


# --- 4) Takılı çağrı kurtarma benzetimi --------------------------------------------------------


async def cmd_kurtarma(args: argparse.Namespace) -> int:
    from sqlalchemy import text

    from app.core.config import Settings
    from app.db.session import create_engine, create_session_factory
    from app.schemas.api import CallCreate
    from app.services.call_ingest import create_call, get_status
    from app.services.call_recovery import recover_stuck_calls

    base = Settings()
    _guard_database(base, args.ortak_db)
    engine = create_engine(base, null_pool=True)
    factory = create_session_factory(engine)
    rows: list[list[Any]] = []

    async def new_call(state: str) -> UUID:
        async with factory() as session, session.begin():
            cid = await create_call(
                session,
                CallCreate(started_at=datetime.now(UTC), transcript="Müşteri: Motor çalışmıyor."),
            )
            await session.execute(
                text(
                    "UPDATE calls SET state = :s, updated_at = now() - interval '30 minutes' "
                    "WHERE id = :id"
                ),
                {"s": state, "id": cid},
            )
        return cid

    async def snap(cid: UUID) -> str:
        async with factory() as session:
            st = await get_status(session, cid)
        return f"{st.state} ({st.error or '—'})"

    try:
        for state in ("beklemede", "yaziya_cevriliyor", "isleniyor"):
            cid = await new_call(state)
            r1 = await recover_stuck_calls(factory, timeout_min=10, enqueue=False)
            after1 = await snap(cid)
            async with factory() as session, session.begin():
                await session.execute(
                    text(
                        "UPDATE calls SET updated_at = now() - interval '30 minutes' WHERE id = :id"
                    ),
                    {"id": cid},
                )
            r2 = await recover_stuck_calls(factory, timeout_min=10, enqueue=False)
            after2 = await snap(cid)
            rows.append([f"{state} (30 dk önce)", after1, after2, f"{r1} / {r2}"])
    finally:
        await engine.dispose()
    print(
        md_table(["Başlangıç", "1. tarama sonrası", "2. tarama sonrası / istek", "Sayaçlar"], rows)
    )
    return 0


# --- Giriş ------------------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("batch", help="çalışan API'ye toplu çağrı yükle ve ölç")
    b.add_argument("--base-url", default="http://localhost:8100")
    b.add_argument("--service-key", default=None, help="verilmezse .env'deki SERVICE_API_KEY")
    b.add_argument("--text", type=int, default=30, help="metinle yüklenecek çağrı sayısı")
    b.add_argument("--audio", type=int, default=0, help="sesle yüklenecek çağrı sayısı")
    b.add_argument("--audio-dir", default=None, help="call_001.wav ... içeren klasör")
    b.add_argument("--bozuk-ses", action="store_true", help="bir de bozuk ses dosyası yükle")
    b.add_argument("--parallel", type=int, default=8, help="aynı anda hatta olan çağrı sayısı")
    b.add_argument("--timeout", type=float, default=900, help="çağrı başına en çok bekleme (sn)")
    b.add_argument("--poll", type=float, default=1.0)
    b.add_argument("--out", default=None)

    s = sub.add_parser("senaryo", help="hata senaryoları (sahte sunucu + gerçek sağlayıcı)")
    s.add_argument("--only", default=None, help="virgülle senaryo anahtarları")
    s.add_argument("--ortak-db", action="store_true", help="ortak veritabanına yazmaya izin ver")
    s.add_argument("--out", default=None)

    k = sub.add_parser("kota", help="gerçek sağlayıcıda kota sondası")
    k.add_argument("--seconds", type=int, default=90)
    k.add_argument("--concurrency", type=int, default=4)
    k.add_argument("--gap", type=float, default=0.0, help="istekler arası bekleme (sn)")
    k.add_argument("--stop-on-429", action="store_true")

    r = sub.add_parser("kurtarma", help="takılı çağrı kurtarma benzetimi")
    r.add_argument("--ortak-db", action="store_true")
    return p


def main() -> int:
    # Windows konsolunda (cp1254) Türkçe/ok karakterleri çökmesin.
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    args = build_parser().parse_args()
    handlers = {
        "batch": cmd_batch,
        "senaryo": cmd_senaryo,
        "kota": cmd_kota,
        "kurtarma": cmd_kurtarma,
    }
    return asyncio.run(handlers[args.cmd](args))


if __name__ == "__main__":
    sys.exit(main())
