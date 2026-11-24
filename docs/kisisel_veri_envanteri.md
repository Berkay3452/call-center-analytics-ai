# Kişisel veri envanteri ve saklama/silme politikası (#269)

Bu belge hangi tabloda ve dosyada hangi kişisel verinin durduğunu, ne kadar saklandığını ve nasıl
silindiğini listeler (KVKK madde 7: silme, yok etme, anonim hale getirme). Veri tipleri:
*doğrudan tanımlayıcı* (ad, telefon, e-posta), *içerik* (konuşma/sorular; içinde kişisel veri geçebilir),
*teknik* (IP, kimlik). Gerçek müşteri verisi bu depoda bulunmaz; örnek veri sentetiktir.

## 1. Envanter

| Yer | Alan | Tür | Maskeli mi? | Silinme yolu |
|---|---|---|---|---|
| Ses dosyası (`storage/audio`, GCS) | Ham konuşma sesi | İçerik, biyometrik olabilir | Hayır (ses maskelenemez) | Çağrı silinince dosya silinir |
| `calls` | `customer_name`, `customer_phone`, `boat_name`, `boat_model`, `marina` | Doğrudan tanımlayıcı | Hayır (işletme verisi) | Çağrı silinir |
| `transcripts` | `full_text` (ham), `masked_text` | İçerik | `masked_text` evet; `full_text` hayır | `calls` silinince CASCADE |
| `transcript_segments` | `text` (ham), `masked_text` | İçerik | `masked_text` evet; `text` hayır | `transcripts` CASCADE |
| `analysis_results` | Sınıflandırma, CRM çıkarımı (JSON) | Türetilmiş; maskeli metinden üretilir | Maskeli girdiden | `calls` CASCADE |
| `agent_runs` | Hata iletisi, model, süre | Teknik | — | `analysis_results` CASCADE |
| `crm_reviews` | `edited_fields`, `note` | İçerik (kullanıcı yazar) | Hayır | `calls` CASCADE |
| `service_orders` | Açıklama, tekne, müşteri bağı | İş kaydı | Hayır | **Silinmez**; `source_call_id` NULL olur (bkz. §3) |
| `customers` | Ad, telefon, e-posta, marina | Doğrudan tanımlayıcı | Hayır | Çağrı silme kapsamı dışı (§3) |
| `boats`, `boat_notes`, `expenses`, `subscriptions` | Tekne, not, gider, abonelik | İş kaydı | Hayır | Çağrı silme kapsamı dışı (§3) |
| `rag_chunks` | Tekne karnesi parçaları + embedding | İş kaydı içeriği | Hayır | Çağrıdan üretilmez; kaynak kayıt silinince (ayrı süreç) |
| `chat_sessions`, `chat_messages` | Asistana sorulan sorular ve cevaplar | İçerik | Hayır | Sahibi `DELETE /assistant/sessions...` ile siler (#176) |
| `owner_accounts` | Kullanıcı adı, parola özeti | Kimlik | — (parola düz değil) | Müşteri silinince CASCADE |
| `admin_accounts` | Kullanıcı adı, görünen ad, parola özeti | Kimlik | — (parola düz değil) | Yönetici hesabı kaldırılınca |
| `audit_log` | `actor_id`, `ip`, olay türü, kimlikler | Teknik; IP kişisel veri sayılabilir | Metin/PII yazılmaz (kodla zorunlu) | **Silinmez** (yalnızca ekleme; §4) |
| Uygulama günlükleri | İstek kimliği, durum | Teknik | Ham kişisel veri yazılmaz (#268 testi) | Günlük döndürme (altyapı) |

**Maskeli / ham ayrımı:** LLM ve RAG yalnızca `masked_text` görür (`app/services/masking.py`); ham metin
(`text`, `full_text`) yalnızca yönetici uçlarından okunur ve çağrı silinince gider.

## 2. Saklama süresi

- `RETENTION_DAYS` (varsayılan `0` = kapalı): çağrının `started_at` tarihinden bu kadar gün sonra çağrı,
  ses dosyası ve transkript otomatik silinir. Günlük Celery beat görevi `purge_expired_calls` çalışır;
  işlenmekte olan çağrılar atlanır; her silme `cagri_silindi` denetim olayı yazar (`neden=saklama_suresi`).
- Varsayılan kapalıdır, çünkü geliştirme ve seed verisi kendiliğinden silinmemelidir. **Canlıda süre
  işletme tarafından belirlenip verilmelidir** (hukuki gereklilik ve iş ihtiyacı: bu belge sayı
  önermez; yanlış bir sayı ya erken veri kaybı ya da gereksiz uzun saklama olur).
- `RETENTION_BATCH_SIZE` (200): bir çalışmada en çok bu kadar çağrı silinir; kalanı ertesi gün alınır.

## 3. Çağrı silme (`DELETE /api/v1/calls/{id}`)

Yalnızca yönetici bağlamı (servis anahtarı, `X-User-Id` yok; tekne sahibi kimliği 403). İşlem sırası:
tek veritabanı işleminde `cagri_silindi` olayı + `calls` satırı silinir (CASCADE: transkript, tur,
analiz, ajan kaydı, CRM önerisi), commit edilir, ardından ses dosyası silinir. İşlenmekte olan çağrı 409.

Silinmeyenler ve gerekçesi:

| Kayıt | Kural | Gerekçe |
|---|---|---|
| Servis emri | Kalır, `source_call_id` NULL | Servis emri işletmenin iş/muhasebe kaydıdır; çağrıdan bağımsız yaşar. Kayıttaki kişisel veriyi silmek ayrı bir müşteri silme talebidir. |
| CRM'e işlenmiş müşteri/tekne/not | Kalır | İşletmenin müşteri kaydıdır; çağrı silinince çağrıdan gelen öneri (`crm_reviews`) gider, onaylanıp işlenmiş kayıt gitmez. |
| Denetim günlüğü | Kalır | Eklemeli ve kişisel veri içermez (yalnızca çağrı kimliği ve sabit değer): "bu çağrı şu tarihte silindi" izi tutulur. |

**Bilinen sınırlar:** (1) Müşteri kaydının kendisini (ad, telefon) silen bir "müşteri silme" ucu bu işte
yoktur; müşteri silme talebi veritabanı yöneticisi eliyle yürür. (2) `audit_log` içindeki `ip` ve
`actor_id` silinemez (tetikleyici reddeder); IP'nin anonimleştirilmesi için yönetici tetikleyiciyi
geçici kapatan bir bakım işlemi gerekir, otomatiği yoktur. (3) Yedeklerden silme altyapının işidir;
yedek saklama süresi `RETENTION_DAYS` ile uyumlu seçilmelidir. (4) Silinen sesin nesne deposunda
sürüm/geri dönüşüm kutusu varsa orada da silinmelidir (GCS nesne sürümlemesi kapalı olmalıdır).

**Bilinen küçük sınırlar (izlenecek):** (5) `yaziya_cevriliyor`/`isleniyor` durumunda takılı kalan çağrı
saklama süresinde silinmez; takılı çağrılar `recover_stuck_calls` ile başarısız duruma düşünce
sonraki çalışmada silinir. (6) Durum denetimi ile silme arasında satır kilidi yoktur (küçük yarış);
işçi silinen çağrıya yazarsa FK hatası alır ve görev hata verir, veri sızmaz. (7) Ses silinemezse
yalnızca günlükte `call.delete.audio_orphan` kaydı olur; artık dosyaları süpüren bir görev yoktur.

## 4. Ham transkript için uygulama düzeyinde şifreleme: değerlendirme

Karar: **uygulama düzeyinde (alan bazlı) şifreleme yapılmadı.** Gerekçe:
- Alan bazlı şifreleme, ham metnin her yazılışında ve okunuşunda (STT sonrası kayıt, yönetici arayüzü,
  analiz bağlamı) şifreleme/çözme ve anahtar erişimi gerektirir; karmaşıklık ve performans yükü getirir.
- Anahtar yönetimi (saklama, döndürme, yedek) ayrı bir sistem ve hata riski ekler; anahtar uygulamayla
  aynı ortamda durursa uygulamayı ele geçiren veriyi de çözer, koruma sınırlı kalır.
- Tehdit modelinde en olası yollar (yetkisiz API erişimi, sızan yedek/disk) için hacim ve veritabanı
  disk şifrelemesi (Cloud SQL, GCS varsayılan AES-256) aynı riski çok daha az maliyetle kapatır.
- Veritabanı yöneticisi düz veriyi görmeye devam eder (kabul edilen kalan risk).

Önerilen sıradaki adım (yapılmadı): gerçek müşteri verisine geçilmeden önce `calls.customer_phone` ve
`transcripts.full_text` için KMS tabanlı zarf şifrelemesi (envelope encryption) ayrıca değerlendirilir.
