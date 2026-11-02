# Yük testi, yetki ve güvenlik kontrol listesi (#158)

**Tarih:** 2026-11-02 · **Betikler/testler:** `backend/scripts/yuk_testi.py`, `backend/tests/test_authorization_matrix.py`

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
| Dosya yükleme | ✓ | 25 MB sınırı (413), tür kontrolü (415), aynı ses 409, depolama adı içerik özeti |
| Gizli anahtar taraması | ✓ | İzlenen dosyalarda `nvapi-`/`sk-`/`AIza`/`AKIA`/`ghp_`/JWT desenleri yok; `backend/.env` git'te yok (`.gitignore`), `.env.example` değerleri boş; ölçüm günlüklerinde LLM anahtarı geçmiyor |
| Hata iletisinde iç bilgi | düzeltildi | Bozuk ses hatası sunucu dosya yolunu gösteriyordu (#221). Kalan: LLM sağlayıcısının ham İngilizce hata gövdesi `calls.error`'da görünüyor (öneri: Türkçe, kısa kullanıcı iletisi; ayrıntı yalnızca `agent_runs`'ta) |
| Bağımlılıklar — backend (`pip-audit`) | düzeltildi | 4 dolaylı paket / 17 bulgu: `certifi` (CA kökü), `filelock` (13), `langgraph-sdk`, `opentelemetry-api`; `uv.lock` güncellendi (certifi 2026.10.23, filelock 4.2.6, langgraph-sdk 0.4.11, opentelemetry-api 1.45.2). Hiçbiri uygulamanın doğrudan kullandığı koddan değil |
| Bağımlılıklar — frontend (`npm audit`) | **AÇIK (frontend)** | `next@16.4.0` **kritik**: kimlik doğrulamasız RCE (Image Optimization'da SVG, `use cache` typed array) ve Server Actions DoS → `next@16.4.4`; `zod` yüksek → `npm audit fix`. 18 orta bulgu yalnızca eslint/openapi-typescript geliştirme araçlarında. h8-frontend'e bildirildi |
| Docker | ✓ / iyileştirildi | Kök olmayan kullanıcı; Postgres ve Redis portları artık yalnızca `127.0.0.1`'e bağlı (eskiden tüm arayüzler; varsayılan şifre `postgres`). Compose'taki `SERVICE_KEY` varsayılanı `change-me-in-local-env` yalnızca yerel içindir; canlıda Secret Manager (`docs/canliya_alma.md`) |
| CORS / API belgesi | ✓ | İzinli origin listesi (`CORS_ORIGINS`); `/docs` prod'da kapalı |
| API düzeyinde hız sınırı | yok | Servis yalnızca .NET uygulamasından çağrılır; ihtiyaç olursa ters vekil (gateway) katmanında uygulanmalı |
| LLM'e giden veri | ✓ | Transkriptteki kişisel veriler maskelenir (`app/services/masking.py`); maskesiz metne düşülmez |
