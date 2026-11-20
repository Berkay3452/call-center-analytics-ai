"""Kara kutu QA turu: ÇALIŞAN bir API'ye dışarıdan saldırı denemeleri (#320, #338).

pytest paketinin (`tests/security/`) tekrarı değildir: orada sahte bağımlılıklarla uygulama
içeriden denenir; burada gerçek sunucuya, gerçek HTTP ile, bir saldırgan/QA mühendisi gibi
gidilir. Her deneme "beklenen davranış" ile karşılaştırılır; uyuşmayan satır `FAIL` yazar.

    python -m scripts.qa_kara_kutu --base-url http://127.0.0.1:18765 --spec openapi.json
    python -m scripts.qa_kara_kutu --base-url ... --hiz-siniri   # IP'yi 60 sn kilitler

Anahtarlar ortam değişkeninden okunur (`SERVICE_API_KEY`, `USER_SIGNING_KEY`); asla argüman
olarak verilmez. **Üretim verisi olan bir ortama karşı çalıştırma**: yazma uçlarına (çağrı
yükleme, CRM) sentetik kayıt bırakır. Yalnızca sentetik/izole veritabanında kullanın.
Önerilen: ayrı veritabanı + sahte LLM (`scripts/fake_llm.py`) + `APP_ENV=prod`.

Kapsam: (1) tüm uçlarda kimliksiz/sahte/eski imza → 401, (2) rol yükseltme → 403, (3) sahip
izolasyonu, (4) 500'e yol açan girdiler (NUL karakteri, sınır dışı tarih/sayı), (5) ses
yükleme suistimali, (6) başlıklar ve CORS, (7) SSE yetkisi ve izleyici sınırı.
Şema tabanlı fuzzing için bkz. docs/qa_kara_kutu_raporu.md (schemathesis).
"""

import argparse
import hashlib
import hmac
import io
import json
import os
import random
import struct
import sys
import threading
import time
import uuid
import wave
from collections.abc import Callable
from typing import Any

import httpx

Result = tuple[str, bool, str]


class Qa:
    def __init__(self, base_url: str, service_key: str, signing_key: str) -> None:
        self.http = httpx.Client(base_url=base_url, timeout=30)
        self.base_url = base_url
        self.sk = service_key
        self.signing = signing_key
        self.results: list[Result] = []

    # --- kimlik yardımcıları -------------------------------------------------------------
    def sig(
        self, uid: str, role: str | None = None, key: str | None = None, ts: int | None = None
    ) -> str:
        stamp = int(time.time()) if ts is None else ts
        clean = (role or "").strip().lower()
        msg = f"{uid}.{clean}.{stamp}" if clean else f"{uid}.{stamp}"
        mac = hmac.new((key or self.signing).encode(), msg.encode(), hashlib.sha256).hexdigest()
        return f"{stamp}.{mac}"

    def hdr(self, uid: str | None = None, role: str | None = None) -> dict[str, str]:
        h = {"X-Service-Key": self.sk}
        if uid:
            h["X-User-Id"] = uid
            h["X-User-Signature"] = self.sig(uid, role)
            if role:
                h["X-User-Role"] = role
        return h

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        self.results.append((name, ok, detail))
        print(("PASS " if ok else "FAIL ") + name + ("" if ok or not detail else f" :: {detail}"))

    def summary(self) -> int:
        failed = [r for r in self.results if not r[1]]
        print(f"\nÖZET: {len(self.results) - len(failed)}/{len(self.results)} geçti")
        return 1 if failed else 0


def wav_bytes(seed: int, seconds: int = 1) -> bytes:
    rnd = random.Random(seed)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(
            b"".join(struct.pack("<h", rnd.randint(-3000, 3000)) for _ in range(8000 * seconds))
        )
    return buf.getvalue()


def load_operations(spec: dict[str, Any]) -> list[tuple[str, str]]:
    return [(m.upper(), p) for p, v in spec["paths"].items() for m in v if m != "parameters"]


def fill(path: str, call_id: str) -> str:
    return (
        path.replace("{call_id}", call_id)
        .replace("{order_id}", str(uuid.uuid4()))
        .replace("{session_id}", str(uuid.uuid4()))
        .replace("{id}", str(uuid.uuid4()))
    )


# --- 1-3: kimlik, rol, sahip izolasyonu -------------------------------------------------------


def auth_matrix(qa: Qa, ops: list[tuple[str, str]], owner: str, other: str, call_id: str) -> None:
    protected = [(m, p) for m, p in ops if not p.startswith("/health")]
    bad: list[tuple[Any, ...]] = []
    anonymous = {
        "anahtarsiz": {},
        "yanlis": {"X-Service-Key": "x" * 40},
        "uzatilmis": {"X-Service-Key": qa.sk + "x"},
        "kisaltilmis": {"X-Service-Key": qa.sk[:-1]},
    }
    for m, p in protected:
        for label, h in anonymous.items():
            r = qa.http.request(m, fill(p, call_id), headers=h)
            if r.status_code != 401:
                bad.append((m, p, label, r.status_code))
    qa.check("tüm uçlar anahtarsız/yanlış anahtarda 401", not bad, str(bad[:5]))

    bad = []
    forged = {
        "imzasiz": {"X-Service-Key": qa.sk, "X-User-Id": owner},
        "yanlis_imza": {
            "X-Service-Key": qa.sk,
            "X-User-Id": owner,
            "X-User-Signature": qa.sig(owner, key="z" * 40),
        },
        "eski_imza": {
            "X-Service-Key": qa.sk,
            "X-User-Id": owner,
            "X-User-Signature": qa.sig(owner, ts=int(time.time()) - 3600),
        },
        "baskasinin_imzasi": {
            "X-Service-Key": qa.sk,
            "X-User-Id": owner,
            "X-User-Signature": qa.sig(other),
        },
        "servis_anahtariyla_imza": {
            "X-Service-Key": qa.sk,
            "X-User-Id": owner,
            "X-User-Signature": qa.sig(owner, key=qa.sk),
        },
    }
    for m, p in protected:
        for label, h in forged.items():
            r = qa.http.request(m, fill(p, call_id), headers=h)
            if r.status_code != 401:
                bad.append((m, p, label, r.status_code))
    qa.check("tüm uçlar sahte/eski/yanlış imzada 401", not bad, str(bad[:5]))

    owner_paths = ("/api/v1/me", "/api/v1/me/owner", "/assistant/", "/chat/")
    bad = []
    for m, p in protected:
        if any(s in p for s in owner_paths):
            continue
        r = qa.http.request(m, fill(p, call_id), headers=qa.hdr(owner, "owner"))
        if r.status_code != 403:
            bad.append((m, p, r.status_code))
    qa.check("sahip rolü yönetici uçlarında 403", not bad, str(bad[:6]))

    bad = []
    for p in ("/api/v1/calls", "/api/v1/customers", "/api/v1/audit-log", "/api/v1/crm"):
        forged_role = qa.hdr(owner, "owner")
        forged_role["X-User-Role"] = "admin"  # imzadan sonra rol başlığını değiştir
        if qa.http.request("GET", p, headers=forged_role).status_code == 200:
            bad.append((p, "rol başlığı imzadan sonra değiştirildi"))
        if qa.http.request("GET", p, headers=qa.hdr(owner)).status_code == 200:
            bad.append((p, "rolsüz imza yönetici sayıldı"))
    qa.check("imzalı sahip rolünü admin'e yükseltemez", not bad, str(bad))

    r = qa.http.post(
        "/api/v1/chat/messages",
        headers={**qa.hdr(other, "owner"), "Content-Type": "application/json"},
        content=json.dumps({"question": "merhaba", "session_id": str(uuid.uuid4())}),
    )
    qa.check("var olmayan oturuma mesaj: veri sızmadan hata", r.status_code in (200, 404))


def ownership(qa: Qa, owner: str, other: str) -> None:
    j = {"Content-Type": "application/json"}
    qa.http.post(
        "/api/v1/chat/messages",
        headers={**qa.hdr(owner, "owner"), **j},
        content=json.dumps({"question": "Merhaba"}),
    )
    mine = qa.http.get("/api/v1/chat/sessions", headers=qa.hdr(owner, "owner")).json()
    items = mine["items"] if isinstance(mine, dict) else mine
    if not items:
        qa.check("sahip izolasyonu: oturum oluşturulamadı", False, "oturum yok")
        return
    sid = items[0]["id"]
    for m in ("GET", "DELETE"):
        r = qa.http.request(m, f"/api/v1/chat/sessions/{sid}", headers=qa.hdr(other, "owner"))
        qa.check(f"başkası oturumu {m} edemez", r.status_code in (403, 404), str(r.status_code))
    miss = qa.http.get(f"/api/v1/chat/sessions/{uuid.uuid4()}", headers=qa.hdr(other, "owner"))
    foreign = qa.http.get(f"/api/v1/chat/sessions/{sid}", headers=qa.hdr(other, "owner"))
    qa.check(
        "var olmayan ve başkasının oturumu aynı yanıtı verir",
        miss.status_code == foreign.status_code,
        f"{miss.status_code} vs {foreign.status_code}",
    )
    qa.http.delete(f"/api/v1/chat/sessions/{sid}", headers=qa.hdr(owner, "owner"))


# --- 4: 500'e yol açan girdiler ----------------------------------------------------------------


def server_errors(qa: Qa, owner: str, call_id: str) -> None:
    failures: list[tuple[str, int]] = []
    admin = qa.hdr()
    j = {"Content-Type": "application/json"}

    def hit(label: str, r: httpx.Response) -> None:
        in_stream = r.status_code == 200 and "internal_error" in r.text[:2000]
        if r.status_code >= 500 or in_stream:
            failures.append((label, r.status_code))

    lists = ["/api/v1/analytics/summary", "/api/v1/calls", "/api/v1/crm", "/api/v1/service-orders"]
    lists += ["/api/v1/customers", "/api/v1/audit-log"]
    extreme = ("0001-01-01", "9999-12-31", "0001-01-01T00:00:00Z", "9999-12-31T23:59:59Z")
    for p in lists:
        for k in ("date_from", "date_to", "since", "until"):
            for v in extreme:
                hit(f"{p}?{k}={v}", qa.http.get(p, headers=admin, params={k: v}))
        for k in ("q", "marina", "status"):
            hit(f"{p}?{k}=NUL", qa.http.get(p, headers=admin, params={k: "a\x00b"}))
        for k in ("page", "page_size", "limit"):
            for v in ("99999999999999", "-1", "1e99"):
                hit(f"{p}?{k}={v}", qa.http.get(p, headers=admin, params={k: v}))

    def send(method: str, path: str, body: Any, h: dict[str, str]) -> httpx.Response:
        return qa.http.request(method, path, headers={**h, **j}, content=json.dumps(body))

    own = qa.hdr(owner, "owner")
    for path in ("/api/v1/assistant/chat", "/api/v1/chat/messages", "/api/v1/chat/messages/stream"):
        hit(f"{path} NUL", send("POST", path, {"question": "a\x00b"}, own))
    hit(
        "assistant history NUL",
        send(
            "POST",
            "/api/v1/assistant/chat",
            {"question": "x", "history": [{"role": "user", "content": "a\x00"}]},
            own,
        ),
    )
    base = {"started_at": "2026-11-20T10:00:00Z", "transcript": "Müşteri: merhaba"}
    for field, value in (
        ("customer_name", "a\x00"),
        ("marina", "a\x00"),
        ("duration_s", 540966033835368279617652654080),
        ("answer_delay_s", 2**31),
        ("transcript", "a\x00b"),
        ("started_at", "0001-01-01T00:00:00Z"),
        ("started_at", "9999-12-31T00:00:00Z"),
    ):
        hit(f"POST /calls {field}", send("POST", "/api/v1/calls", {**base, field: value}, admin))
    segs = [{"speaker": "rep", "text": "a\x00", "start_ms": 2**40, "end_ms": 1}]
    hit(
        "POST /calls segments",
        send(
            "POST", "/api/v1/calls", {"started_at": "2026-11-20T10:00:00Z", "segments": segs}, admin
        ),
    )
    for act in ("approve", "reject"):
        for k in ("note", "location", "problem", "potential_job"):
            hit(
                f"crm {act} {k} NUL",
                send("POST", f"/api/v1/crm/{call_id}/{act}", {k: "a\x00"}, admin),
            )
    for k, v in (
        ("customer_name", "a\x00b"),
        ("duration_s", "9" * 30),
        ("customer_name", "A" * 5000),
    ):
        r = qa.http.post(
            "/api/v1/calls/audio",
            headers=admin,
            files={"file": ("a.wav", wav_bytes(99), "audio/wav")},
            data={"started_at": "2026-11-20T10:00:00Z", k: v},
        )
        hit(f"audio {k}", r)
    qa.check(
        "500 üreten girdi yok (NUL, sınır dışı tarih/sayı, uzun ad)",
        not failures,
        str(failures[:8]),
    )


# --- 5-6: yükleme, başlıklar, CORS -------------------------------------------------------------


def uploads(qa: Qa) -> None:
    form = {"started_at": "2026-11-20T10:00:00Z"}

    def up(name: str, data: bytes, ctype: str = "audio/wav") -> int:
        r = qa.http.post(
            "/api/v1/calls/audio",
            headers=qa.hdr(),
            files={"file": (name, data, ctype)},
            data=form,
        )
        return r.status_code

    seed = int(time.time())
    qa.check("HTML içerikli .wav → 415", up("x.wav", b"<script>1</script>" * 50) == 415)
    qa.check(
        "exe içerikli .wav → 415",
        up("x.wav", b"MZ" + b"\x00" * 500, "application/octet-stream") == 415,
    )
    qa.check("boş dosya → 415", up("e.wav", b"") == 415)
    qa.check("RIFF başlıklı çöp → 415", up("x.wav", b"RIFF" + b"\xff" * 1000) == 415)
    qa.check("izin verilmeyen uzantı (.svg) → 415", up("x.svg", b"<svg/>", "image/svg+xml") == 415)
    big = qa.http.post(
        "/api/v1/calls/audio",
        headers=qa.hdr(),
        files={"file": ("big.wav", b"RIFF" + b"\x00" * (26 * 1024 * 1024), "audio/wav")},
        data=form,
    )
    qa.check("26 MB ses → 413", big.status_code == 413, str(big.status_code))
    audio = wav_bytes(seed)
    first = up("../../etc/a.wav", audio)
    qa.check("yol gezinmeli dosya adı güvenle saklanır (202)", first == 202, str(first))
    qa.check("aynı ses ikinci kez → 409", up("a.wav", audio) == 409)
    huge = qa.http.post(
        "/api/v1/assistant/chat",
        headers={**qa.hdr(str(uuid.uuid4()), "owner"), "Content-Type": "application/json"},
        content=b'{"question":"' + b"A" * 300_000 + b'"}',
    )
    qa.check("300 KB JSON gövde → 413", huge.status_code == 413, str(huge.status_code))


def headers_and_cors(qa: Qa, allowed_origin: str) -> None:
    r = qa.http.get("/api/v1/me", headers=qa.hdr())
    h = {k.lower(): v for k, v in r.headers.items()}
    for name, expect in (
        ("x-content-type-options", "nosniff"),
        ("x-frame-options", "DENY"),
        ("referrer-policy", "no-referrer"),
        ("cache-control", "no-store"),
    ):
        qa.check(f"başlık {name}: {expect}", h.get(name) == expect, str(h.get(name)))
    for origin in ("http://evil.example", "null", allowed_origin + ".evil.com"):
        pre = qa.http.options(
            "/api/v1/me",
            headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
        )
        qa.check(
            f"CORS: yabancı kaynak {origin} reddedilir",
            pre.headers.get("access-control-allow-origin") is None,
            str(pre.headers.get("access-control-allow-origin")),
        )
    if qa.http.get("/openapi.json", headers=qa.hdr()).status_code == 200:
        print("INFO belge uçları açık (geliştirme modu); üretim kapalılığı denenmedi")
        return
    for path in ("/docs", "/redoc", "/openapi.json", "/.env", "/metrics"):
        code = qa.http.get(path, headers=qa.hdr()).status_code
        qa.check(f"{path} üretimde kapalı", code == 404, str(code))


# --- 7: SSE ------------------------------------------------------------------------------------


def sse(qa: Qa, owner: str, call_id: str) -> None:
    path = f"/api/v1/calls/{call_id}/transcript/stream"
    qa.check(
        "SSE: sahip rolü 403", qa.http.get(path, headers=qa.hdr(owner, "owner")).status_code == 403
    )
    qa.check("SSE: anahtarsız 401", qa.http.get(path).status_code == 401)
    qa.check(
        "SSE: var olmayan çağrı 404",
        qa.http.get(f"/api/v1/calls/{uuid.uuid4()}/transcript/stream", headers=qa.hdr()).status_code
        == 404,
    )
    qa.check(
        "ses dosyası: sahip rolü 403",
        qa.http.get(f"/api/v1/calls/{call_id}/audio", headers=qa.hdr(owner, "owner")).status_code
        == 403,
    )
    codes: list[Any] = []

    def viewer() -> None:
        try:
            with (
                httpx.Client(base_url=qa.base_url, timeout=20) as c,
                c.stream("GET", path, headers=qa.hdr()) as s,
            ):
                codes.append(s.status_code)
                started = time.time()
                for _ in s.iter_raw():
                    if time.time() - started > 5:
                        break
        except httpx.HTTPError as exc:
            codes.append(type(exc).__name__)

    threads = [threading.Thread(target=viewer) for _ in range(7)]
    for t in threads:
        t.start()
        time.sleep(0.4)
    for t in threads:
        t.join()
    qa.check(
        "SSE: bir çağrıda en fazla 5 eşzamanlı izleyici (fazlası 429)",
        429 in codes and codes.count(200) <= 5,
        str(codes),
    )


def rate_limit(qa: Qa) -> None:
    codes = [
        qa.http.get("/api/v1/me", headers={"X-Service-Key": f"yanlis{i}"}).status_code
        for i in range(14)
    ]
    qa.check(
        "10 hatalı anahtardan sonra 429", codes[-1] == 429 and 429 not in codes[:10], str(codes)
    )
    r = qa.http.get("/api/v1/me", headers={"X-Service-Key": "yanlis"})
    qa.check("429'da Retry-After var", bool(r.headers.get("retry-after")))


# --- 8: iş akışları (başarılı yol da çalışmalı) --------------------------------------------------


def workflows(qa: Qa) -> None:
    """Saldırı değil, mutlu yol: yetki/doğrulama sıkılaştırması gerçek işi bozmamalı."""
    pending = qa.http.get("/api/v1/crm", headers=qa.hdr(), params={"status": "bekliyor"}).json()
    if not pending["items"]:
        qa.check("iş akışları: bekleyen CRM kaydı yok (seed gerekli)", False)
        return
    call_id = pending["items"][0]["call_id"]
    customers = qa.http.get("/api/v1/customers", headers=qa.hdr()).json()
    target = next(c for c in customers if c["boats"])
    j = {"Content-Type": "application/json"}
    r = qa.http.put(
        f"/api/v1/calls/{call_id}/match",
        headers={**qa.hdr(), **j},
        content=json.dumps({"customer_id": target["id"], "boat_id": target["boats"][0]["id"]}),
    )
    qa.check(
        "elle eşleştirme 200 (eskiden 500)", r.status_code == 200, f"{r.status_code} {r.text[:80]}"
    )
    for state, code in (("approve", 200), ("reject", 200)):
        r = qa.http.post(
            f"/api/v1/crm/{call_id}/{state}",
            headers={**qa.hdr(), **j},
            content=json.dumps({"note": "QA turu"}),
        )
        qa.check(f"CRM {state} {code}", r.status_code == code, f"{r.status_code} {r.text[:80]}")
    created = qa.http.post(
        "/api/v1/calls",
        headers={**qa.hdr(), **j},
        content=json.dumps(
            {
                "started_at": "2026-11-20T10:00:00Z",
                "duration_s": 120,
                "customer_name": "QA Sentetik",
                "transcript": "Müşteri: Merhaba, teknemde arıza var.",
            }
        ),
    )
    qa.check("metinli çağrı oluşturma 202", created.status_code == 202, str(created.status_code))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--base-url", required=True)
    parser.add_argument(
        "--spec", required=True, help="OpenAPI JSON dosyası (prod'da /openapi.json kapalı)"
    )
    parser.add_argument("--origin", default="http://localhost:3000", help="izinli CORS kaynağı")
    parser.add_argument(
        "--hiz-siniri", action="store_true", help="IP'yi 60 sn kilitleyen 429 denemesi"
    )
    args = parser.parse_args(argv)
    service_key = os.environ.get("SERVICE_API_KEY", "")
    signing_key = os.environ.get("USER_SIGNING_KEY", "")
    if not service_key or not signing_key:
        print("SERVICE_API_KEY ve USER_SIGNING_KEY ortam değişkenleri gerekli.", file=sys.stderr)
        return 2
    with open(args.spec, encoding="utf-8") as fh:
        ops = load_operations(json.load(fh))
    qa = Qa(args.base_url, service_key, signing_key)
    customers = qa.http.get("/api/v1/customers", headers=qa.hdr()).json()
    calls = qa.http.get("/api/v1/calls", headers=qa.hdr(), params={"limit": 1}).json()["items"]
    if len(customers) < 2 or not calls:
        print("Seed verisi gerekli: en az 2 müşteri ve 1 çağrı.", file=sys.stderr)
        return 2
    owner, other, call_id = customers[0]["id"], customers[1]["id"], calls[0]["id"]
    sections: list[tuple[str, Callable[[], None]]] = [
        ("Kimlik, rol", lambda: auth_matrix(qa, ops, owner, other, call_id)),
        ("Sahip izolasyonu", lambda: ownership(qa, owner, other)),
        ("500 üreten girdiler", lambda: server_errors(qa, owner, call_id)),
        ("Ses yükleme ve gövde sınırı", lambda: uploads(qa)),
        ("Başlıklar ve CORS", lambda: headers_and_cors(qa, args.origin)),
        ("SSE", lambda: sse(qa, owner, call_id)),
        ("İş akışları", lambda: workflows(qa)),
    ]
    if args.hiz_siniri:
        sections.append(("Hız sınırı", lambda: rate_limit(qa)))
    for title, run in sections:
        print(f"\n== {title}")
        run()
    return qa.summary()


if __name__ == "__main__":
    sys.exit(main())
