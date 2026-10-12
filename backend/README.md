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
4. Veritabanı şemasını kurun: `uv run alembic upgrade head` (Supabase için `.env`'deki `DATABASE_URL`'i değiştirmeniz yeterli). Şema tasarımı: `docs/db_schema.md`; model değişince `uv run alembic revision --autogenerate -m "aciklama"` ile yeni migration üretip gözden geçirin.

STT bağımlılıkları (torch, faster-whisper, pyannote) büyüktür ve donanım kararı netleşince kurulacaktır: `uv sync --extra ai --extra stt`

### uv kullanmadan kurulum (requirements.txt)

`requirements.txt` ve `requirements-dev.txt`, `uv.lock` dosyasından üretilmiş **sabit sürümlü** listelerdir (Python 3.12 gerekir). `pip` ile kurulum:

```
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
```

- `requirements.txt`: uygulama ve `ai` ekstrası (FastAPI, Celery, SQLAlchemy, LangGraph, LangChain...).
- `requirements-dev.txt`: test ve kod kalitesi araçları (pytest, ruff, mypy).
- CI'daki **Bağımlılık sürümleri** kontrolü, `uv.lock` ile `pyproject.toml` ve bu iki dosyanın uyumunu her PR'da denetler; uyumsuzsa PR kırmızı olur.
- Bu dosyaları elle düzenlemeyin. Bağımlılık değişince `pyproject.toml` güncellenir, `uv lock` çalıştırılır ve dosyalar şu komutlarla yeniden üretilir:

```
uv export --frozen --no-hashes --no-emit-project --no-dev --extra ai -o requirements.txt
uv export --frozen --no-hashes --no-emit-project --only-dev -o requirements-dev.txt
```

## Çalıştırma

| Ne | Komut |
|----|-------|
| API (geliştirme) | `uv run uvicorn app.main:app --reload` |
| API dokümantasyonu | http://localhost:8000/docs |
| Celery işçisi (Windows) | `uv run celery -A app.workers.celery_app worker -Q default,analysis,index --pool=solo -l info` |
| Testler | `uv run pytest` |
| Lint + format | `uv run ruff check .` ve `uv run ruff format .` |
| Tip kontrolü | `uv run mypy app tests` |

Servis anahtarı kurulmadan `/api/v1` uçlarını denemek için `.env` içinde `AUTH_DEV_BYPASS=true` yapın (yalnızca `APP_ENV=local`).

## Sentetik veri üretimi ve veritabanı doldurma (seed)

Miço Usta sentetik kayıtlarını (`data/synthetic/*.json`) üretmek ve tüm sentetik veriyi (müşteriler, tekneler, ustalar, servis kayıtları, usta notları, giderler, abonelikler, RAG parçaları + 10 çağrı verisi) veritabanına yüklemek için önce `uv run alembic upgrade head` ile şemayı kurun, ardından `backend/` klasöründe:

```
uv run python -m scripts.seed                  # JSON dosyalarını üretir + veritabanını doldurur (idempotent)
uv run python -m scripts.seed --generate-only  # Veritabanına bağlanmadan yalnızca JSON dosyalarını üretir
uv run python -m scripts.seed --reset          # Tabloları TRUNCATE ile temizleyip sıfırdan doldurur
```

Script sabit tohum (`SEED = 42`, `Faker('tr_TR')`) kullanır; her çalıştırmada aynı veriyi üretir ve ikinci çalıştırmada `ON CONFLICT DO UPDATE` ile mevcut kayıtları bozmadan günceller.

## Agent'ları gerçek LLM ile değerlendirme

`.env`'de LLM ayarları doluyken (geçici seçim: Gemini, bkz. #13) agent'lar sentetik çağrılarda (`data/synthetic/`) çalıştırılıp doğru etiketlerle karşılaştırılır:

```
python -m scripts.evaluate                                 # 10 çağrının hepsi
python -m scripts.evaluate --calls call_001,call_004       # seçili çağrılar
python -m scripts.evaluate --fast <model> --smart <model>  # modeli .env'i değiştirmeden dene
```

Çıktı: alan bazında doğruluk tablosu, yanlış alanlar, süre ve token sayısı. Ücretsiz katman sınırları nedeniyle çağrılar sırayla işlenir.

## Uç Noktalar

| Yol | Açıklama |
|-----|----------|
| `GET /health` | Süreç ayakta mı (canlılık) |
| `GET /health/ready` | Veritabanı ve Redis erişilebilir mi (hazır olma; değilse 503) |
| `GET /api/v1/me` | Servis anahtarı doğrulaması (`X-Service-Key`, isteğe bağlı `X-User-Id`) |
| `GET /api/v1/me/owner` | Tekne sahibi kimliği doğrulaması (`X-Service-Key` + zorunlu `X-User-Id`) |

## Klasör Yapısı

| Klasör | İçerik |
|--------|--------|
| `app/core` | Ayarlar, loglama, hata yönetimi, servis anahtarı doğrulama, istek kimliği ara katmanı |
| `app/api` | Route'lar ve bağımlılıklar (oturum, servis anahtarı, kullanıcı kimliği) |
| `app/db` | Async SQLAlchemy motoru, oturumlar, model tabanı (şema Supabase migration'larından gelir) |
| `app/schemas` | API istek/yanıt şemaları |
| `app/services` | İş mantığı |
| `app/workers` | Celery uygulaması ve kuyruklar (stt, analysis, index) |
| `app/llm` | Ücretsiz, OpenAI-uyumlu LLM sağlayıcıları için istemci fabrikası |
| `app/agents` | Agent sözleşmesi (`base.py`), LLM agent tabanı (`llm_agent.py`), dört analiz agent'ı, prompt'lar (`prompts/`), alıntı doğrulama (`grounding.py`), LangGraph orkestratörü (`orchestrator.py`), varsayılan akış (`registry.py`) |
| `app/assistant` | Miço AI (Tekne Sahibi asistanı): planlayıcı, hazır araçlar, tekne karnesi araması, cevap üretimi, kaynak kontrolü; dışa açılan tek giriş `answer_question` (çağrı analizinden bağımsız) |
| `app/stt` | STT sağlayıcı sözleşmesi |
| `app/rag` | Embedding sözleşmesi; RAG bileşenleri buraya gelecek |
| `tests` | Testler (gerçek veritabanı/Redis/LLM gerektirmez) |

## Kurallar

- Kod yorumları Türkçe; değişken, fonksiyon ve tablo adları İngilizce.
- Route'lar iş mantığı içermez; servisler HTTP bilmez.
- Veritabanı şeması yalnızca `supabase/migrations` ile değişir.
- Gizli anahtarlar `.env`'de durur ve asla commit edilmez.
