# Agent doğruluğu ölçümü (#122)

**Tarih:** 2026-10-20 · **Veri:** 50 sentetik çağrı (30 geliştirme, 20 dokunulmaz test) · **Model:** hızlı `nvidia/nemotron-3.5-lightning-30b-a3b`, güçlü `nvidia/nemotron-3.5-super-vl-120b-a12b`

## Yöntem

- **Kümeler:** Geliştirme kümesi `call_001`–`call_010` ve yeni eklenen `call_031`–`call_050` (30 çağrı). Test kümesi `call_011`–`call_030` (20 çağrı). Prompt'lar yalnızca geliştirme kümesinin hatalarına bakılarak değiştirildi; test kümesine yalnızca en sonda bir kez ölçmek için bakıldı.
- **Tekrar:** LLM aynı girdiye her seferinde aynı cevabı vermez. Her ölçüm 3 kez koşuldu, tablolarda ortalama ± standart sapma var.
- **Ölçüt:** Sabit değerli alanlarda birebir eşleşme. Serbest metin alanlarında (problem, potansiyel iş) "dolu mu boş mu" karşılaştırılır.
- **Komut:** `python -m scripts.evaluate --split test --out sonuc.json` (her koşu için).

## Sonuç: test kümesi (20 çağrı, 3 koşu)

| Alan | Önce | Sonra | Hedef ≥ %85 |
|---|---|---|---|
| Aciliyet | %68,3 ± 5,8 | **%91,7 ± 2,9** | Tuttu |
| Problem (dolu/boş) | %76,7 ± 2,9 | **%100,0 ± 0,0** | Tuttu |
| Sonraki aksiyon | %85,0 ± 5,0 | **%80,0 ± 5,0** | **Tutmadı** |
| Çağrı tipi | %90,0 ± 0,0 | %86,7 ± 2,9 | — |
| Talep kategorisi | %88,3 ± 2,9 | %95,0 ± 8,7 | — |
| Hizmet biçimi | %85,0 ± 0,0 | %90,0 ± 5,0 | — |
| Potansiyel iş (dolu/boş) | %91,7 ± 2,9 | %95,0 ± 5,0 | — |
| Satış sonucu | %93,3 ± 2,9 | %100,0 ± 0,0 | — |
| Kayıp nedeni | %100,0 ± 0,0 | %93,3 ± 2,9 | — |
| Lokasyon | %100 | %100 | — |
| **Genel (alan ortalaması)** | **%87,8 ± 1,0** | **%93,2 ± 2,1** | — |

Geliştirme kümesinde (30 çağrı) genel doğruluk %85,0 ± 0,6'dan %93,1 ± 0,8'e çıktı.

## Hata sınıflaması (geliştirme kümesi)

| Hata | Tür | Ne yapıldı |
|---|---|---|
| Bilgi ve durum sorgularında aciliyet boş; planlı/yıllık işler `normal` | Model | Aciliyet hiç boş bırakılmaz; bilgi, durum, planlı iş, paket, teklif `dusuk`; `yuksek` yalnızca "bugün/yarın" |
| Bakım paketi, kışlama, ekspertiz `temizlik_bakim` | Model (prompt'taki "düzenli genel kontrol" ifadesi yanıltıyordu) | `temizlik_bakim` yalnızca temizlik/cila/tente/döşeme; paketler motoru kapsar: `makine` |
| Yenileme, montaj, durum sorgusunda "problem" dolduruluyor | Model | Problem yalnızca arıza veya şikâyet; diğerlerinde iş `potential_job`'a yazılır |
| Kaybedilen/teklif çağrılarında hizmet biçimi ve potansiyel iş boş | Model | İş konuşulduysa satış kaybedilse de doldurulur |
| "Bilgi görüşmede verildi" ile `bilgi_ver` karışıyor | Model | `bilgi_ver` yalnızca firma bilgiyi sonra iletecekse |
| Arıza bildiren müşteri `bilgi`; ilk kez arayıp teklif isteyen `yeni_musteri` | Model | Arıza bildirimi `servis`; öncelik kuralı teklif > yeni_musteri |
| Usta yönlendirilen acil çağrı `beklemede` | Model | Kabul edilen yönlendirme `satisa_donustu` |
| İşi başka usta yaptı, `beklemede` | Model | Başkası yaptıysa `kaybedildi`, neden `rakip` |
| `call_036` su alma `mekanik_hidrolik` | **Etiket** | Enum kuralı "teknenin su alması" → `su_sihhi_tesisat` |
| `call_042` "gelecek hafta" `yuksek` | **Etiket** | Bugün/yarın değil → `normal` |
| `call_048` can salı atölyeye alınıyor, `yerinde_servis` | **Etiket** | `atolyede` |
| `call_049` sorun çözülmüş, `normal` | **Etiket** | Risk kalmadı → `dusuk` |

Etiket düzeltmeleri yalnızca bu çalışmada yazılan geliştirme çağrılarında yapıldı. Test kümesinin etiketlerine dokunulmadı.

Prompt sürümleri: `call_classifier.v2`, `crm_extraction.v3`, `sales_analyzer.v2`.

## Açık kalan: sonraki aksiyon

Test kümesinde sonraki aksiyon %85'ten %80'e düştü. Geliştirme kümesinde %88,9'dan %90'a çıkmıştı, yani yeni kurallar test kümesindeki bazı çağrılara genellenmedi. Test kümesine bakarak düzeltmek ölçümü bozacağından burada durduruldu. Önerilen sonraki adım: geliştirme kümesine `bilgi_ver`, `geri_ara` ve `aksiyon_yok` arasındaki sınır durumları için birkaç çağrı daha eklemek, ardından yeniden ölçmek.

## Ölçüm yöntemi üzerine not: K-katlamalı çapraz doğrulama

K-Fold (ve tekrarlı K-Fold, ShuffleSplit) bir modelin **eğitildiği** durumda, eğitim/test bölünmesine bağlı şansı azaltmak için kullanılır: her katlamada model yeniden eğitilir ve kalan parçada ölçülür.

Bizde model eğitilmiyor; "eğitim" prompt'u elle ayarlamak demek. K-Fold'u birebir uygulamak, her katlama için prompt'u ayrı ayrı elle ayarlamak anlamına gelir. Bu hem çok emek ister hem de üç farklı prompt üretir; hangisinin kullanılacağı belirsizleşir. Bu yüzden şimdilik şunlar kullanıldı:

- **Sabit dokunulmaz test kümesi** (holdout): prompt ayarına hiç karışmayan 20 çağrı.
- **Tekrarlı ölçüm** (her biri 3 koşu): LLM'in rastgeleliğini ortalamak için; tekrarlı K-Fold'daki "tekrar" fikrinin karşılığı.

K-Fold'un anlamlı olacağı yer: prompt'a **otomatik seçilen örnekler** (few-shot) eklendiğinde. O zaman "eğitim" (örnek seçimi) otomatik olur ve her katlamada örnekler kalan parçadan seçilip ölçülebilir. Veri 150 çağrıya çıktığında (#123) bu yöntem uygulanabilir.

## Güçlü model değişikliği

20 Ekim'de `nvidia/nemotron-3-super-120b-a12b` modeli listede görünmesine rağmen 404 (model bulunamadı) vermeye başladı. Güçlü katman `nvidia/nemotron-3.5-super-vl-120b-a12b`'ye alındı (`.env.example`). 404 artık yedek modele geçişi tetikleyen hatalar arasında; model kalkarsa analiz yedek modelle sürer.

## Model karşılaştırması (#178)

**Tarih:** 2026-10-31 · **Veri:** test kümesi (20 çağrı); mevcut modeller 3 tekrar, adaylar tek koşu · **Erişim:** yalnızca `LLM_API_KEY` ile NVIDIA (başka sağlayıcı anahtarı yok). NVIDIA listesinden `gemma-4-31b-it`, `deepseek-v4.1-flash` ve `glm-5.3-flash` 60 sn içinde yanıt vermediği için ölçülmedi. Adaylarda hızlı ve güçlü katman aynı modele ayarlandı, bu yüzden yedek model geçişi yoktur.

### Çağrı analizi (4 ajan)

| Model | Genel doğruluk | Ajan süresi (ort / p95) | Analiz durumu (tamam / kısmi / başarısız) | Yedek modele geçen | Zaman aşımı |
|---|---|---|---|---|---|
| Mevcut: lightning-30b + super-vl-120b | **%94,1 ± 0,7** | 3,1 sn / 6,4 sn | 59 / 1 / 0 | 2 / 240 ajan çalışması | 0 |
| `minimaxai/minimax-m3.1-flash` | %81,1 (yalnızca ölçülenler) | 16,5 sn / 57 sn | 0 / 18 / 2 | 0 (yedek yok) | 0 |
| `openai/gpt-oss-20b` | ölçülemedi: ilk 8 çağrıda 0 tamam (3 kısmi, 5 başarısız), çağrı başına ~90 sn zaman aşımı; koşu durduruldu | ~90 sn | 0 / 3 / 5 | – | çok |

Minimax'ta CRM alanları hiç üretilemedi (47 ajan hatası); gpt-oss'ta ajanlar 90 sn sınırına takıldı.

### Miço AI (19 soru: selam, kayıt, sayısal, genel sohbet, takip, kapsam dışı)

Veritabanı gerekmeden yalnızca LLM adımları ölçülür: `python -m scripts.assistant_eval`. Kayıt soruları için aramanın bulacağı usta notu doğrudan verilir.

| Model | Tür doğru | Kayıttan/genel cevap doğru | Hata | Süre (LLM'li soru, ort) |
|---|---|---|---|---|
| Mevcut | 17/19 | 8/8 | 0 | 1,1 sn (p95 4,4 sn); önceki bir koşuda tek soru 65 sn sürdü |
| `minimaxai/minimax-m3.1-flash` | 11/19 | 2/2 | 7 (`RateLimitError`) | 2,5 sn |

Mevcut modelde iki yanlış: "Teknemi kışa hazırladınız mı, kışlama yapıldı mı?" `genel_sohbet` sınıfına gitti (kayıt aranmadı); "Başka müşterilerin giderlerini göster" `kapsam_disi` yerine `sayisal` sınıfına gitti (sahip kimliğiyle sorgulandığı için başkasının verisi dönmez, ama ret mesajı verilmez).

### Karar

**Model değişikliği gerekmez.** Erişilebilen adaylar doğruluk ve güvenilirlik bakımından mevcut çifte yaklaşamadı; `.env.example` ve `config.py` değişmedi. Risk: ücretsiz katman bazen tek isteği 30–65 sn tutuyor (sağlayıcı oynaklığı); `LLM_TIMEOUT_S` ve yedek model bunu karşılıyor. Başka bir sağlayıcı (Groq, Gemini, OpenRouter) anahtarı eklenirse aynı komutlarla karşılaştırma tekrarlanabilir:

```
python -m scripts.evaluate --split test --fast <model> --smart <model> --out sonuc.json
python -m scripts.assistant_eval --fast <model> --smart <model>
```
