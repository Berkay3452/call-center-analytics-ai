"""Geliştirme başlatıcısı: backend'i tek komutla ayağa kaldırır.

    uv run python -m scripts.dev

Sırayla (zaten hazır olanı atlayarak):
1. `.env` yoksa `.env.example`'dan oluşturur; eksik LLM anahtarını uyarır.
2. Docker Desktop kapalıysa açar, hazır olana kadar bekler.
3. `docker compose up -d`: PostgreSQL, Redis ve embedding servisi (bge-m3).
4. Migration (`alembic upgrade head`).
5. Seed ses dosyaları yoksa üretir (Piper); veritabanı boşsa (veya ses yeni üretildiyse) seed'ler.
6. Vektörü olmayan RAG parçalarını indeksler.
7. Celery işçisini arka planda açar (günlüğü `storage/logs/celery.log`).
8. API'yi (`uvicorn --reload`) ön planda açar; Ctrl+C hepsini kapatır.

Frontend ayrı terminalde: `cd frontend && npm run dev`.

Yalnızca geliştirme içindir: üretimde API bunların hiçbirini yapmaz.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent
COMPOSE_FILE = REPO_DIR / "infra" / "docker-compose.yml"
LOG_DIR = BACKEND_DIR / "storage" / "logs"
API_PORT = 8000

_DOCKER_BIN_DIRS = [r"C:\Program Files\Docker\Docker\resources\bin"]


def docker_desktop_candidates(env: Mapping[str, str] | None = None) -> list[str]:
    """Docker Desktop'ın olası kurulum yolları (kullanıcıya özel kurulum dahil)."""
    source: Mapping[str, str] = os.environ if env is None else env
    paths: list[str] = []
    local = source.get("LOCALAPPDATA")
    if local:  # "yalnızca bu kullanıcı için" kurulum
        paths.append(str(Path(local) / "Programs" / "DockerDesktop" / "Docker Desktop.exe"))
    program_files = source.get("ProgramFiles", r"C:\Program Files")
    paths.append(str(Path(program_files) / "Docker" / "Docker" / "Docker Desktop.exe"))
    paths.append(r"D:\Docker\Docker Desktop.exe")
    return paths


# --- Küçük yardımcılar --------------------------------------------------------------------------


def step(message: str) -> None:
    print(f"\n▶ {message}", flush=True)


def info(message: str) -> None:
    print(f"  {message}", flush=True)


def warn(message: str) -> None:
    print(f"  ⚠ {message}", flush=True)


def fail(message: str) -> None:
    print(f"\n✖ {message}", file=sys.stderr, flush=True)
    sys.exit(1)


def wait_until(
    check: Callable[[], bool],
    *,
    timeout: float,
    interval: float = 2.0,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> bool:
    """`check` doğru dönene kadar bekler; süre dolarsa False."""
    deadline = clock() + timeout
    while True:
        if check():
            return True
        if clock() >= deadline:
            return False
        sleep(interval)


def port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def http_ok(url: str, timeout: float = 3.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return bool(200 <= resp.status < 300)
    except (urllib.error.URLError, OSError, ValueError):
        return False


def redis_ok(host: str = "127.0.0.1", port: int = 6379) -> bool:
    try:
        with socket.create_connection((host, port), timeout=2) as s:
            s.sendall(b"PING\r\n")
            return s.recv(16).startswith(b"+PONG")
    except OSError:
        return False


def run(cmd: list[str], *, quiet: bool = False) -> int:
    kwargs: dict[str, object] = {"cwd": BACKEND_DIR}
    if quiet:
        kwargs.update(stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return subprocess.run(cmd, check=False, **kwargs).returncode  # type: ignore[call-overload]


def kill_tree(proc: subprocess.Popen[bytes] | subprocess.Popen[str]) -> None:
    """Süreci ve alt süreçlerini kapatır (Windows'ta `taskkill /T`)."""
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        proc.terminate()


# --- Ortam ----------------------------------------------------------------------------------------


def ensure_env_file(backend_dir: Path = BACKEND_DIR) -> bool:
    """`.env` yoksa `.env.example`'dan oluşturur; oluşturulduysa True."""
    env = backend_dir / ".env"
    if env.exists():
        return False
    example = backend_dir / ".env.example"
    if not example.exists():
        fail(".env ve .env.example bulunamadı.")
    shutil.copyfile(example, env)
    return True


def find_docker() -> str | None:
    found = shutil.which("docker")
    if found:
        return found
    for directory in _DOCKER_BIN_DIRS:
        candidate = Path(directory) / ("docker.exe" if os.name == "nt" else "docker")
        if candidate.exists():
            return str(candidate)
    return None


def compose_command(docker: str, *, rag: bool) -> list[str]:
    cmd = [docker, "compose", "-f", str(COMPOSE_FILE)]
    if rag:
        cmd += ["--profile", "rag"]
    return [*cmd, "up", "-d"]


def ensure_docker() -> str:
    docker = find_docker()
    if docker is None:
        fail("Docker bulunamadı. Docker Desktop'ı kurun (docs/calistirma.md).")
    assert docker is not None
    if run([docker, "info"], quiet=True) == 0:
        info("Docker hazır.")
        return docker
    desktop = next((p for p in docker_desktop_candidates() if Path(p).exists()), None)
    if desktop is None or os.name != "nt":
        fail("Docker çalışmıyor. Docker Desktop'ı açın ve komutu yeniden çalıştırın.")
    info("Docker Desktop açılıyor, hazır olması bekleniyor (en fazla 4 dk)...")
    subprocess.Popen([str(desktop)])
    if not wait_until(lambda: run([docker, "info"], quiet=True) == 0, timeout=240, interval=5):
        fail("Docker Desktop zamanında hazır olmadı.")
    info("Docker hazır.")
    return docker


# --- Veritabanı -----------------------------------------------------------------------------------


async def _fetchval(sql: str) -> int | None:
    import asyncpg

    from app.core.config import get_settings
    from scripts.seed.loader import _asyncpg_dsn

    conn = await asyncpg.connect(_asyncpg_dsn(get_settings().database_url), statement_cache_size=0)
    try:
        value = await conn.fetchval(sql)
        return int(value) if value is not None else None
    finally:
        await conn.close()


def db_value(sql: str) -> int | None:
    """Tek değerli sorgu; veritabanına ulaşılamaz veya tablo yoksa None."""
    try:
        return asyncio.run(_fetchval(sql))
    except Exception:
        return None


def db_ready() -> bool:
    return db_value("SELECT 1") == 1


# --- Adımlar --------------------------------------------------------------------------------------


def start_infrastructure(docker: str, *, rag: bool) -> None:
    step("Altyapı (PostgreSQL, Redis" + (", embedding" if rag else "") + ")")
    if run(compose_command(docker, rag=rag)) != 0:
        fail("`docker compose up` başarısız.")
    if not wait_until(db_ready, timeout=90):
        fail("PostgreSQL hazır olmadı (localhost:5433).")
    info("PostgreSQL hazır.")
    if not wait_until(redis_ok, timeout=60):
        fail("Redis hazır olmadı (localhost:6379).")
    info("Redis hazır.")


def wait_embeddings() -> bool:
    from app.core.config import get_settings

    settings = get_settings()
    if settings.embedding_provider != "tei":
        return True
    info("Embedding servisi bekleniyor (ilk açılışta model iner, birkaç dakika sürebilir)...")
    ok = wait_until(lambda: http_ok(f"{settings.tei_url}/health"), timeout=600, interval=5)
    if ok:
        info("Embedding servisi hazır.")
    else:
        warn("Embedding servisi hazır olmadı; Miço AI geçmiş/öneri araması çalışmayabilir.")
    return ok


def migrate() -> None:
    step("Veritabanı şeması (alembic)")
    if run([sys.executable, "-m", "alembic", "upgrade", "head"]) != 0:
        fail("Migration başarısız.")


def seed_audio_missing() -> bool:
    from app.core.config import get_settings
    from app.services.audio_ingest import storage_dir

    return not (storage_dir(get_settings()) / "seed" / "call_001.wav").exists()


def prepare_data(*, audio: bool) -> None:
    step("Örnek veri")
    audio_generated = False
    if audio and seed_audio_missing():
        info("Seed ses dosyaları yok, üretiliyor (~90 sn, ilk seferde ~60 MB model iner)...")
        cmd = ["uv", "run", "--with", "piper-tts", "python", "-m", "scripts.generate_audio"]
        if run(cmd) == 0:
            audio_generated = True
        else:
            warn("Ses üretilemedi; çağrı detayında oynatıcı seed çağrılarında 'ses yok' gösterir.")
    calls = db_value("SELECT count(*) FROM calls")
    if not calls or audio_generated:
        info("Seed yükleniyor...")
        if run([sys.executable, "-m", "scripts.seed"]) != 0:
            fail("Seed başarısız.")
    else:
        info(f"Veritabanında {calls} çağrı var, seed atlandı.")


def index_rag(*, embeddings_ready: bool) -> None:
    pending = db_value("SELECT count(*) FROM rag_chunks WHERE embedding IS NULL")
    if not pending:
        return
    step("Miço AI arama indeksi")
    if not embeddings_ready:
        warn(f"{pending} parça indekslenemedi (embedding servisi hazır değil).")
        return
    info(f"{pending} parça vektörleniyor...")
    if run([sys.executable, "-m", "scripts.rag_index"]) != 0:
        warn("İndeksleme başarısız; sonra `uv run python -m scripts.rag_index` ile deneyin.")


def start_celery() -> subprocess.Popen[bytes]:
    step("Analiz işçisi (Celery)")
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / "celery.log"
    schedule_path = LOG_DIR / "celerybeat-schedule"
    log = open(log_path, "ab")  # noqa: SIM115 - süreç boyunca açık kalır
    cmd = [
        sys.executable, "-m", "celery", "-A", "app.workers.celery_app", "worker",
        "-B", "-s", str(schedule_path),
        "-Q", "default,stt,analysis,index", "--pool=solo", "-l", "info",
    ]  # fmt: skip
    proc = subprocess.Popen(cmd, cwd=BACKEND_DIR, stdout=log, stderr=subprocess.STDOUT)
    info(f"Celery arka planda çalışıyor (günlük: {log_path}).")
    return proc


def preflight_warnings() -> None:
    from app.core.config import get_settings

    settings = get_settings()
    if not settings.llm_api_key or not settings.llm_api_key.get_secret_value():
        warn("LLM_API_KEY boş (backend/.env): çağrı analizi ve Miço AI'nın LLM adımları çalışmaz.")


def banner() -> None:
    print(
        "\n" + "─" * 64
        + "\n  Backend hazır:   http://127.0.0.1:8000   (API belgeleri: /docs)"
        + "\n  Frontend için:   ayrı terminalde  cd frontend ; npm run dev"
        + "\n  Uygulama:        http://localhost:3000"
        + "\n  Durdurmak için Ctrl+C (API ve Celery birlikte kapanır)"
        + "\n" + "─" * 64 + "\n",
        flush=True,
    )  # fmt: skip


# --- Ana akış -------------------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backend geliştirme ortamını tek komutla açar.")
    parser.add_argument("--no-rag", action="store_true", help="Embedding servisini (bge-m3) açma.")
    parser.add_argument("--no-audio", action="store_true", help="Seed seslerini üretme.")
    parser.add_argument("--no-celery", action="store_true", help="Celery işçisini açma.")
    parser.add_argument(
        "--skip-docker", action="store_true", help="Docker adımını atla (altyapı hazır)."
    )
    parser.add_argument("--reset-db", action="store_true", help="Veritabanını sıfırdan seed'le.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    os.chdir(BACKEND_DIR)
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))

    step("Hazırlık")
    if port_in_use(API_PORT):
        fail(f"{API_PORT} portu dolu: başka bir API çalışıyor. Onu kapatıp yeniden deneyin.")
    if ensure_env_file():
        info(
            ".env oluşturuldu (.env.example'dan). SERVICE_API_KEY ve LLM_API_KEY değerlerini girin."
        )
    preflight_warnings()

    embeddings_ready = False
    if not args.skip_docker:
        docker = ensure_docker()
        start_infrastructure(docker, rag=not args.no_rag)
        if not args.no_rag:
            embeddings_ready = wait_embeddings()
    migrate()
    if args.reset_db:
        step("Veritabanı sıfırlanıyor")
        if run([sys.executable, "-m", "scripts.seed", "--reset"]) != 0:
            fail("Seed başarısız.")
    else:
        prepare_data(audio=not args.no_audio)
    if not args.no_rag:
        index_rag(embeddings_ready=embeddings_ready)

    celery = None if args.no_celery else start_celery()
    banner()
    api = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--reload", "--port", str(API_PORT)],
        cwd=BACKEND_DIR,
    )
    try:
        api.wait()
    except KeyboardInterrupt:
        pass
    finally:
        print("\nKapatılıyor...", flush=True)
        kill_tree(api)
        if celery is not None:
            kill_tree(celery)


if __name__ == "__main__":
    main()
