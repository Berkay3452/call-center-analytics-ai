# Sentetik çağrı verisi

Miço Usta bağlamında yazılmış **10 sahte telefon görüşmesi** ve her biri için **doğru etiketler** (ground truth). Gerçek müşteri verisi yoktur; isimler, tekneler ve marinalar kurgusaldır. Agent'ların testinde ve doğruluk ölçümünde (#21) kullanılır.

Bu ilk partidir: şimdilik yalnızca **metin ve etiket**. Sese çevirme (TTS) sonraki adımdır. Vize hedefi 30+ çağrıdır.

## Klasör yapısı

| Yol | İçerik |
|---|---|
| `calls/call_NNN.json` | Görüşme metni: `{"call_id", "turns": [{"speaker", "text"}]}` |
| `truth/call_NNN.truth.json` | Doğru etiketler (aşağıda) |
| `calls_meta.json` | Santral/CRM bilgisi ve müşteri/tekne referansı |

## Görüşme dosyası

- `speaker`: `rep` (firma temsilcisi) veya `customer` (müşteri). Backend'deki `Speaker` ile aynı değerler.
- `text` **zaten maskelenmiştir**: agent'lar yalnızca maskeli metni görür. Telefon `[TELEFON]`, kişi adı `[İSİM]` olarak yazılır. Tekne adı ve marina kişisel veri sayılmaz, açık yazılır.

## Etiket dosyası (`truth`)

```
call_type            yeni_musteri | servis | teklif | acil | bilgi
crm.request_category motor_arizasi | elektrik_arizasi | yakit_sistemi | govde_ve_kil |
                     periyodik_bakim | kis_bakimi | diger | null
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

Değerler `backend/app/domain/enums.py` ile birebir aynıdır. Konuşmada geçmeyen alan `null`'dır (agent'ın uydurmaması beklenir). Serbest metin alanları (`problem`, `potential_job`) ölçümde birebir değil, anlam olarak karşılaştırılır.

## Santral bilgisi (`calls_meta.json`)

`started_at`, `answer_delay_s` (çalma→açılma süresi, "Ortalama cevap süresi" KPI'ı buradan hesaplanır, sesten çıkmaz), `duration_s`, `switchboard_outcome` ve `customer_ref` (müşteri, tekne, model, marina). Müşteri/tekne adları şimdilik frontend mock verisinden alındı; Melih'in #23 listesi hazır olunca eşleştirilecek.

## Dağılım

| | |
|---|---|
| Çağrı tipi | 2 acil, 3 servis, 2 teklif, 1 yeni müşteri, 2 bilgi |
| Satış sonucu | 4 satışa dönüşen, 4 kaybedilen, 2 beklemede |
| Kayıp nedeni | takvim (003), geç dönüş (004), fiyat (005), rakip (006): her neden bir kez |

`call_001`, hocanın örnek senaryosudur (Tuzla Marina, motor devir sorunu).

## Değişiklik kuralı

Etiket değiştirmek ölçüm sonuçlarını değiştirir; bir etiketi düzeltirseniz nedenini PR'da yazın. Yeni çağrı eklerken `backend/tests/test_synthetic_calls.py` formatı denetler.
