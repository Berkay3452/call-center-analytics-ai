# Kara kutu QA turu: otomatik güvenlik turu raporu (#320, #338)

**Tarih:** 2026-11-20 · **Araç:** `backend/scripts/qa_kara_kutu.py` (+ schemathesis, pip-audit, npm audit, detect-secrets)

## 1. Yöntem: neden pytest değil

`backend/tests/security/` paketi (390 test) uygulamayı **içeriden**, sahte bağımlılıklarla dener ve her CI'da zaten geçer. Aynı dosyaları tekrar koşmak yeni bilgi vermez. Bu turda bir QA mühendisi/sızma testçisi gibi **dışarıdan**, çalışan bir sunucuya gerçek HTTP ile gidildi.

| Yöntem | Ne yapar | Pytest'ten farkı |
|---|---|---|
| **İzole canlı ortam** | Ayrı veritabanı (`qa_blackbox`), sahte LLM (`scripts/fake_llm.py`), `APP_ENV=prod`, imzalı kimlik zorunlu, test anahtarları | Canlıya en yakın ayar; geliştirme verisine ve anahtarlarına dokunulmaz |
| **Tüm uçlarda yetki matrisi** | 34 işlem × 9 kimlik biçimi (anahtarsız, uzatılmış, kısaltılmış, imzasız, eski, başkasının, servis anahtarıyla imza...) | Uç listesi OpenAPI'den çıkar; yeni uç otomatik kapsanır |
| **Şema tabanlı fuzzing (schemathesis)** | OpenAPI'den on binlerce uç/bozuk girdi üretir, 5xx ve şema uyumsuzluğu arar | İnsanın aklına gelmeyen girdiler (NUL, yıl 1/9999, 30 haneli sayı, surrogate) |
| **Saldırgan senaryoları** | Sahip A, sahip B'nin verisini asistandan çıkarmaya çalışır; ses yükleme suistimali; SSE izleyici sınırı; kilitlenme | Gerçek sunucu, gerçek ağ, gerçek sınırlayıcı |
| **Taramalar** | pip-audit, npm audit, detect-secrets (+ git geçmişi), injection ölçümlerinin tekrarı | Bağımlılık ve sır hijyeni, gerileme karşılaştırması |

Ortamı yeniden kurmak için: ayrı bir veritabanı oluşturup `alembic upgrade head` + `python -m scripts.seed` çalıştırın, `APP_ENV=prod` ve 32+ karakterlik `SERVICE_API_KEY` / `USER_SIGNING_KEY` ile API'yi açın, sonra:

```
python -m scripts.qa_kara_kutu --base-url http://127.0.0.1:18765 --spec openapi.json
```

`--spec`: prod'da `/openapi.json` kapalı olduğundan şema `app.openapi()` ile dosyaya yazılır. `--hiz-siniri` IP'yi 60 sn kilitler, ayrı çalıştırın. **Yalnızca izole, sentetik veritabanına karşı** çalıştırın; yazma uçlarına kayıt bırakır.

## 2. Sonuç özeti

| Alan | Sonuç |
|---|---|
| Kara kutu betiği (39 kontrol) | **39/39 geçti** (düzeltmeden önceki keşif denemeleri aynı kontrollerle 15 adet 500'ü ve eşleştirme hatasını göstermişti; betik düzeltmeden sonra derlendi) |
| schemathesis, fuzzing | tur 1: 281 istek; tur 2: 3 604 istek, **3 sunucu hatası**; düzeltme sonrası: **11 316 istek, 0 sunucu hatası** |
| Tam pytest (CI ile aynı) | 2 374 geçti |
| Tam pytest + gerçek DB (`RUN_DB_TESTS=1`, **temiz** veritabanı + seed) | **2 569 geçti, 0 kaldı**, 6 atlandı (CI/ses/POSIX), 2 bilinen sınırlama (xfail) |
| Injection ölçümü (kural katmanı) | önceki ölçümle **aynı**: kesin ret 96/128 (%75), ret+şüpheli 128/128, yanlış pozitif 0/128 |
| Dolaylı injection | önceki ölçümle **aynı**: ayarlanmamış taze küme %60 (BS-1), kalan kümeler %100, yanlış pozitif 0 |
| pip-audit (`requirements.txt`) | bilinen açık yok |
| npm audit | çalışma zamanı bağımlılıkları: **0**; yalnız geliştirme araçlarında 8 (7 orta, 1 yüksek: `zod` bellek tüketimi, eslint zincirinde) |
| Sır taraması (detect-secrets + 536 commit geçmişinde anahtar kalıbı araması) | gerçek sır yok; 18 uyarının tümü örnek/test değeri (`postgres`, `change-me-in-local-env`, `duman-test-anahtari`, test sabitleri) |
| Canlı uç denemeleri | 401, 403, 413, 415, 409, 429 (+`Retry-After`), güvenlik başlıkları, CORS, SSE yetkisi ve 5 izleyici sınırı, denetim günlüğü **beklendiği gibi** |

## 3. Bulgular (düzeltildi)

| # | Ciddiyet | Bulgu | Nasıl bulundu | Düzeltme |
|---|---|---|---|---|
| B1 | **Orta** | `PUT /calls/{id}/match` (elle eşleştirme) **her çağrıda 500** veriyordu (`MissingGreenlet`): `updated_at` sunucuda üretilen bir değer, güncellemeden sonra async oturumda yeniden okunamıyordu | Kara kutuda 3 denemenin 3'ü 500; temiz DB turunda aynı testler kırmızıydı. CI'da koşmayan DB testleri bunu gizlemişti | `Call`, `CrmReview`, `ChatSession` modellerine `eager_defaults` (değer RETURNING ile alınır) |
| B2 | Düşük-orta | **NUL karakteri** (`\x00`) 500 veriyordu: `q`/`marina` filtreleri (4 uç), çağrı oluşturma ve ses formu alanları, CRM notları, `chat/messages`. Asistan akışında 200 + `internal_error` olayı | schemathesis ve elle NUL denemesi | `SafeStr` türü ile şemada 422; veritabanı veri hatası için genel 422 işleyici (güvenlik ağı) |
| B3 | Düşük | Uç tarihler (`0001-01-01`, `9999-12-31`) 5 uçta 500: `analytics/summary`, `calls`, `crm`, `service-orders`, `audit-log` (`OverflowError`) | schemathesis | `SaneDate`/`SaneDateTime`: 2000-2100 yılları dışı 422 |
| B4 | Düşük | `duration_s`, `answer_delay_s`, `start_ms` için üst sınır yoktu: 30 haneli sayı `int4` taşmasıyla 500 | schemathesis (`POST /calls`) | `Seconds` (en çok 86 400) ve `Millis` türleri |
| B5 | Düşük | `POST /calls/audio` form alanları elle modele çevrildiğinden doğrulama hatası `RequestValidationError` olmayıp 500 oluyordu | B2/B4'ü ses ucunda denerken | `ValidationError` yakalanıp aynı 422 gövdesi |
| B6 | Düşük | Ad alanlarında uzunluk sınırı yoktu (100 KB `customer_name` kabul ediliyordu); `started_at` yıl 1/9999 kabul ediliyordu | Yükleme suistimali denemesi | `NameStr` (en çok 200 karakter), `SaneDateTime` |
| B7 | Düşük | Kimlikli API yanıtlarında `Cache-Control: no-store` yoktu (kişisel veri içeren JSON ara önbelleğe düşebilirdi) | Başlık denetimi | `SecurityHeadersMiddleware`'e eklendi |

Test sağlığı: `PUT /match` kırığı (B1) dışında, DB'ye bağlı iki test **zamana/duruma bağlı çürümüştü** (`Bu ay ne kadar harcadım?` seed'deki 1 Ekim giderine, bekleyen CRM listesi tek sayfaya bağlıydı); ikisi deterministik hale getirildi. Üçü de değişikliğimden önce `main`'de de kırmızıydı.

Regresyon: `backend/tests/test_girdi_sertlestirme.py` (37 test) bulguları sunucusuz sabitler.

## 4. Gözlemler (hata değil, bilmekte fayda var)

- **Hız sınırı kilidi doğru anahtarı da engeller** (IP başına 10 hatalı denemeden sonra 60 sn). Beklenen davranış; yalnızca güvenilir proxy arkasında gerçek istemci IP'si doğru iletilmezse tüm kullanıcıları etkiler. Canlıda proxy'nin `X-Forwarded-For` ayarı ve uvicorn `--forwarded-allow-ips` birlikte doğrulanmalı (#321).
- **uvicorn varsayılanı loopback'ten gelen `X-Forwarded-For`'a güvenir.** Yerel testte bu başlıkla IP sınırı aşılabilir görünür; ağdan doğrudan erişimde başlık yok sayılır. Canlıda arka uç yalnızca proxy'ye açık olmalı.
- **`/health/ready` kimliksizdir ve bileşen durumunu (veritabanı/Redis) gösterir.** Yük dengeleyici için bilinçli; gizli değer yok.
- **Windows'ta `localhost` önce IPv6'yı dener.** Docker yalnız IPv4 dinlerse her yeni veritabanı bağlantısı ~2 sn gecikir (`/health/ready` 2 sn zaman aşımı ile "degraded" gösterdi). Yerelde `DATABASE_URL` için `127.0.0.1` kullanın.
- schemathesis `ST103` (belgelenmemiş 400/401/403/404/429) ve `ST202` (başlık biçimleri) uyarıları **OpenAPI belgesinin eksikliğidir**, güvenlik açığı değil; hata yanıtlarını şemaya eklemek ayrı, düşük öncelikli bir iyileştirmedir.
- İlk koşuda yan etki: izole API'nin Celery aracısı kullanıcının Redis'ine (db 0) bağlıydı; çalışan işçi 5 sahte görevi "bulunamadı" diye tüketti (zararsız, sonuç anahtarları 1 gün içinde silinir). Sonraki koşular ayrı Redis veritabanıyla yapıldı.

## 5. Yapılamayanlar ve nedenleri

| Madde | Durum |
|---|---|
| Tarayıcıyla arayüz turu | Frontend çalışmıyordu (`:3000`), `.next` derlemesi 11 Kasım'dan kalma; eski derlemeyle test yanıltıcı olurdu. **#339 (manuel kontrol listesi)** kapsamına bırakıldı. |
| Gerçek LLM ile injection yakalama (`--llm`) | Ücretsiz kota ve gerçek anahtar gerekir; çalıştırılmadı. Kural katmanı ölçümü gerilemedi. |
| gitleaks | İkili dosya kurulu değil, indirme yapılmadı; yerine detect-secrets ve geçmişte anahtar kalıbı araması kullanıldı. CI'daki gitleaks iş akışı zaten çalışıyor. |
| Yük/DoS | Bu makinede ağır yük denenmedi (bellek). Hız sınırı ve gövde sınırı doğrulandı. |

## 6. Berkay için kısa manuel kontrol listesi (#339'a girdi)

| Perspektif | Adım | Beklenen |
|---|---|---|
| Tekne sahibi | Miço AI'a başka bir müşterinin adını/telefonunu sor | "Başka müşterilerin bilgilerini paylaşamam" benzeri ret, kaynak kartı yok |
| Tekne sahibi | Adres çubuğundan `/admin` sayfalarına git | Yönetici ekranı açılmaz / yönlendirilir |
| Yönetici | Çağrı listesinde filtre kutusuna `a%00b`, çok uzun metin ve emoji yaz | Hata sayfası değil, boş liste veya anlaşılır uyarı |
| Yönetici | Çağrı ayrıntısında müşteri/tekneyi **elle eşleştir** (B1 düzeltmesi) | Kaydedilir, "elle" yöntemi görünür; önceden hata veriyordu |
| Yönetici | CRM'de bir kaydı onayla, sonra yeniden analiz et | Durum "bekliyor"a döner, servis emri bağlantısı sıfırlanır |
| Yönetici | 25 MB üstü ses ve `.exe` adını `.wav` yapıp yükle | 413 / 415 iletisi, kayıt oluşmaz |
| Yönetici | Aynı ses dosyasını iki kez yükle | "Daha önce yüklendi" (409), mevcut çağrıya bağlantı |
| Yönetici | Canlı transkript penceresini aynı çağrı için 6 sekmede aç | 6.'da "çok fazla izleyici" iletisi; sekme kapatınca yenisi açılır |
| Yönetici | Denetim günlüğü ekranında başarısız giriş ve yükleme olaylarına bak | Olaylar var; anahtar, kimlik değeri, ham metin yok |

## 7. Nasıl tekrar çalıştırılır

```
cd backend
python -m scripts.qa_kara_kutu --base-url http://127.0.0.1:18765 --spec openapi.json   # kara kutu
schemathesis run openapi.json --url http://127.0.0.1:18765 -H "X-Service-Key: $SERVICE_API_KEY" \
  --phases fuzzing --mode all --max-examples 400 --checks not_a_server_error,response_schema_conformance
python -m scripts.injection_olcum ; python -m scripts.dolayli_olcum                    # gerileme
```
