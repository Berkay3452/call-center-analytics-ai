# Sistemi yerelde çalıştırma rehberi

Bu rehber, projeyi sıfırdan bilgisayarında ayağa kaldırmak isteyen herkes (Berkay, Ahmet, Melih) içindir. Sonunda şunlar çalışır durumda olur: PostgreSQL, Redis, backend API, analiz işçisi (Celery) ve frontend.

> Durum: **14 Ekim 2026'da temiz bir klonda (`git clone`, boş veritabanı, `.env.example`'dan) baştan sona doğrulandı.** Bir adım çalışmazsa "Sık hatalar" bölümüne bak, orada yoksa #58'e yorum yaz.

## 1. Gerekenler

| Araç | Sürüm | Neden |
|---|---|---|
| Docker Desktop | güncel (WSL2 destekli) | PostgreSQL (pgvector) ve Redis |
| [uv](https://docs.astral.sh/uv/) | güncel | Python 3.12 ve backend bağımlılıkları (sistem Python'u gerekmez) |
| Node.js | 20+ | Frontend |
| Git | herhangi | Repo |

## 2. Hızlı başlangıç (5 terminal sekmesi)

Tüm komutlar Windows PowerShell için yazıldı; macOS/Linux'ta kopyalama komutu hariç aynıdır.

**Sekme 1: veritabanı ve Redis** (repo kökünde)

```
docker compose -f infra/docker-compose.yml up -d
```

Postgres `localhost:5433`, Redis `localhost:6379` portunda açılır. Durumu `docker compose -f infra/docker-compose.yml ps` ile gör; ikisi de `healthy` olmalı.

**Sekme 2: backend kurulumu** (`backend/` klasöründe)

```
uv sync --extra ai
Copy-Item .env.example .env
```

`.env` dosyasını aç ve bölüm 3'teki zorunlu değerleri doldur. Sonra:

```
uv run alembic upgrade head
uv run python -m scripts.seed
```

İlk komut tabloları kurar, ikincisi sentetik veriyi (müşteri, tekne, usta, servis kayıtları, 30 çağrı ve analiz sonuçları) yükler. Seed tekrar çalıştırılabilir; sıfırdan yüklemek için `uv run python -m scripts.seed --reset`.

**Sekme 2: API'yi başlat** (aynı klasör)

```
uv run uvicorn app.main:app --reload
```

**Sekme 3: Celery işçisi** (`backend/`). Ses yükleme ve yeniden analiz arka planda bu işçide çalışır. Yalnızca seed verisine bakacaksan gerekmez.

```
uv run celery -A app.workers.celery_app worker -Q default,stt,analysis,index --pool=solo -l info
```

**Sekme 4: frontend** (`frontend/` klasöründe)

```
npm install
Copy-Item .env.example .env.local
npm run dev
```

Frontend `http://localhost:3000` adresinde açılır. Varsayılan olarak **sahte (mock) veriyle** çalışır. Gerçek backend'e bağlamak için `.env.local` içinde `NEXT_PUBLIC_USE_MOCKS=false` yap, `SERVICE_KEY` değerini backend `.env`'deki `SERVICE_API_KEY` ile aynı yap ve `npm run dev`'i yeniden başlat.

## 3. Ortam değişkenleri (backend/.env)

`.env.example` dosyasındaki varsayılanlar yerel Docker ile uyumludur. Değiştirmen gerekenler:

| Değişken | Ne yapmalı |
|---|---|
| `SERVICE_API_KEY` | Herhangi bir değer yaz (ör. `yerel-gelistirme-anahtari`). Frontend'deki `SERVICE_KEY` ile birebir aynı olmalı |
| `AUTH_DEV_BYPASS` | İsteğe bağlı: `true` yaparsan servis anahtarı olmadan `/api/v1` uçlarını deneyebilirsin (yalnızca `APP_ENV=local`) |
| `LLM_API_KEY` | Yalnızca **yeni çağrı analizi** (Celery) ve Miço AI için gerekir. Seed verisini görmek için gerekmez. Anahtarı Berkay'dan değil, kendi hesabından al; `.env` asla commit edilmez |
| `DATABASE_URL`, `REDIS_URL` | Docker compose ile geliyor, değiştirme |
| `STT_PROVIDER` | Ses yüklemeyi denemeyeceksen dokunma. Hızlı deneme için `stub`; ayrıntı `backend/README.md` |
| `EMBEDDING_PROVIDER` | Miço AI aramasını denemeyeceksen `hash` yaz (model indirmeden). Gerçek arama için bölüm 5 |

## 4. Çalıştığını kontrol et

| Kontrol | Beklenen |
|---|---|
| `http://localhost:8000/health` | `{"status":"ok"...}` |
| `http://localhost:8000/health/ready` | Veritabanı ve Redis `ok`; değilse 503 |
| `http://localhost:8000/docs` | Swagger arayüzü; `Authorize` ile `X-Service-Key` gir |
| `GET /api/v1/me` (başlık: `X-Service-Key`) | 200 |
| `GET /api/v1/calls?page_size=5` | 5 çağrı, `total` 30 |
| `GET /api/v1/analytics/summary?date_from=2026-10-01&date_to=2026-10-31` | `total_calls` 30 |
| `http://localhost:3000` | `/admin/analytics` sayfasına yönlenir |

Komut satırından deneme örneği:

```
curl -H "X-Service-Key: <SERVICE_API_KEY>" "http://localhost:8000/api/v1/calls?page_size=5"
```

## 5. İsteğe bağlı parçalar

- **Miço AI araması (bge-m3 embedding):** `docker compose -f infra/docker-compose.yml --profile rag up -d` (ilk açılışta ~2,3 GB model iner), sonra `backend/` içinde `uv run python -m scripts.rag_index`. Ayrıntı: `backend/README.md`.
- **Ses → yazı (STT):** `uv sync --extra ai --extra stt`; ilk kullanımda model (`small`, ~500 MB) iner. Model varsayılan olarak `C:\Users\<sen>\.cache\huggingface` altına iner; C: diskin doluysa `.env` içinde `WHISPER_DOWNLOAD_ROOT=D:/models/whisper` yaz (klasörü önceden aç). Denemek için bir ses dosyası `POST /api/v1/calls/audio` ile yüklenir (`file` + `started_at` form alanları); durum `yaziya_cevriliyor` → `isleniyor` → `tamam` ilerler. Mono kayıtta konuşmacılar ayrılamaz (tek parça çıkar). Ayrıntı: `backend/README.md`.
- **Miço AI sohbeti (gerçek veriyle):** `.env`'de `LLM_API_KEY` dolu olmalı ve arama için `EMBEDDING_PROVIDER=hash` (hızlı) ya da bge-m3 (ilk madde). Seed sahibi `606bd734-644f-5c21-af2f-dc734c4ecd67` (Ahmet Yılmaz, tekne Poyraz) ile: `curl -N -X POST -H "X-Service-Key: <anahtar>" -H "X-User-Id: 606bd734-644f-5c21-af2f-dc734c4ecd67" -H "Content-Type: application/json" -d '{"question":"Kaç bakım hakkım kaldı?"}' http://localhost:8000/api/v1/chat/messages/stream` (SSE: `status` → `delta` → `done`).
- **Testler:** `uv run pytest` (hızlı, DB gerekmez). Gerçek veritabanı testleri: Docker ayaktayken `$env:RUN_DB_TESTS="1"; uv run pytest`.

## 6. Durdurma ve sıfırlama

```
docker compose -f infra/docker-compose.yml down        # durdur, veri kalır
docker compose -f infra/docker-compose.yml down -v     # durdur ve veritabanını sil (sıfırdan başlamak için)
```

`down -v` sonrası bölüm 2'deki `alembic upgrade head` ve `seed` komutlarını tekrar çalıştır.

> Dikkat: `down -v`, bge-m3 model önbelleğini (`hf-cache`, ~2,3 GB) de siler. Yalnızca veritabanını sıfırlamak için: `docker compose -f infra/docker-compose.yml down` ve ardından `docker volume rm call-center-dev_pgdata`. Veritabanı doluyken aynı sonucu `uv run python -m scripts.seed --reset` verir.

## 7. Sık hatalar

| Belirti | Neden / çözüm |
|---|---|
| `docker compose` bulunamıyor / "daemon is not running" | Docker Desktop açık değil. Aç, "Engine running" olana kadar bekle |
| `connection refused` 5433 | Postgres henüz hazır değil veya compose çalışmıyor: `docker compose -f infra/docker-compose.yml ps` |
| Port 5433 veya 6379 dolu | Başka bir Postgres/Redis çalışıyor. Onu durdur veya compose'daki portu ve `.env`'deki adresi birlikte değiştir |
| API 401 `unauthorized` | `X-Service-Key` yok ya da `.env`'deki `SERVICE_API_KEY` ile aynı değil. Frontend için `SERVICE_KEY` da aynı olmalı |
| `alembic` "relation already exists" | Eski veritabanı kalmış: bölüm 6'daki `down -v` ile sıfırla |
| `/health/ready` 503 | Postgres veya Redis ayakta değil; yanıtın içinde hangisi olduğu yazar |
| Yeni çağrı "isleniyor"da takılı | Celery işçisi çalışmıyor (sekme 3) veya `LLM_API_KEY` boş / hatalı |
| Frontend hâlâ sahte veri gösteriyor | `.env.local` içinde `NEXT_PUBLIC_USE_MOCKS=false` yapıp `npm run dev`'i yeniden başlat |
| Frontend gerçek backend'e bağlıyken konsolda "uncached data during prerendering" hatası, `npm run build` kırılıyor | Bilinen sorun (Next 16 Suspense kuralı, çağrı sayfaları); `npm run dev` ile sayfalar çalışır. Düzeltme planlanıyor |
| `bge-m3` konteyneri hemen kapanıyor (çıkış kodu 137) | Bellek yetersizliği; `infra/docker-compose.yml`'deki `--max-batch-tokens 2048` ayarı bunu önler. Güncel `main`'i çektiğinden emin ol |
| STT modeli C: diskini dolduruyor | `.env` içinde `WHISPER_DOWNLOAD_ROOT` ayarla (bölüm 5) |
| Windows'ta Celery hata veriyor | `--pool=solo` bayrağını kullandığından emin ol |
