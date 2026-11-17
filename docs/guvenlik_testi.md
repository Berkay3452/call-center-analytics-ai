# Güvenlik doğrulama testleri ve saldırı senaryoları (#276)

**Tarih:** 2026-11-17 · **Paket:** `backend/tests/security/` · **Betik:** `backend/scripts/guvenlik_testi.py`

Amaç, güvenlik katmanının çalıştığını **kanıtlayan**, yeniden çalıştırılabilir bir saldırı paketidir. Her test saldırganın gözünden yazılmıştır (sahte anahtar, kimlik tahmini, gizlenmiş talimat, zehirli transkript, aşırı yük); savunma tutuyorsa geçer. Paket CI'daki `Testler (pytest)` işinde her PR'da çalışır (veritabanı gerektirmeyenler); sahip izolasyonu testleri `RUN_DB_TESTS=1` ile duman testi işinde gerçek veritabanıyla çalışır.

## 1. Tek komutla çalıştırma

```
cd backend
uv run python -m scripts.guvenlik_testi          # veritabanı gerektirmeyenler
uv run python -m scripts.guvenlik_testi --db     # + gerçek veritabanıyla sahip izolasyonu (RUN_DB_TESTS=1)
uv run python -m scripts.guvenlik_testi --markdown   # tabloyu Markdown olarak yazar
```

Çıkış kodu, kalan test yoksa 0'dır. "Sınırlama" sütunu, bilinen ve belgelenmiş açıkları gösteren `xfail(strict=True)` testlerdir: sınırlama giderilirse test kırılır ve belge güncellenmeye zorlanır.

## 2. Sonuç tablosu (2026-11-17, `--db` ile)

| Saldırı sınıfı | OWASP LLM | OWASP API | Geçti | Kaldı | Atlandı | Sınırlama |
|---|---|---|---|---|---|---|
| Kimlik doğrulama ve yetki yükseltme | LLM06 | API2, API5, API8 | 172 | 0 | 0 | 0 |
| Sahip izolasyonu (IDOR/BOLA) | LLM06, LLM02 | API1 | 14 | 0 | 0 | 0 |
| Prompt injection (doğrudan, gizlenmiş, dolaylı) ve çıktı sızıntısı | LLM01, LLM02, LLM07 | - | 55 | 0 | 0 | 1 |
| Kişisel veri (maskeleme) sızıntısı | LLM02 | API3 | 23 | 0 | 0 | 1 |
| Hız sınırı ve kaynak tüketimi | LLM10 | API4 | 14 | 0 | 0 | 0 |
| Yetkisiz araç / aşırı yetki | LLM06 | API5 | 24 | 0 | 0 | 0 |
| Yazma uçlarında işlev düzeyi yetki | LLM06 | API5 | 2 | 0 | 0 | 0 |
| Eşleme tablosunun doğruluğu | - | - | 23 | 0 | 0 | 0 |
| **Toplam** |  |  | 327 | 0 | 0 | 2 |

`--db` olmadan sahip izolasyonu satırı atlanır (14 test "atlandı" görünür). Önceden var olan testler (`test_authorization_matrix.py` 83, `test_injection.py`, `test_indirect_injection.py`, `test_yetki_siniri.py`, `test_protection.py` vb.) bu tabloya dahil değildir; bu paket onların **üstüne** taze saldırılar ekler. Prompt injection ve dolaylı injection için ölçülen yakalama oranları: `docs/injection_olcum.md`, `docs/dolayli_injection_olcum.md`.

### Saldırı paketinin içeriği

| Modül | Denenen saldırılar |
|---|---|
| `test_kimlik_saldirilari.py` | 20 sahte/değiştirilmiş anahtar × 6 uç; anahtarı sorgu/çerez/Bearer/uzantılı başlıktan gönderme; olağandışı HTTP yöntemleri; 14 sahte `X-User-Id` (SQL, yol gezinmesi, çoklu kimlik, 5000 karakter); sahip kimliğiyle yönetici uçları; kaba kuvvet ve kilitlenme; hata gövdesinde iç bilgi/anahtar yansıması; kimliksiz erişilebilen uç taraması; prod'da `/docs` ve `/openapi.json` |
| `test_sahip_izolasyonu_integration.py` | Başkasının oturumunu okuma/silme/devam ettirme (iki uç ailesi), var olmayan ile başkasının oturumunun aynı 404'ü vermesi, toplu silme, gövdeye sahte `owner_id`/`ownerId`/`user_id`, başkasının teknesi için araçlar, sayfalama suistimali |
| `test_prompt_injection_saldirilari.py` | 17 taze doğrudan saldırı; 8 kodlama (base64, hex, rot13, harf arası boşluk, sıfır genişlikli karakter, Kiril homoglif, büyük harf, URL) × 2 yük; çok turlu bölünmüş saldırı; zehirli transkript ve sınırlayıcıdan kaçış; çıktıda sistem istemi/anahtar/IBAN/kimlik/kart sızıntısı |
| `test_maskeleme_sizinti.py` | 15 alışılmadık biçimde kişisel veri (telefon, TC, IBAN, kart, e-posta, plaka, pasaport), ayırıcı çeşitleri, ad kalıpları, idempotans |
| `test_hiz_siniri_ve_kaynak_tuketimi.py` | `X-Forwarded-For`/`X-Real-IP`/`Forwarded`/`CF-Connecting-IP` ile IP sınırını atlatma, kimlik döndürme, aşırı büyük/bozuk gövde, geçersiz soru alanları |
| `test_yetkisiz_arac_kullanimi.py` | İzin listesi dışı araç, sahip seçtiren alan yokluğu, boş sahip, kimlik alanında SQL/şablon enjeksiyonu, yazma işlevi yokluğu, modele araç bağlanmaması, ajanların yazma katmanını içe aktarmaması |
| `test_yetki_haritasi.py` | Durum değiştiren her ucun hangi kimlik bağımlılığını istediği; belgelenmemiş yeni açık uç testi kırar |
| `test_owasp_eslesmesi.py` | Aşağıdaki eşleme tablolarındaki her dosya yolunun gerçekten var olması |

## 3. OWASP Top 10 for LLM Applications (2025) eşlemesi

| Madde | Savunma (kod) | Kanıt (test) |
|---|---|---|
| LLM01 Prompt injection | `backend/app/assistant/injection.py` (normalizasyon, kodlama çözme, kural + LLM sınıflandırıcı), `backend/app/security/untrusted.py` (dolaylı: tarama, sınırlayıcı) | `backend/tests/security/test_prompt_injection_saldirilari.py`, `backend/tests/test_injection.py`, `backend/tests/test_indirect_injection.py` |
| LLM02 Hassas bilgi ifşası | `backend/app/services/masking.py` (LLM'e giden metin maskeli), `backend/app/security/untrusted.py` (`output_leaks`: çıktı denetimi) | `backend/tests/security/test_maskeleme_sizinti.py`, `backend/tests/test_masking_olcum.py` |
| LLM03 Tedarik zinciri | `.github/workflows/backend-ci.yml` (pip-audit), `.github/workflows/gizli-anahtar-taramasi.yml`, `.github/workflows/imaj-taramasi.yml`, `.github/dependabot.yml` | `backend/tests/test_secret_hygiene.py` |
| LLM04 Veri ve model zehirleme | Eğitim yok; kayıtlardan (transkript, usta notu) gelen zehirli içerik veri bloğuna hapsedilir: `backend/app/security/untrusted.py`, `backend/app/agents/llm_agent.py` | `backend/tests/test_indirect_injection.py` |
| LLM05 Uygunsuz çıktı işleme | LLM çıktısı şemayla doğrulanır, ham metin yürütülmez: `backend/app/schemas/analysis.py`, `backend/app/assistant/answer.py` | `backend/tests/test_analysis_schemas.py`, `backend/tests/test_indirect_injection.py` |
| LLM06 Aşırı yetki | İzin listesindeki 5 salt-okunur araç, sahip kodda zorunlu: `backend/app/assistant/tools.py`, `backend/app/assistant/planner.py`; modele araç bağlanmaz | `backend/tests/security/test_yetkisiz_arac_kullanimi.py`, `backend/tests/security/test_sahip_izolasyonu_integration.py`, `backend/tests/test_yetki_siniri.py` |
| LLM07 Sistem istemi sızıntısı | İstem parçaları çıktıda aranır: `backend/app/security/untrusted.py`; istemler `backend/app/assistant/prompts/` | `backend/tests/security/test_prompt_injection_saldirilari.py` |
| LLM08 Vektör/gömme zayıflıkları | Arama yalnızca sahibin kayıtlarında: `backend/app/assistant/retrieval.py`; zehirli not alıntılanamaz | `backend/tests/test_indirect_injection.py`, `backend/tests/test_assistant_history_integration.py` |
| LLM09 Yanlış bilgi | Sayıyı araç hesaplar, kaynak yoksa "bulamadım": `backend/app/assistant/grounding.py`, `backend/app/agents/grounding.py` | `backend/tests/test_assistant.py`, `backend/tests/test_agent_quality.py` |
| LLM10 Sınırsız tüketim | Hız sınırı (kimlik + IP), gövde sınırı, soru uzunluğu 5000: `backend/app/core/protection.py`, `backend/app/core/ratelimit.py` | `backend/tests/security/test_hiz_siniri_ve_kaynak_tuketimi.py`, `backend/tests/test_protection.py` |

## 4. OWASP API Security Top 10 (2023) eşlemesi

| Madde | Savunma (kod) | Kanıt (test) |
|---|---|---|
| API1 Nesne düzeyi yetki (BOLA) | Her sorguda `owner_id`; başkasının oturumu 404: `backend/app/services/assistant_chat.py` | `backend/tests/security/test_sahip_izolasyonu_integration.py`, `backend/tests/test_assistant_chat_integration.py` |
| API2 Bozuk kimlik doğrulama | Sabit zamanlı servis anahtarı, yalnızca başlık, hatalı denemede kilit: `backend/app/core/security.py`, `backend/app/api/deps.py` | `backend/tests/security/test_kimlik_saldirilari.py`, `backend/tests/test_authorization_matrix.py` |
| API3 Nesne özelliği düzeyi yetki | Yanıtlar `response_model` ile süzülür; gövdedeki `owner_id` yok sayılır: `backend/app/schemas/api.py` | `backend/tests/security/test_sahip_izolasyonu_integration.py`, `backend/tests/test_api_contract.py` |
| API4 Sınırsız kaynak tüketimi | `backend/app/core/protection.py`, `backend/app/core/ratelimit.py`; ses 25 MB sınırı: `backend/app/storage/audio_validation.py` | `backend/tests/security/test_hiz_siniri_ve_kaynak_tuketimi.py`, `backend/tests/test_audio_validation.py` |
| API5 İşlev düzeyi yetki (BFLA) | `require_admin`: `backend/app/api/deps.py`; **kısmi**, bkz. §6 BS-1 | `backend/tests/security/test_kimlik_saldirilari.py`, `backend/tests/security/test_yetki_haritasi.py` |
| API6 Hassas iş akışlarına sınırsız erişim | Asistan uçları için daha sıkı sınır; aynı ses 409: `backend/app/core/protection.py` | `backend/tests/test_protection.py`, `backend/tests/test_audio_ingest.py` |
| API7 SSRF | Kullanıcı girdisiyle dış adres çağrılmaz; gömme/LLM/STT adresleri ortam yapılandırmasından gelir: `backend/app/rag/embedders.py` | `backend/tests/security/test_yetkisiz_arac_kullanimi.py` (`test_ssrf_surface_is_a_single_configured_http_client`) |
| API8 Güvenlik yanlış yapılandırması | Güvenlik başlıkları, CORS listesi, prod'da `/docs` ve `/openapi.json` kapalı, `AUTH_DEV_BYPASS` prod'da reddedilir: `backend/app/main.py`, `backend/app/core/config.py` | `backend/tests/security/test_kimlik_saldirilari.py`, `backend/tests/test_protection.py` |
| API9 Uç envanteri yönetimi | Tek sürüm öneki, OpenAPI belgesi prod'da kapalı; her uç kimlik testinden geçer: `docs/api.md` | `backend/tests/test_authorization_matrix.py`, `backend/tests/test_docs_consistency.py` |
| API10 API'lerin güvensiz tüketimi | LLM/STT yanıtı şemayla doğrulanır, hata ayrıntısı kullanıcıya gösterilmez: `backend/app/core/public_errors.py`, `backend/app/llm/client.py` | `backend/tests/test_protection.py`, `backend/tests/test_llm_resilience.py` |

## 5. Paketin bulduğu açıklar

| Bulgu | Durum |
|---|---|
| `/openapi.json` üretimde kimliksiz erişilebiliyordu (API8/API9: tüm uç envanteri ve şemalar görünüyordu; `/docs` kapalıydı ama şema açıktı) | **Düzeltildi** bu PR'da: `openapi_url` prod'da `None` (`backend/app/main.py`); test `test_api_docs_are_closed_in_production` |
| Durum değiştiren 7 uç yalnızca servis anahtarı ister; tekne sahibi kimliğiyle gelen çağrı da erişebilir | **Bilinen sınırlama BS-1** (rol sistemi #275'e bağlı) |

## 6. Bilinen sınırlamalar

| No | Sınırlama | Neden / azaltma | İzleme |
|---|---|---|---|
| BS-1 | `POST /calls`, `POST /calls/audio`, `POST /calls/{id}/analyze`, `PUT /calls/{id}/match`, `POST /crm/{id}/approve`, `POST /crm/{id}/reject`, `PATCH /service-orders/{id}/status` rol denetimi yapmaz: `X-User-Id` taşıyan servis çağrısı da yönetici işlemi yapabilir | Servis anahtarı yalnızca Miço Usta arka ucunda ve yönetici arayüzünün sunucu tarafında bulunur, tarayıcıya verilmez; yine de kimlik başlığı doğrulanmamıştır. Rol denetimi #275 ile gelecek | `backend/tests/security/test_yetki_haritasi.py` açık uç kümesini sabitler; #275 bir ucu kapatınca ya da yeni açık uç eklenince test kırılır |
| BS-2 | Kalıp dışı köşeli parantezli sahte yönerge (`[SİSTEM: ...]`) dolaylı injection taramasında işaretlenmez | Metin yine de sınırlayıcı içinde veri olarak sunulur ve model çıktısı şema + sızıntı denetiminden geçer; ayarlanmamış taze kümede ölçülen yakalama ≈ %60 (`docs/dolayli_injection_olcum.md`) | `test_known_gap_bracketed_fake_system_directive_is_not_scanned` (xfail, strict) |
| BS-3 | Yazıyla söylenen numaralar ("sıfır beş üç iki ...") ve kalıp dışı serbest adlar maskelenemez | Kural tabanlı maskeleme bilinçli olarak basittir; ayrıntı `docs/maskeleme_olcum.md` | `test_known_gap_numbers_spoken_as_words_are_not_masked` (xfail, strict) |
| BS-4 | Kimlik başlığı (`X-User-Id`) imzalı değildir: servis anahtarını ele geçiren biri her sahip adına konuşabilir | Servis anahtarı gizli tutulur (Secret Manager), kimlik hatası IP başına sınırlanır ve denetim günlüğüne yazılır; imzalı kimlik belirteci entegrasyonla birlikte düşünülecek | `docs/guvenlik_mimarisi.md` |
| BS-5 | Gerçek LLM ile uçtan uca injection denemesi CI'da yok (sahte model) | CI'da gerçek model çağrılmaz; gerçek model ölçümü elle: `python -m scripts.injection_olcum --llm`, `python -m scripts.dolayli_olcum` | `docs/injection_olcum.md` |
