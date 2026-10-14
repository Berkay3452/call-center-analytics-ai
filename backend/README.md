# Backend (FastAPI)

Çağrı merkezi analitiği sisteminin API'si ve arka plan işçileri. Mimari için repo kökündeki `Sistem_mimarisi_v1.md` dosyasına bakın.

> Tüm sistemi (backend + frontend) sıfırdan ayağa kaldırmak için önce [`docs/calistirma.md`](../docs/calistirma.md) rehberine bak.

## Gereksinimler

- [uv](https://docs.astral.sh/uv/) (Python sürümünü ve sanal ortamı uv yönetir; sistem Python'u gerekmez)
- Docker Desktop (yerel PostgreSQL + Redis için)

## Kurulum

Komutlar `backend/` klasöründe çalıştırılır.

1. Python 3.12'yi ve bağımlılıkları `.venv` içine kurun: `uv sync --extra ai`
2. Ortam dosyasını oluşturun: `.env.example` dosyasını `.env` olarak kopyalayıp doldurun.
3. Yerel veritabanı ve Redis'i başlatın (repo kökünden): `docker compose -f infra/docker-compose.yml up -d`
4. Veritabanı şemasını kurun: `uv run alembic upgrade head` (Supabase için `.env`'deki `DATABASE_URL`'i değiştirmeniz yeterli). Şema tasarımı: `docs/db_schema.md`; model değişince `uv run alembic revision --autogenerate -m "aciklama"` ile yeni migration üretip gözden geçirin.

STT (ses → metin, #15) için: `uv sync --extra ai --extra stt` (faster-whisper; CPU'da çalışır, torch gerekmez). Model ilk kullanımda indirilir (`small` ≈ 500 MB). Sağlayıcı `.env`'deki `STT_PROVIDER` ile seçilir:

| Sağlayıcı | Ne zaman |
|---|---|
| `faster_whisper` | Yerel, ücretsiz, ses dışarı çıkmaz. CPU'da `WHISPER_MODEL=small` (hız/doğruluk dengesi) veya `base` (hızlı) |
| `openai_compatible` | OpenAI uyumlu Whisper API'si (ör. Groq `whisper-large-v3`); hızlı ama ses üçüncü tarafa gider, `STT_API_KEY` gerekir |
| `stub` | STT kurmadan zinciri denemek için: ses dosyasının yanındaki `.txt` transkripti okur |

Konuşmacı ayrımı: santral kaydı stereo ise `STT_CHANNEL_LAYOUT=stereo_rep_left` (temsilci sol kanal) ile her kanal ayrı yazıya çevrilir. Mono kayıtta konuşmacılar ayrılamaz.

Sağlayıcıları karşılaştırma (doğruluk WER/CER ve hız RTF): `python -m scripts.stt_benchmark --audio <ses klasörü> --providers faster_whisper,openai_compatible`. Referans metin aynı adlı sentetik çağrıdan (`call_001.wav` → `data/synthetic/calls/call_001.json`) veya ses yanındaki `.txt`'den alınır.

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
| Celery işçisi (Windows) | `uv run celery -A app.workers.celery_app worker -Q default,stt,analysis,index --pool=solo -l info` |
| Testler | `uv run pytest` |
| Lint + format | `uv run ruff check .` ve `uv run ruff format .` |
| Tip kontrolü | `uv run mypy app tests` |

`X-User-Id` her zaman UUID olmalıdır (veritabanındaki `owner_id`). Canlıda `SERVICE_API_KEY` en az 32 karakter olmalıdır. Admin uçlarında rol ayrımını .NET uygulaması yapar; bu servis yalnızca servis anahtarını doğrular.

Servis anahtarı kurulmadan `/api/v1` uçlarını denemek için `.env` içinde `AUTH_DEV_BYPASS=true` yapın (yalnızca `APP_ENV=local`).

## Sentetik veri üretimi ve veritabanı doldurma (seed)

Miço Usta sentetik kayıtlarını (`data/synthetic/*.json`) üretmek ve tüm sentetik veriyi (müşteriler, tekneler, ustalar, servis kayıtları, usta notları, giderler, abonelikler, RAG parçaları + 30 çağrı verisi) veritabanına yüklemek için önce `uv run alembic upgrade head` ile şemayı kurun, ardından `backend/` klasöründe:

```
uv run python -m scripts.seed                  # JSON dosyalarını üretir + veritabanını doldurur (idempotent)
uv run python -m scripts.seed --generate-only  # Veritabanına bağlanmadan yalnızca JSON dosyalarını üretir
uv run python -m scripts.seed --reset          # Tabloları TRUNCATE ile temizleyip sıfırdan doldurur
```

Script sabit tohum (`SEED = 42`, `Faker('tr_TR')`) kullanır; her çalıştırmada aynı veriyi üretir ve ikinci çalıştırmada `ON CONFLICT DO UPDATE` ile mevcut kayıtları bozmadan günceller.

## Miço AI araması (RAG, #26)

Tekne karnesi (usta notları ve servis kayıtları) hibrit aranır: **vektör** (bge-m3) + **Türkçe tam metin**, sonuçlar RRF ile birleştirilir; her arama `owner_id` ile sınırlıdır. Embedding modeli Docker'da TEI servisiyle CPU'da çalışır (Python'a torch kurulmaz):

```
docker compose -f ../infra/docker-compose.yml --profile rag up -d   # ilk açılışta ~2,3 GB model iner
uv run python -m scripts.rag_index            # seed sonrası: vektörü olmayan parçaları doldurur
uv run python -m scripts.rag_eval             # 14 örnek soruda isabet@1, isabet@3, MRR
uv run python -m scripts.rag_eval --mode text # karşılaştırma: yalnızca tam metin (veya --mode vector)
```

Servis olmadan denemek için `EMBEDDING_PROVIDER=hash` (modelsiz, yalnızca kelime örtüşmesi; gerçek kalite ölçümü için kullanılmaz).

## Agent'ları gerçek LLM ile değerlendirme

`.env`'de LLM ayarları doluyken (NVIDIA Nemotron 3; Gemini yedek, bkz. #13; Nemotron için `LLM_DISABLE_THINKING=true`) agent'lar sentetik çağrılarda (`data/synthetic/`) çalıştırılıp doğru etiketlerle karşılaştırılır:

```
python -m scripts.evaluate                                 # çağrıların hepsi
python -m scripts.evaluate --split test                    # 20 çağrılık dokunulmaz test kümesi
python -m scripts.evaluate --calls call_001,call_004       # seçili çağrılar
python -m scripts.evaluate --fast <model> --smart <model>  # modeli .env'i değiştirmeden dene
```

Çıktı: alan bazında doğruluk tablosu, yanlış alanlar, süre ve token sayısı. Ücretsiz katman sınırları nedeniyle çağrılar sırayla işlenir.

## Uç Noktalar

Analiz arka planda Celery işçisinde çalışır (`-Q default,analysis,index`); LLM ayarları `.env`'de dolu olmalıdır. Tüm uçların sözleşmesi (şemalar, yetki başlıkları, örnek JSON'lar): `docs/api.md`. Aşağıdakiler şu an çalışan uçlardır.

| Yol | Açıklama |
|-----|----------|
| `GET /health` | Süreç ayakta mı (canlılık) |
| `GET /health/ready` | Veritabanı ve Redis erişilebilir mi (hazır olma; değilse 503) |
| `GET /api/v1/me` | Servis anahtarı doğrulaması (`X-Service-Key`, isteğe bağlı `X-User-Id`) |
| `GET /api/v1/analytics/summary` | KPI ve analitik özeti: çağrı ve satış metrikleri, neden ve kategori dağılımları (#52) |
| `GET /api/v1/calls` | Sayfalı çağrı listesi ve filtreleme (tarih, aciliyet, kategori, durum, serbest metin) |
| `GET /api/v1/calls/{id}` | Çağrı detayı: santral, maskeli transkript (segmentleriyle) ve en son analiz |
| `GET /api/v1/crm` | Sayfalı CRM kayıt/öneri listesi (7 temel alan + alıntılar) |
| `POST /api/v1/calls` | Transkriptli çağrıyı kaydeder, analizi kuyruğa alır (202); ayrıntı `docs/api.md` |
| `POST /api/v1/calls/audio` | Ses kaydını yükler (multipart); STT → analiz arka planda (202) |
| `POST /api/v1/calls/{id}/analyze` | Çağrıyı yeniden işler: yeni analiz sürümü, transkript yoksa yeniden STT |
| `GET /api/v1/calls/{id}/status` | İşlenme durumu |
| `GET /api/v1/me/owner` | Tekne sahibi kimliği doğrulaması (`X-Service-Key` + zorunlu `X-User-Id`) |

## Klasör Yapısı

| Klasör | İçerik |
|--------|--------|
| `app/core` | Ayarlar, loglama, hata yönetimi, servis anahtarı doğrulama, istek kimliği ara katmanı |
| `app/api` | Route'lar ve bağımlılıklar (oturum, servis anahtarı, kullanıcı kimliği) |
| `app/db` | Async SQLAlchemy motoru, oturumlar, model tabanı (şema Supabase migration'larından gelir) |
| `app/schemas` | API istek/yanıt şemaları |
| `app/services` | İş mantığı; `analysis_store.py`: transkript ve analiz sonuçlarını veritabanına yazma/okuma, `DbRunRecorder` |
| `app/workers` | Celery uygulaması ve kuyruklar (stt, analysis, index) |
| `app/llm` | Ücretsiz, OpenAI-uyumlu LLM sağlayıcıları için istemci fabrikası |
| `app/agents` | Agent sözleşmesi (`base.py`), LLM agent tabanı (`llm_agent.py`), dört analiz agent'ı, prompt'lar (`prompts/`), alıntı doğrulama (`grounding.py`), LangGraph orkestratörü (`orchestrator.py`), varsayılan akış (`registry.py`) |
| `app/assistant` | Miço AI (Tekne Sahibi asistanı): planlayıcı, hazır araçlar, tekne karnesi araması, cevap üretimi, kaynak kontrolü; dışa açılan tek giriş `answer_question` (çağrı analizinden bağımsız) |
| `app/stt` | STT: sağlayıcı sözleşmesi (`base.py`), faster-whisper / Whisper API / stub (`providers.py`), konuşmacı ayrımı ve turlar (`pipeline.py`), WER/CER (`metrics.py`) |
| `app/rag` | RAG: embedding sağlayıcıları (`embedders.py`: bge-m3/TEI, OpenAI uyumlu, hash), indeksleme (`indexer.py`), hibrit arama (`search.py`) |
| `tests` | Testler (gerçek veritabanı/Redis/LLM gerektirmez) |

## Kurallar

- Kod yorumları Türkçe; değişken, fonksiyon ve tablo adları İngilizce.
- Route'lar iş mantığı içermez; servisler HTTP bilmez.
- Veritabanı şeması yalnızca `supabase/migrations` ile değişir.
- Gizli anahtarlar `.env`'de durur ve asla commit edilmez.
