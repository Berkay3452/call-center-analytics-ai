# Canlıya Alma (Google Cloud Dağıtım) Ön Araştırma Rehberi

Bu belge, **Call Center Analytics AI** sisteminin canlı ortama (Google Cloud Platform - GCP) taşınması için mimari seçenekleri, gizli anahtarları, ses depolama stratejisini ve dağıtım adımlarını özetleyen ön araştırma notudur (#120).

---

## 1. Google Cloud Mimari Seçenekleri

Sistemin bileşenleri:
- **Backend API:** FastAPI (HTTP + SSE stream)
- **Asenkron İşçi (Worker):** Celery + Celery Beat (STT transkripsiyon + LLM ajan zinciri + periyodik görevler)
- **Frontend Web:** Next.js 16 (Standalone Node.js sunucusu)
- **Veritabanı:** PostgreSQL 17 + pgvector (Supabase veya Cloud SQL)
- **Kuyruk & Önbellek:** Redis
- **Vektör Arama (Opsiyonel):** Text Embeddings Inference (bge-m3)

### Seçenek A: Cloud Run + Yönetilen Veritabanı (Önerilen / Sunucusuz)

* **Backend API & Frontend:** İki ayrı Google Cloud Run servisi olarak çalıştırılır.
  * API: `call-center-api` (otomatik ölçeklenen konteyner, min-instances: 1 önerilir).
  * Web: `call-center-web` (Next.js standalone imajı, minimum kaynak tüketimi).
* **Celery Worker:**
  * Cloud Run Servisi (CPU her zaman tahsisli: `--no-cpu-throttling`, maksimum timeout 60 dakika) veya Cloud Run Job.
  * *Alternatif:* Celery yerine Google Cloud Tasks entegrasyonu veya sabit bir küçük VM (Compute Engine `e2-small` / `e2-medium`).
* **Veritabanı:** Supabase (mevcut canlı Postgres + pgvector) veya GCP Cloud SQL for PostgreSQL 17.
* **Redis:** Google Cloud Memorystore for Redis veya Upstash Serverless Redis.
* **Avantajları:** Düşük ilk maliyet, sunucu bakımı gerektirmemesi, otomatik SSL, Google IAM ve Secret Manager entegrasyonu.

### Seçenek B: Compute Engine VM (Tek Sunucuda Docker Compose / Demo & Sunum)

* **Yapılandırma:** GCP üzerinde tek bir Ubuntu VM (`e2-standard-4`, 4 vCPU, 16 GB RAM, 50 GB SSD).
* **Dağıtım:** `infra/docker-compose.yml` (`--profile app`) ile sistem tek komutla VM üzerinde ayağa kaldırılır; Nginx veya Caddy ters vekil (reverse proxy) ile Let's Encrypt SSL sertifikası sağlanır.
* **Avantajları:** Yerel Docker ortamıyla birebir aynı çalışma prensibi; STT (faster-whisper) ve embedding modellerinin diskte kalıcı önbelleğe alınması kolaydır; Celery worker için ekstra ayar gerektirmez.
* **Dezavantajları:** Yatay ölçekleme manueldir; sunucu güncelleme ve yedekleme sorumluluğu ekibe aittir.

---

## 2. Gerekli Gizli Anahtarlar (Secrets Management)

Üretim ortamında gizli anahtarlar asla imaj içerisine gömülmez; **GCP Secret Manager** veya Cloud Run ortam değişkenleri üzerinden enjekte edilir:

| Değişken Adı | Açıklama | Kullanıldığı Servis |
|---|---|---|
| `SERVICE_API_KEY` | Backend API'yi yetkisiz erişimden koruyan servis anahtarı | API, Worker, Init |
| `SERVICE_KEY` | Frontend sunucusunun Backend API ile haberleşirken kullandığı servis anahtarı | Web |
| `DATABASE_URL` | PostgreSQL bağlantı adresi (`postgresql+asyncpg://...`) | API, Worker, Init |
| `REDIS_URL` | Redis bağlantı adresi (`redis://...`) | API, Worker, Init |
| `CELERY_BROKER_URL` | Celery broker adresi (Redis db 1) | API, Worker |
| `CELERY_RESULT_BACKEND` | Celery sonuç adresi (Redis db 2) | API, Worker |
| `LLM_API_KEY` | Model sağlayıcısı API anahtarı (NVIDIA, Gemini veya Groq) | Worker |
| `LLM_PROVIDER` | Seçilen sağlayıcı (`nvidia`, `gemini`, `groq`, `openai_compatible`) | Worker |
| `LLM_FAST_MODEL` | Hızlı sınıflandırıcı/özetleyici model adı | Worker |
| `LLM_SMART_MODEL` | Güçlü CRM/satış analizi model adı | Worker |
| `AUDIO_STORAGE_BACKEND` | Ses depolama sağlayıcısı: `local` (varsayılan) veya `gcs` (#121) | API, Worker |
| `GCS_BUCKET_NAME`, `GCS_PROJECT_ID` | Ses kayıtlarının tutulduğu Google Cloud Storage kovası ve projesi (`AUDIO_STORAGE_BACKEND=gcs` iken) | API, Worker |
| `GCS_CREDENTIALS_FILE` | Servis hesabı anahtar dosyası (Cloud Run'da boş bırakılır, çalışan hesabın kimliği kullanılır) | API, Worker |

---

## 3. Ses Depolama Stratejisi (#121 Bağımlılığı)

Konteynerler durumsuz (stateless) olduğundan, santralden gelen ses dosyaları yerel diskte tutulamaz:

1. **Supabase Storage / Google Cloud Storage (GCS):**
   * Ses dosyaları `POST /api/v1/calls/audio` üzerinden yüklendiğinde içerik özeti (SHA-256) hesaplanır.
   * Dosya doğrudan `call-audio` isimli bulut deposuna yazılır.
   * Veritabanında `calls.audio_path` sütununda depodaki nesne anahtarı (`calls/{sha256}.wav`) saklanır.
2. **Erişim ve Güvenlik:**
   * Ses oynatma uç noktası (`GET /api/v1/calls/{id}/audio`), bulut sağlayıcısından kısa ömürlü imzalı URL (Signed URL) üreterek istemciye yönlendirme (302 Redirect) yapar veya doğrudan akış sağlar (Range desteğiyle).
3. **STT İşleme:**
   * Celery STT işçisi ses dosyasını bulut deposundan geçici çalışma dizinine indirir (`/tmp`), transkripsiyonu tamamladıktan sonra geçici dosyayı temizler.

---

## 4. Tahmini Canlıya Alma Adımları

1. **Google Cloud Projesi ve Kaynakların Hazırlanması:**
   ```bash
   gcloud config set project <PROJECT_ID>
   gcloud services enable run.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com
   ```
2. **Artifact Registry Deposu Oluşturma:**
   ```bash
   gcloud artifacts repositories create call-center-repo \
       --repository-format=docker \
       --location=europe-west3 \
       --description="Call Center AI Docker İmajları"
   ```
3. **İmajların Derlenmesi ve Yüklenmesi:**
   ```bash
   # Backend imajı
   docker build -t europe-west3-docker.pkg.dev/<PROJECT_ID>/call-center-repo/backend:latest ./backend
   docker push europe-west3-docker.pkg.dev/<PROJECT_ID>/call-center-repo/backend:latest

   # Frontend imajı (NEXT_PUBLIC_USE_MOCKS derleme sırasında koda gömülür; Dockerfile varsayılanı
   # false'tur, çalışma zamanında ortam değişkeniyle değiştirilemez)
   docker build -t europe-west3-docker.pkg.dev/<PROJECT_ID>/call-center-repo/frontend:latest ./frontend
   docker push europe-west3-docker.pkg.dev/<PROJECT_ID>/call-center-repo/frontend:latest
   ```
4. **Veritabanı Migration & Seed (Tek Seferlik Cloud Run Job):**
   ```bash
   gcloud run jobs create call-center-init \
       --image=europe-west3-docker.pkg.dev/<PROJECT_ID>/call-center-repo/backend:latest \
       --command="python,-m,scripts.docker_init" \
       --set-secrets="DATABASE_URL=DATABASE_URL:latest,REDIS_URL=REDIS_URL:latest" \
       --region=europe-west3

   gcloud run jobs execute call-center-init --region=europe-west3
   ```
5. **API ve Web Servislerinin Dağıtımı:**
   ```bash
   # Backend API
   gcloud run deploy call-center-api \
       --image=europe-west3-docker.pkg.dev/<PROJECT_ID>/call-center-repo/backend:latest \
       --port=8000 \
       --allow-unauthenticated \
       --region=europe-west3 \
       --set-secrets="DATABASE_URL=DATABASE_URL:latest,REDIS_URL=REDIS_URL:latest,SERVICE_API_KEY=SERVICE_API_KEY:latest"

   # Frontend Web
   gcloud run deploy call-center-web \
       --image=europe-west3-docker.pkg.dev/<PROJECT_ID>/call-center-repo/frontend:latest \
       --port=3000 \
       --allow-unauthenticated \
       --region=europe-west3 \
       --set-env-vars="API_URL=https://call-center-api-<hash>.a.run.app/api/v1" \
       --set-secrets="SERVICE_KEY=SERVICE_API_KEY:latest"
   ```

---

## 5. Risk ve Optimizasyon Değerlendirmesi

* **Soğuk Başlangıç (Cold Start):** Python + ML kütüphaneleri (PyAV, faster-whisper) konteyner başlangıcında 5-10 saniye ek süre alabilir. Cloud Run'da API için `min-instances: 1` tutulması gecikmeyi engeller.
* **Bellek Tahsisi:** Backend ve işçi konteynerleri için en az 2 GB RAM (STT veya RAG çalışacaksa 4 GB) yapılandırılmalıdır.
* **Celery Timeout Sınırı:** Cloud Run maksimum istek süresi 60 dakikadır. Uzun ses dosyaları için bu süre yeterlidir ancak işçinin arka planda kesintisiz çalışması için Compute Engine VM veya kalıcı CPU tahsisi önerilir.
