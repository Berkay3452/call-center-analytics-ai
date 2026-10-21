# =============================================================
# 1. Aşama: Builder — Bağımlılıkları uv ile sanal ortama kurar
# =============================================================
FROM ghcr.io/astral-sh/uv:0.5.29 AS uv_bin
FROM python:3.12-slim-bookworm AS builder

# uv ikili dosyalarını builder aşamasına kopyala
COPY --from=uv_bin /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Katman önbelleğinden yararlanmak için bağımlılık dosyalarını kopyala
COPY pyproject.toml uv.lock ./

# Üretim ortamı bağımlılıklarını (.venv) dev araçları olmadan kur
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev --extra ai --extra stt

# =============================================================
# 2. Aşama: Runner — Çalışma zamanı imajı (API & Celery Worker)
# =============================================================
FROM python:3.12-slim-bookworm AS runner

# Sağlık kontrolü için curl, ses işleme ve STT için ffmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ffmpeg \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Güvenlik için kök olmayan kullanıcı ve grup (appuser:appgroup)
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /bin/bash -m appuser

WORKDIR /app

# Builder aşamasından hazır sanal ortamı kopyala
COPY --from=builder /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="/app"

# Uygulama kodlarını, migration'ları ve betikleri kopyala
COPY app/ /app/app/
COPY migrations/ /app/migrations/
COPY alembic.ini /app/alembic.ini
COPY scripts/ /app/scripts/
COPY pyproject.toml /app/pyproject.toml

# Depolama, log ve sentetik veri dizinlerini oluştur, izinleri ver
RUN mkdir -p /app/storage/logs /app/storage/audio /app/storage/models /data/synthetic && \
    chown -R appuser:appgroup /app /data

USER appuser

EXPOSE 8000

# Varsayılan komut: FastAPI API sunucusu
# Celery worker veya init servisi için docker-compose command ile ezilebilir.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
