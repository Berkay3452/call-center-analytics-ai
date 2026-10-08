# Backend (FastAPI)

Çağrı merkezi analitiği sisteminin API'si ve arka plan işçileri. Mimari için repo kökündeki `Sistem_mimarisi_v1.md` dosyasına bakın.

## Gereksinimler

- [uv](https://docs.astral.sh/uv/) (Python sürümünü ve sanal ortamı uv yönetir; sistem Python'u gerekmez)
- Docker Desktop (yerel PostgreSQL + Redis için)

## Kurulum

Komutlar `backend/` klasöründe çalıştırılır.

1. Python 3.12'yi ve bağımlılıkları `.venv` içine kurun: `uv sync --extra ai`
2. Ortam dosyasını oluşturun: `.env.example` dosyasını `.env` olarak kopyalayıp doldurun.
3. Yerel veritabanı ve Redis'i başlatın (repo kökünden): `docker compose -f infra/docker-compose.yml up -d`

STT bağımlılıkları (torch, faster-whisper, pyannote) büyüktür ve donanım kararı netleşince kurulacaktır: `uv sync --extra ai --extra stt`

## Çalıştırma

| Ne | Komut |
|----|-------|
| API (geliştirme) | `uv run uvicorn app.main:app --reload` |
| API dokümantasyonu | http://localhost:8000/docs |
| Celery işçisi (Windows) | `uv run celery -A app.workers.celery_app worker -Q default,analysis,index --pool=solo -l info` |
| Testler | `uv run pytest` |
| Lint + format | `uv run ruff check .` ve `uv run ruff format .` |
| Tip kontrolü | `uv run mypy app tests` |

Supabase kurulmadan `/api/v1` uçlarını denemek için `.env` içinde `AUTH_DEV_BYPASS=true` yapın (yalnızca `APP_ENV=local`).

## Uç Noktalar

| Yol | Açıklama |
|-----|----------|
| `GET /health` | Süreç ayakta mı (canlılık) |
| `GET /health/ready` | Veritabanı ve Redis erişilebilir mi (hazır olma; değilse 503) |
| `GET /api/v1/me` | Oturumdaki kullanıcı (Supabase JWT) |

## Klasör Yapısı

| Klasör | İçerik |
|--------|--------|
| `app/core` | Ayarlar, loglama, hata yönetimi, JWT doğrulama, istek kimliği ara katmanı |
| `app/api` | Route'lar ve bağımlılıklar (oturum, kullanıcı, rol) |
| `app/db` | Async SQLAlchemy motoru, oturumlar, model tabanı (şema Supabase migration'larından gelir) |
| `app/schemas` | API istek/yanıt şemaları |
| `app/services` | İş mantığı |
| `app/workers` | Celery uygulaması ve kuyruklar (stt, analysis, index) |
| `app/llm` | Ücretsiz, OpenAI-uyumlu LLM sağlayıcıları için istemci fabrikası |
| `app/agents` | Agent sözleşmesi (`base.py`), LangGraph orkestratörü (`orchestrator.py`), varsayılan akış (`registry.py`); agent'lar buraya gelecek |
| `app/stt` | STT sağlayıcı sözleşmesi |
| `app/rag` | Embedding sözleşmesi; RAG bileşenleri buraya gelecek |
| `tests` | Testler (gerçek veritabanı/Redis/LLM gerektirmez) |

## Kurallar

- Kod yorumları Türkçe; değişken, fonksiyon ve tablo adları İngilizce.
- Route'lar iş mantığı içermez; servisler HTTP bilmez.
- Veritabanı şeması yalnızca `supabase/migrations` ile değişir.
- Gizli anahtarlar `.env`'de durur ve asla commit edilmez.
