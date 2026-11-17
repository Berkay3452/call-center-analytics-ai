# Yük testi, yetki ve güvenlik kontrol listesi (#158)

**Tarih:** 2026-11-02 (güncelleme 2026-11-17, #276) · **Betikler/testler:** `backend/scripts/yuk_testi.py`, `backend/tests/test_authorization_matrix.py`, `backend/scripts/guvenlik_testi.py` (saldırı paketi)

> Saldırı odaklı otomatik paket, sonuç tablosu, OWASP LLM/API eşlemesi ve bilinen sınırlamalar: **`docs/guvenlik_testi.md`**. Bu belgedeki kontrol listesi o paketin kanıtlarıyla güncellenmiştir.

## 1. Hafif yük testi

Tek `uvicorn` süreci (geliştirme düzeni), seed'li ayrı veritabanı (50 çağrı), Docker Desktop (Windows) üzerinde Postgres; makine yoğun kullanımdaydı (başka ajanlar/Docker çalışıyordu), sayılar yukarı yönde gürültülüdür. Her hücre 200 istek; **hata (200 dışı yanıt) yok**.

| Uç | Eşzamanlı | İstek/sn | p50 ms | p95 ms | maks ms |
|---|---|---|---|---|---|
| `GET /calls` (liste, 20 satır) | 20 | 52,9 | 271 | 1246 | 1475 |
| `GET /calls` | 30 | 52,0 | 399 | 1359 | 1526 |
| `GET /analytics/summary` (KPI) | 20 | 27,0 | 604 | 1654 | 2192 |
| `GET /analytics/summary` | 30 | 28,9 | 842 | 1819 | 1929 |
| `POST /chat/messages` ("selam", LLM'siz) | 20 | 32,7 | 466 | 1419 | 1801 |
| `POST /chat/messages` | 30 | 33,1 | 694 | 1777 | 1906 |

Tek istek (yük yokken, `127.0.0.1`): `/api/v1/me` 7 ms · liste 176 ms · KPI 388 ms.

**Darboğaz notları**
- Süre veritabanı gidiş-dönüşlerinden gelir: boş yükte bile liste (2 sorgu) 176 ms, KPI 388 ms; tablolar küçük (< 0,5 MB) ve indeksler yerinde. Windows'ta Docker port yönlendirmesi sorgu başına gecikme ekler; canlıda (aynı ağda) çok daha düşük beklenir.
- Tek süreç + `DB_POOL_SIZE=5`: 30 eşzamanlıda istekler kuyruğa girer (p95 ≈ 1,3–1,8 sn). Havuzu 20'ye çıkarmak KPI'da 29 → 35 istek/sn, sohbette 33 → 44 istek/sn verdi (liste gürültü içinde değişmedi); canlıda `DB_POOL_SIZE` 15–20 ve birden çok API süreci önerilir.
- `localhost` adı Windows'ta IPv6'ya önce düşüp her istekte ≈ 200 ms ekler; yerelde ölçüm/geliştirme için `127.0.0.1` kullanın.
- Hedef (20–30 eşzamanlı istek) hatasız karşılandı. LLM'li sohbet soruları sağlayıcı kotasına bağlıdır (≈ 40 istek/dk, bkz. `docs/dayaniklilik.md`); burada ölçülmedi.

Yeniden çalıştırma: `uv run python -m scripts.yuk_testi --base-url http://127.0.0.1:8100 --owner-id <müşteri UUID> --concurrency 20,30 --requests 200` (sohbet kayıt yazar; ortak veritabanında değil ayrı bir veritabanında çalıştırın).

## 2. Yetki testleri

`tests/test_authorization_matrix.py` (83 test), OpenAPI belgesindeki **her** `/api/v1` ucu için:
- `X-Service-Key` yoksa ve yanlışsa 401 `unauthorized` (28 uç × 2); yeni bir uç eklenip kimlik doğrulaması unutulursa test kırılır.
- Tekne sahibi uçlarında (`/chat/*`, `/assistant/*`) `X-User-Id` yoksa veya UUID değilse (`1 OR 1=1` dahil) 400.
- Anahtar sorgu dizgesinden kabul edilmez; `/health` herkese açık ve yalnızca `status/version/env` döner; `AUTH_DEV_BYPASS` prod'da reddedilir.

Mevcut, kapsamı genişlemeden korunan testler: sohbet oturumu başka sahibe aitse 404 (silme dahil, `test_assistant_chat_integration.py`), araçların `owner_id` zorunluluğu ve başkasının teknesi/notu dönmemesi (`test_assistant*.py`), geçmiş sorularında başka sahibin kaydının alıntılanmaması (`test_assistant_history_integration.py`).

## 3. Güvenlik kontrol listesi

| Madde | Durum | Not |
|---|---|---|
| Servis anahtarı sabit zamanlı karşılaştırılır, yalnızca başlıktan alınır | ✓ | `app/core/security.py`; prod'da ≥ 32 karakter, `AUTH_DEV_BYPASS` yalnızca local/test |
| Her uç kimlik ister | ✓ | Yetki matrisi testi (§2) |
| Tekne sahibi izolasyonu | ✓ | Kodda zorunlu `owner_id`, başka sahibin oturumu 404 (varlığı sızdırılmaz) |
| SQL enjeksiyonu | ✓ | Parametreli SQLAlchemy sorguları; tek `f"..."` kullanımı sabit bir `server_default` |
| Dosya yükleme | ✓ | 25 MB sınırı (413), tür kontrolü (415), içerik doğrulaması (sihirli bayt + kod çözücü, bozuk/sahte uzantı 415, 120 dk üstü 413; #270), aynı ses 409, depolama adı içerik özeti |
| Gizli anahtar taraması | ✓ | İzlenen dosyalarda `nvapi-`/`sk-`/`AIza`/`AKIA`/`ghp_`/JWT desenleri yok; `backend/.env` git'te yok (`.gitignore`), `.env.example` değerleri boş; ölçüm günlüklerinde LLM anahtarı geçmiyor |
| Hata iletisinde iç bilgi | düzeltildi (#221, #271) | Bozuk ses hatası sunucu yolunu gösteriyordu (#221); LLM/STT ham hata gövdesi `calls.error`'da görünüyordu (#271'de kapandı: sabit Türkçe iletiler, ayrıntı yalnızca `agent_runs`'ta) |
| Bağımlılıklar — backend (`pip-audit`) | düzeltildi | 4 dolaylı paket / 17 bulgu: `certifi` (CA kökü), `filelock` (13), `langgraph-sdk`, `opentelemetry-api`; `uv.lock` güncellendi (certifi 2026.10.23, filelock 4.2.6, langgraph-sdk 0.4.11, opentelemetry-api 1.45.2). Hiçbiri uygulamanın doğrudan kullandığı koddan değil |
| Bağımlılıklar — frontend (`npm audit`) | **Kapatıldı (#272)** | `next@16.4.0` kritik bulgusu sonraki sürümlerle kapandı; 2026-11-17 `npm audit --omit=dev`: kritik/yüksek yok, 1 orta (`next` 16.3.0–16.4.4, `unstable_cache` kök parametre bilgi sızıntısı; düzeltme 16.4.6, bkz. §4). Geliştirme araçlarındaki orta bulgular üretime girmez |
| Docker | ✓ / iyileştirildi | Kök olmayan kullanıcı; Postgres ve Redis portları artık yalnızca `127.0.0.1`'e bağlı (eskiden tüm arayüzler; varsayılan şifre `postgres`). Compose'taki `SERVICE_KEY` varsayılanı `change-me-in-local-env` yalnızca yerel içindir; canlıda Secret Manager (`docs/canliya_alma.md`) |
| CORS / API belgesi | ✓ / düzeltildi (#276) | İzinli origin listesi (`CORS_ORIGINS`); `/docs` prod'da kapalı. Saldırı paketi `/openapi.json`'ın prod'da kimliksiz açık kaldığını buldu (tüm uç envanteri görünüyordu); `openapi_url` prod'da kapatıldı |
| İşlev düzeyi yetki (rol) | **kısmi** | Yönetici uçları (`/audit-log`, çağrı silme) tekne sahibi kimliğine 403 verir; 7 yazma ucu henüz rol denetimi yapmaz (BS-1, #275); `test_yetki_haritasi.py` açık uç kümesini sabitler |
| Saldırı paketi (kimlik, IDOR, injection, sızıntı, hız sınırı, araç yetkisi) | ✓ | 327 test, 0 kalan, 2 belgelenmiş sınırlama; `docs/guvenlik_testi.md`, CI'da her PR'da |
| API düzeyinde hız sınırı | **var** (#271) | Redis kayan pencere (kimlik kovası + kimlikten bağımsız IP tavanı: genel 600/dk, asistan 60/dk; `X-User-Id` döndürülerek kimlik kovası atlatılsa da IP tavanı geçerli kalır); bkz. §5 |
| LLM'e giden veri | ✓ | Transkriptteki kişisel veriler maskelenir (`app/services/masking.py`); maskesiz metne düşülmez |

## 4. Tedarik zinciri taramaları (#272, 2026-11-17)

**Yeniden çalıştırılan denetimler**
- Backend: `uvx pip-audit --requirement requirements.txt --no-deps --disable-pip` → **bilinen açık yok**.
- Frontend: `npm audit --omit=dev --audit-level=high` → kritik/yüksek yok; 1 **orta** bulgu: `next` 16.3.0–16.4.4 (`unstable_cache()` ile çağrılan `use cache` işlevinde kök parametre bilgi sızıntısı, GHSA-mfr8-8qww-v76h). Uygulama `unstable_cache`/`use cache` kullanmıyor, bu yüzden etkilenmiyor; düzeltme 16.4.6'dadır ve Dependabot `next` için PR açacaktır (sürüm yükseltmesi o PR'da yapılır). Eşik `high` olduğundan CI kırmaz; gerekçeli istisna budur.

**CI'daki otomatik adımlar**
| Adım | Davranış |
|---|---|
| `backend-ci.yml` → `security` (pip-audit) | Her bilinen açıkta **PR'ı kırar** (`continue-on-error` kaldırıldı, `Backend CI sonucu`na bağlandı). pip-audit önem derecesine göre süzemez; yanlış pozitifte `--ignore-vuln <ID>` ve bu bölümde gerekçe |
| `frontend-ci.yml` → `npm audit --audit-level=high` | Yüksek/kritikte kırar (önceden vardı) |
| `gizli-anahtar-taramasi.yml` (gitleaks) | Her PR'da tüm geçmişi tarar, bulguda kırar; ayrı iş akışı olduğundan diğer işlere süre eklemez |
| `imaj-taramasi.yml` (Trivy) | Yalnızca bilgi raporu (`exit-code: 0`); PR'larda çalışmaz: haftalık, elle ve Dockerfile/kilit dosyası main'e girince |
| `.github/dependabot.yml` | Haftalık uv, npm, GitHub Actions ve Docker güncelleme PR'ları |
| `.pre-commit-config.yaml` | İsteğe bağlı yerel gitleaks + özel anahtar denetimi |
| `.gitignore` | `.env*`, `*.pem`, `*.key`, `*.p12`, `*.pfx`, `*.jks`, `id_rsa*`, `credentials.json` |
| `tests/test_secret_hygiene.py` | LLM/STT/embedding/servis/Supabase anahtarları yalnızca ortamdan okunur, varsayılanı yok, `repr`/dump/günlüğe düşmez; kaynakta anahtar deseni yok; `.env.example` boş |

Sınırlar: gitleaks ve Trivy ilk kez CI'da çalışır (yerelde ikili indirilmedi); ilk çalışmada yanlış pozitif çıkarsa `.gitleaksignore` ile gerekçeli eklenir.

## 5. Hız sınırı ölçümü (#271, 2026-11-17)

Varsayılan sınırlarla (genel 120/dk, aynı IP, kimliksiz) yerel API'ye `python -m scripts.yuk_testi --concurrency 20 --requests 100` çalıştırıldı (Postgres ve Redis yerel):

| Uç | Eşzamanlı | İstek | 200 | 429 | Hata | p50 ms |
|---|---|---|---|---|---|---|
| `GET /calls` | 20 | 100 | 100 | 0 | 0 | 114 |
| `GET /analytics/summary` | 20 | 100 | 19 | 81 | 0 | 466 |

Aynı dakikada 120 istek hakkı (ısınma isteği + 100 + 19) dolduğu için kalan 81 istek `429` aldı; **hata oranı %0** (429 hata sayılmaz, ayrıca raporlanır). Bu, sınırın çalıştığını gösterir; kapasite ölçümü için API `RATE_LIMIT_GENERAL_PER_MIN` yükseltilerek başlatılmalıdır (duman testi ortamında 2000). Kalıcı gecikme değerleri §1'deki tablodadır.
