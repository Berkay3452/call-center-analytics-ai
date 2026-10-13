# Sentetik çağrı verisi

Miço Usta bağlamında yazılmış **30 sahte telefon görüşmesi** ve her biri için **doğru etiketler** (ground truth). Gerçek müşteri verisi yoktur; isimler, tekneler ve marinalar kurgusaldır. Agent'ların testinde ve doğruluk ölçümünde (#21) kullanılır.

Şimdilik yalnızca **metin ve etiket**; ses kayıtları ayrı bir iştir. İlk 10 çağrı (#12) ve sonraki 20 çağrı (#38) elle yazıldı. Hedef sonrasında ~150 çağrıdır.

## Klasör yapısı

| Yol | İçerik |
|---|---|
| `calls/call_NNN.json` | Görüşme metni: `{"call_id", "turns": [{"speaker", "text"}]}` |
| `truth/call_NNN.truth.json` | Doğru etiketler (aşağıda) |
| `calls_meta.json` | Santral/CRM bilgisi ve müşteri/tekne referansı |
| `customers_boats.json` | Müşteri ve tekne birleşik referans listesi (#12 ve #23 ortak sözleşmesi) |
| `marinas.json` | İstanbul/Marmara/Ege marinaları (10 marina) |
| `customers.json` | Sentetik müşteriler (18 müşteri; sahte telefon ve `@example.com` e-posta) |
| `boats.json` | Müşterilere bağlı tekneler (23 tekne; tip, model, boy, motor, yıl, marina) |
| `craftsmen.json` | Ustalar ve uzmanlık alanları (6 usta) |
| `service_orders.json` | Geçmiş 1–2 yıla ait servis emirleri (61 kayıt) |
| `boat_notes.json` | Türkçe usta notları / tekne karnesi (85 not; Miço AI RAG kaynağı) |
| `expenses.json` | Tekne bakım ve marina giderleri (62 kayıt; Miço AI gider aracı kaynağı) |
| `subscriptions.json` | Yıllık bakım ve kışlama paketleri (15 kayıt; kalan hak aracı kaynağı) |

## Görüşme dosyası

- `speaker`: `rep` (firma temsilcisi) veya `customer` (müşteri). Backend'deki `Speaker` ile aynı değerler.
- `text` **zaten maskelenmiştir**: agent'lar yalnızca maskeli metni görür. Telefon `[TELEFON]`, kişi adı (müşteri ve çalışan) `[İSİM]` olarak yazılır. Tekne adı ve marina kişisel veri sayılmaz, açık yazılır.
- Her görüşme 15–30 konuşma sırasıdır ve sıralar müşteri/temsilci arasında değişir.

## Etiket dosyası (`truth`)

```
call_type            yeni_musteri | servis | teklif | acil | bilgi
crm.request_category makine | mekanik_hidrolik | elektrik_elektronik | su_sihhi_tesisat |
                     iklimlendirme | tekne_guvenligi | temizlik_bakim | diger | null
crm.location         serbest metin | null
crm.problem          serbest metin | null
crm.service_mode     yerinde_servis | atolyede | uzaktan_destek | null
crm.urgency          dusuk | normal | yuksek | acil | null
crm.potential_job    serbest metin | null
crm.next_action      servis_randevusu_olustur | teklif_hazirla | geri_ara | bilgi_ver |
                     usta_ata | aksiyon_yok | null
sales.outcome        satisa_donustu | kaybedildi | beklemede
sales.loss_reason    yalnızca outcome=kaybedildi iken dolu
notes                etiketin neden böyle olduğuna dair kısa not
```

Değerler `backend/app/domain/enums.py` ile birebir aynıdır; kategori ve sonraki aksiyon kuralları `docs/enums.md`'de. Konuşmada geçmeyen alan `null`'dır (agent'ın uydurmaması beklenir). Serbest metin alanları (`problem`, `potential_job`) ölçümde birebir değil, anlam olarak karşılaştırılır.

## Santral bilgisi (`calls_meta.json`)

`started_at`, `answer_delay_s` (çalma→açılma süresi, "Ortalama cevap süresi" KPI'ı buradan hesaplanır, sesten çıkmaz), `duration_s`, `switchboard_outcome` ve `customer_ref` (müşteri, tekne, model, marina). Müşteri/tekne adları şimdilik frontend mock verisinden alındı; Melih'in #23 listesi hazır olunca eşleştirilecek.

## Dağılım (30 çağrı)

| | |
|---|---|
| Çağrı tipi | 4 acil, 11 servis, 6 teklif, 4 yeni müşteri, 5 bilgi |
| Satış sonucu | 10 satışa dönüşen, 11 kaybedilen, 9 beklemede |
| Kayıp nedeni | fiyat 3, geç dönüş 2, rakip 2, takvim 2, güven 1, diğer 1 |
| Talep kategorisi | sekiz kategorinin hepsi (+ iş konuşulmayan çağrılarda `null`) |
| Aciliyet | dört seviyenin hepsi |

`call_001`, hocanın örnek senaryosudur (Tuzla Marina, motor devir sorunu).

## Kümeler (`split`, `calls_meta.json`)

- **`gelistirme`** (`call_001`–`call_010`): agent prompt'ları bu çağrılara bakılarak ayarlanabilir.
- **`test`** (`call_011`–`call_030`, 20 çağrı): **dokunulmaz test kümesi**. Prompt ayarında kullanılmaz, yalnızca ölçümde (`python -m scripts.evaluate --split test`). Bu kümedeki bir çağrıya bakarak prompt değiştirilirse ölçüm değerini kaybeder.

Bazı çağrılar bilinçli olarak zor/sınır durumlarıdır: iş konuşulmayan bilgi çağrıları (kategori `null`), firmanın vermediği hizmet (kaptan kiralama → kayıp nedeni `diger`), kayıtlı olmayan ilk kez arayan müşteriler (`Volkan Tekin`, `Ece Aksoy`, `Tuncay Erdem`: CRM'de müşteri/tekne eşleşmesi yok), aynı müşterinin ikinci kez aramaları.

## Değişiklik kuralı

Etiket değiştirmek ölçüm sonuçlarını değiştirir; bir etiketi düzeltirseniz nedenini PR'da yazın. Yeni çağrı eklerken `backend/tests/test_synthetic_calls.py` formatı denetler.

## Veritabanına yüklenen çağrı verisi hakkında

`python -m scripts.seed` 30 çağrıyı da yükler: `calls`, `transcripts`, `transcript_segments` ve **doğru etiketleri `analysis_results` tablosuna sürüm 1 olarak** (Admin Çağrı Analitiği ekranı API hazır olmadan da dolsun diye). Dikkat:
- Bu satırlar yapay zekânın değil **elle yazılmış doğru etiketlerin** sonucudur (güven 1.0, `agent_runs` yok).
- Gerçek analiz aynı çağrı için **sürüm 2** olarak eklenmelidir (`UNIQUE (call_id, version)`).
- `audio_path` ve `audio_sha256` boştur; ses dosyaları (TTS) gelince doldurulur.
