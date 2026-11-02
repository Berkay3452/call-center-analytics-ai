# Ajan ve LLM dayanıklılık ölçümü (#216, #151)

**Tarih:** 2026-11-02 · **LLM:** NVIDIA Nemotron 3.5 (ücretsiz katman; hızlı `lightning-30b`, güçlü `super-120b`) · **Betikler:** `backend/scripts/dayaniklilik.py`, `backend/scripts/sayisal_tutarlilik.py`

Ölçümler gerçek hatta yapıldı: API → Celery işçisi → LangGraph ajanları → NVIDIA. Ortak veritabanı kirlenmesin diye çağrılar ayrı bir veritabanına (`call_center_loadtest`) ve ayrı Redis veritabanına (db 1) yazıldı. İşçi, Windows geliştirme düzeniyle aynı: `--pool=solo` (aynı anda tek görev). Ayarlar: `LLM_MAX_CONCURRENCY=2`, `LLM_REQUESTS_PER_MINUTE=30`, istek zaman aşımı 30 sn, ajan bütçesi 90 sn.

## 1. Güvenilirlik: toplu çalıştırma (#151, #216)

| Koşu | Çağrı | Tamam | Kısmi / başarısız | Toplam süre p50 / p95 / maks | Duvar saati |
|---|---|---|---|---|---|
| Pilot: metin, 4 paralel | 10 | 10 | 0 | 31,5 / 38,8 / 39,5 sn | 89 sn |
| Toplu: metin, 10 paralel | 40 | 40 | 0 | 58,3 / 76,4 / 78,8 sn | 252 sn |
| Ses (STT `base`), 3 paralel | 5 | 5 | 0 | 28,0 / 33,2 / 34,1 sn | 56 sn |
| Bozuk ses (geçersiz wav) | 1 | 0 | 1 başarısız (beklenen) | 21,1 sn | — |

**Hatasız tamamlanma: 55/55 geçerli çağrı (%100); hedef ≥ %95 sağlandı.** 30 çağrı koşulu 40 çağrıyla aşıldı.

- Toplam süre büyük ölçüde **işçi kuyruğunda bekleme**dir (tek işçi, tek görev): 40 çağrı 6,3 sn/çağrı hızla eritildi; kuyruğa 40 çağrı birden girince son çağrı ~79 sn bekledi. Bekleme dışında analiz tek başına p50 ≈ 5,4 sn.
- Ajan süreleri (40 çağrı, p50 / p95 / maks): sınıflandırma 1,7 / 3,5 / 6,7 · CRM 2,0 / 4,2 / 14,2 · satış 1,8 / 6,4 / 10,6 · özet 4,4 / 6,3 / 9,8 sn. Dördü paralel çalıştığı için çağrı süresi en yavaş ajan kadardır.
- Yeniden deneme: 50 metin çağrısında 9 ajan çalışması (7'si **özetleyici**) ilk cevabı şemaya uymadığı için bir düzeltme turu aldı; zaman aşımına uğrayan ajan **yok**. Toplam ≈ 530 bin token (çağrı başına ≈ 9,6 bin).
- **Yedek modele geçiş çok sık:** hızlı modelle çalışan 100 ajan çalışmasının **39'u (%39)** hızlı modelden 429 aldı ve güçlü modele (yedek) geçip tamamlandı (sınıflandırma 22, özet 17; işçi günlüğünde 86 adet `429 Too Many Requests`). Sonuç yine hatasızdı, ama kota sınırına yaslanıldığını gösterir. Aynı anahtarı başka bir oturum da kullanıyorsa pay paylaşılır. Betik çıktısındaki "yedek modele geçen" sayısı bu yüzden 0 görünür: **`fallback_from` veritabanına yazılmıyor** (yalnızca `model` sütunu hangi modelin cevap verdiğini gösterir; bu tablo ona bakılarak çıkarıldı).

### Uçtan uca süre (hedef: 5 dk'lık çağrı için yükleme → sonuç ≤ 3 dk)

| Aşama | Ölçüm |
|---|---|
| STT (`base`, int8, CPU; ~3 dk'lık sentetik ses, mono) | 3,8–5,9 sn (RTF ≈ 0,02–0,03) |
| STT (`small`, projenin seçtiği) | **Bu makinede ölçülemedi:** model yüklenirken `mkl_malloc: failed to allocate memory` (RAM kısıtlı; aynı hata ana kopyanın sanal ortamında da çıkıyor). Önceki ölçüm (`docs/stt_karari.md`): RTF 0,2–0,3 → 5 dk ≈ 60–90 sn |
| LLM analizi (kuyruk yok) | p50 5,4 sn, p95 ≈ 10 sn |
| Kaydetme + eşleştirme | < 1 sn |

5 dk'lık bir çağrı için beklenen toplam: kuyruk (boşsa 0) + STT 60–90 sn (`small`) + analiz ~10 sn ≈ **1,5–2 dk < 3 dk**. Kuyrukta başka iş varsa süre o kadar uzar; tek işçi ile 3 dk'yı aşmamak için aynı anda ~20 analizden fazla kuyruğa girmemeli (aşağıdaki öneri 2).

## 2. Sayısal soru tutarlılığı (#151)

`scripts/sayisal_tutarlilik.py`: 7 gerçek tekne sahibi için gider toplamı, "bu ay" gideri ve kalan bakım hakkı soruları sorulur; sohbet cevabındaki sayı, asistan koduna dokunmayan **ham SQL** ile karşılaştırılır.

**20/20 soruda sohbet cevabı = SQL sonucu (%100).** (Sayıları kod hesaplar; LLM yalnızca soruyu araca eşler, 20 soruda yanlış eşleme çıkmadı.) Not: yönetici KPI panelinde tekne sahibi gideri ve paket hakkı yoktur; panel karşılaştırması yalnızca çağrı sayıları için anlamlıdır ve onlar `analytics_service` testleriyle SQL'e bağlıdır.

## 3. Hata senaryoları

Kullanıcı = çağrı detayında görünen `calls.error`. "Sahte sunucu" = yerel OpenAI-uyumlu sunucu. Süre = yüklemeden çağrının son durumuna.

| Senaryo | Süre | Çağrı durumu | Kullanıcı ne görür | Not |
|---|---|---|---|---|
| Boş API anahtarı | 0,8 sn | `basarisiz` | "LLM yapılandırılmadı: LLM_API_KEY tanımlı değil (.env)" | Hemen, ağ yok |
| Geçersiz API anahtarı (gerçek sağlayıcı) | 1,9 sn | `basarisiz` | `OpenAIPermissionDeniedError: Error code: 403 - {...}` | NVIDIA 401 değil **403** döner; yedek model denenmez (kalıcı hata) |
| Ağ kesintisi: bağlantı reddi | 18,8 sn | `basarisiz` | "Connection error." (yedek model de) | Windows'ta reddedilen bağlantı yeniden denemelerle 13–18 sn sürdü |
| Ağ kesintisi: paketler düşüyor | 90,8 sn | `basarisiz` | "Süre sınırı aşıldı (90 sn)" | Dört ajan da bütçeyi bitirdi |
| Model yanıt vermiyor | 91,8 sn | `basarisiz` | "Süre sınırı aşıldı (90 sn)" | İstek zaman aşımı 30 sn × 2 deneme; eşzamanlılık 2 olduğu için ajanlar sırada beklediğinden yedek modele sıra gelmedi |
| 429, Retry-After: 1 (sürekli) — **eski** | 4,7 sn | `basarisiz` | `OpenAIRateLimitError: Error code: 429` | SDK 1 kez denedi, yedek model de 429 → pes |
| 429, Retry-After: 1 (sürekli) — **#221 sonrası** | 17,9 sn | `basarisiz` | aynı | 3 kez bekleyip denedi (günlükte `agent.rate_limit_backoff`) |
| 429, Retry-After: 30 (sürekli) | 90,7 sn | `basarisiz` | "Süre sınırı aşıldı (90 sn)" | SDK'nın 30 sn'lik beklemesi eşzamanlılık yuvasını tuttu |
| 429 ilk 2 istekte, sonra normal | 3,0 sn | tamam (sahte sunucu yalnızca sınıflandırma için geçerli JSON verir) | — | SDK'nın tek yeniden denemesi Retry-After'a uyup kurtardı |
| Sağlayıcı 500 | 11,5 sn | `basarisiz` | `OpenAIAPIError: Error code: 500` | İstek başına 4 deneme (SDK 2 × birincil/yedek) |
| Model yok (404) | 0,7 sn | `basarisiz` | `OpenAIModelNotFoundError: 404` | Yedek model denendi |
| LLM düz yazı / boş / yarım JSON | 0,6–0,7 sn | `basarisiz` | "Cevapta JSON nesnesi bulunamadı." | Her ajan 1 düzeltme turu (2 deneme) alır |
| LLM geçerli JSON ama şemaya uymuyor | 0,9 sn | **`kismi`** | — (`errors`: "Field required") | **Dikkat:** CRM şemasının tüm alanları isteğe bağlı olduğundan `{"tip":"servis"}` gibi alakasız bir JSON "başarılı" sayılıp **boş CRM kaydı** olarak kaydedildi |
| ~30 bin karakter transkript | 5,1 sn | `tamam` | — | Sorun yok |
| ~600 bin karakter transkript | 30,3 sn | `tamam` | — | Sağlayıcı kabul etti (çok token); üst sınır yok |
| Bozuk ses | 21 sn (kuyruk dahil; STT 3,4 sn) | `basarisiz` | "Yazıya çevirme başarısız: Ses çözümlenemedi: …" | **Düzeltildi (#221):** ileti sunucu dosya yolunu içeriyordu |
| STT modeli belleğe sığmıyor (`small`) | 5–9 sn | `basarisiz` | `RuntimeError: mkl_malloc: failed to allocate memory` | Çağrı kaybolmadı; "Yeniden Analiz Et" ile `base` modelle tamamlandı |

### Takılı çağrı kurtarma (#107)

| Deney | Sonuç |
|---|---|
| `beklemede` / `yaziya_cevriliyor` / `isleniyor` durumunda 30 dk hareketsiz çağrı | 1. taramada `beklemede` + "yeniden deneniyor (deneme 1)" ve görev kuyruğa alınır; 2. taramada `basarisiz` + "İşlem zaman aşımına uğradı, yeniden deneyin". Üç durumda da aynı |
| **Gerçek:** işçi analiz ortasında öldürüldü (`isleniyor`) | Çağrı `isleniyor`da kaldı (kayıp değil, ama kullanıcı takıldı); kurtarma taraması çağrıyı yeniden kuyruğa aldı, yeni işçi 7,5 sn'de `tamam` yaptı |
| Kurtarma sırasında yeniden analiz isteği | #218 ile ikinci görev açılmaz (`already_running`); testi `tests/test_call_ingest_integration.py` |

Kurtarma taraması varsayılan olarak 10 dk hareketsizlik sonrası çalışır ve Beat gerektirir (`scripts.dev` Beat'i açar; elle `celery worker` açılırsa yalnızca işçi başlangıcında bir kez taranır).

## 4. Kota (rate limit) davranışı

`python -m scripts.dayaniklilik kota` ile gerçek sağlayıcıda sondalandı (hızlı model, 5 token'lık istek):

| Deneme | Sonuç |
|---|---|
| 1 istek/0,8 sn, 90 sn | İlk dakikada 39 başarılı, sonra 429; ikinci dakikada 26 başarılı + 19 429 → kota **≈ 40 istek/dk** (kayan pencere) |
| 4 eşzamanlı, 70 sn | 8. istekte 429 (diğer oturumların kotası da payı yer) |
| Başarılı istek gecikmesi | p50 0,24–0,35 sn, p95 0,6–1,1 sn (kısa istek) |
| 429 yanıt başlıkları | `Retry-After` ve `X-RateLimit-*` **yok** → bekleme süresi tahmin edilmeli |

Bir çağrı analizi 4 istektir. Kota 40 istek/dk, uygulama sınırı 30 istek/dk (`LLM_REQUESTS_PER_MINUTE`) → **dakikada en çok ~7 çağrı** işlenebilir (sınır ve kota işçi başına/anahtar başınadır; birden çok işçi ya da başka bir iş aynı anahtarı kullanırsa 429 görülür). Toplu koşularda hızlı model sık 429 verdi (yukarıda %39); uygulama sınırı 30/dk olmasına rağmen sağlayıcı daha erken kesti (kısa süreli patlama sınırı ya da başka oturumların aynı anahtardan istek atması olası). Yedek model (güçlü, ayrı kota) bunu karşıladı; #221'deki bekle-ve-yeniden-dene yedeğe geçmeden önce kısa süre bekler.

## 5. Bulgular ve öneriler

| # | Bulgu | Önem | Durum / öneri |
|---|---|---|---|
| 1 | 429'da ajan ~5 sn içinde pes ediyor; Retry-After yok | Yüksek | **Düzeltildi (#221):** bekle-ve-yeniden-dene (4/8/16 sn + pay, tavan 30 sn, 3 kez; `LLM_RATE_LIMIT_RETRIES`, `LLM_RATE_LIMIT_BACKOFF_S`) |
| 2 | Tek işçi (`--pool=solo`) tüm çağrıları sıraya dizer; STT sırasında analiz de bekler | Orta | Sunumda `docker compose --profile app` (prefork) kullanın ya da `-c 4 --pool=threads`; STT için ayrı işçi (`-Q stt -c 1`) ve analiz için ayrı işçi (`-Q analysis`) açın |
| 3 | `calls.error` ham sağlayıcı iletisi (İngilizce/JSON) gösteriyor | Orta | Türkçe, anlaşılır ileti (ör. "Yapay zekâ servisi şu an yanıt vermiyor, biraz sonra yeniden deneyin") + ayrıntı yalnızca `agent_runs`'ta; **ayrı issue önerilir** |
| 4 | Tüm alanları isteğe bağlı CRM şeması alakasız JSON'u "başarılı" sayıyor (sessiz boş sonuç) | Orta | `CrmExtraction` için "en az bir alan dolu" doğrulaması; **ayrı issue önerilir** (ajan alanı) |
| 5 | Semafor, SDK'nın kendi Retry-After uykusunu da tutuyor | Düşük | `LLM_MAX_RETRIES=0` ve beklemeyi ajan katmanında yapmak (kısmen #221'de) |
| 6 | Model yanıt vermezse eşzamanlılık 2 olduğundan ajanlar sırada bekliyor, yedek modele sıra gelmeden 90 sn doluyor | Düşük | Ajan bütçesini 120 sn yapmak ya da `LLM_TIMEOUT_S`'yi 20 sn'ye çekmek |
| 7 | Bellek kısıtlı makinede `small` STT modeli yüklenemiyor (`mkl_malloc`) | Orta (ortama bağlı) | Sunumda `WHISPER_MODEL=base` yedeği; işçi RAM'ini ≥ 2 GB boş tutun |
| 8 | `task_acks_late` + Redis: öldürülen işçinin mesajı 1 saat (visibility timeout) sonra yeniden teslim edilebilir; çağrı arada kurtarıldıysa aynı çağrı ikinci kez analiz edilir (yeni sürüm) | Düşük | Zararsız ama gereksiz LLM kullanımı; görevin başında çağrı zaten `tamam` ise atlamak |
| 9 | `agent_runs.fallback_from` yazılmıyor; yedek modele ne sıklıkla geçildiği panelden/veritabanından görülemiyor | Düşük | `analysis_store` kaydına `fallback_from` eklenmeli (ek nullable sütun gerekirse migration) |
| 10 | Çağrı kaybolması (sessizce) | — | **Gözlenmedi:** her senaryoda çağrı `basarisiz`/`kismi`/`tamam` oldu; işçi ölümü kurtarma ile toparlandı |

## 6. Nasıl yeniden çalıştırılır

```
# Ayrı veritabanı ve Redis db 1; API 8100, işçi (WHISPER_MODEL=base gerekirse)
export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:15432/call_center_loadtest
export REDIS_URL=redis://localhost:6379/1
uv run alembic upgrade head
uv run uvicorn app.main:app --port 8100
uv run celery -A app.workers.celery_app worker -Q default,stt,analysis,index --pool=solo -l info

uv run python -m scripts.dayaniklilik batch --base-url http://localhost:8100 --text 40 --parallel 10
uv run python -m scripts.dayaniklilik batch --text 0 --audio 5 --bozuk-ses --audio-dir <seed ses klasörü> --parallel 3
uv run python -m scripts.dayaniklilik senaryo            # hata senaryoları (veritabanı adında "loadtest" şart)
uv run python -m scripts.dayaniklilik kota --seconds 90 --concurrency 1 --gap 0.8
uv run python -m scripts.dayaniklilik kurtarma
uv run python -m scripts.sayisal_tutarlilik --questions 20   # ortak veritabanında yalnızca okur
```
