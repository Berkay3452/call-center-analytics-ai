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

## Miço AI sohbet kalitesi ve güvenlik (#213)

82 soruluk testle (selam, sohbet, genel bilgi, kayıt, sayısal, takip, küfür/argo, injection, anlamsız girdi, İngilizce) uygun cevap oranı **%85 → %95-98** (69/81 → 77-79/81). Küfür artık yankılanmıyor, hakaret ve anlamsız girdi saçma "kayıtlarınızda bulamadım" cevabı almıyor, "başka müşterilerin giderleri" kendi toplamını döndürmüyor, saat/tarih uydurulmuyor. Selam, saat, tarih, küfür politikası gibi 33 soru LLM'siz 0,7 sn'nin altında cevaplanıyor; LLM'li sorularda medyan ~2 sn. Ayrıntı, bulgular, politika ve soru bazlı tablo: [asistan_sohbet_olcumu.md](asistan_sohbet_olcumu.md). Yeniden üretmek için: `python -m scripts.assistant_chat_eval --out sonuc.json` (Postgres, embedding ve `.env` gerekir).

## Tek LLM değerlendirmesi: karma mı, tek (güçlü) model mi? (#215)

**Tarih:** 2026-11-02 · **Veri:** test kümesi, 20 çağrı × 2 tekrar (aynı koşullar, sırayla A-B-A-B) · **Ayar:** `LLM_REQUESTS_PER_MINUTE=10` (model başına), eşzamanlılık 2 · **Komut:** `python -m scripts.evaluate --split test --fast <m> --smart <m> --out sonuc.json`

- **A (karma, mevcut):** hızlı `lightning-30b-a3b`, güçlü `super-vl-120b-a12b`; geçici hatada diğer modele yedek geçiş.
- **B (tek model):** `LLM_FAST_MODEL` = `LLM_SMART_MODEL` = `super-vl-120b-a12b`. Yedek model yok (`llm_fallback_for`: aday birincille aynı olunca `None`).

| Ölçüt | A karma | B tek model |
|---|---|---|
| Başarısız ajan çalışması (hepsi 429) | **38 / 200 (%19)** | 93 / 200 (%47) |
| Yedek modele geçen ajan çalışması | 80 | 0 (yedek yok) |
| Analiz durumu (tamam / kısmi / başarısız), 2 koşu toplamı | 15 / 25 / 0 | 1 / 37 / 2 |
| Ölçülen alanlarda doğruluk (özet hariç) | %88,8 ve %86,1 | %92,9 ve %92,5 |
| Çağrı başına süre (ort.) | **18,9 sn** | 24,4 sn |
| Ajan süresi (ort. / p95) | **10,2 sn / 49,0 sn** | 15,3 sn / 54,2 sn |
| Zaman aşımı | 0 | 0 |

**Okuma.** Doğruluk karşılaştırmasını B lehine okumak yanıltıcı: B'de ajanların yarıya yakını 429 ile düştüğü için yalnızca *çalışabilen* (kolay) ajanların alanları ölçülüyor. Aynı alanda gerçek fark küçük (birkaç puan) ve bu örneklemle (20 çağrı, 2 koşu) güvenilir değil. Güvenilir olan fark dayanıklılık ve süredir:

1. **Kota model başına tükeniyor.** Karma yapılandırma yükü iki modele böler; tek modelde bütün istekler (4-5 ajan × çağrı) aynı kotaya biner ve 429 oranı 2,4 katına çıkar.
2. **Yedek yol kalmıyor.** Karmada 429 alan 80 ajan çalışması diğer modele geçip tamamlandı; tek modelde böyle bir yol yok, çağrılar `kismi` kaldı (37/40).
3. **Güçlü model daha yavaş:** ajan süresi 10,2 → 15,3 sn, çağrı süresi 18,9 → 24,4 sn (+%29).

Ek gözlem: ilk deneme (50 çağrı × 3 tekrar, `LLM_REQUESTS_PER_MINUTE=30`, art arda koşular) iki yapılandırmada da çöktü: ilk ~35 çağrıdan sonra tüm istekler 429 aldı (hızlı modele atılan tek tek `curl` istekleri bile 429 verdi). Anahtar başka oturumlarla paylaşıldığı için etkin sınır `.env`'deki 30 RPM'den düşük; bu yüzden model başına 10 RPM'e inildi ve yine de her iki yapılandırmada 429 görüldü. Sonuç, kotanın mevcut yapılandırmanın dar boğazı olduğu ve tek modelin bunu kötüleştirdiğidir. Not: ölçüm, #221'deki "429'da bekleyip yeniden dene" davranışı birleşmeden önceki kodla yapıldı; yeniden deneme iki yapılandırmada da başarısızlık oranını düşürür, ama tek modelin yük/yedek dezavantajını ortadan kaldırmaz.

**Karar: karma yapılandırma kalır; `.env.example` ve varsayılan ayarlar değişmedi.** Tek modelin kazancı (sadelik, tutarlılık) kota ve süre kaybını karşılamıyor. Tek modele ancak şu koşullarda dönülür: (a) ücretli/yüksek kotalı bir anahtar, (b) güçlü modele ayrı bir yedek model (`LLM_FALLBACK_MODEL`) ve (c) bu ölçümün yeniden yapılması. Tek model + hızlı yedek (C) yapılandırması kota yüzünden ölçülemedi.

**Yapılamayanlar.** Asistan sorularının (82 soru × 3 tekrar) tek model ile ölçümü kota ve embedding servisi (bellek baskısıyla kapalıydı) nedeniyle yapılamadı; asistan tarafında yalnızca iki iyileştirme yapıldı: `AssistantLLM` artık ajanlarla aynı dakikalık kota sırasını (`llm_rate_limiter`) kullanıyor (daha önce yalnızca eşzamanlılık sınırı vardı), ve genel cevap güçlü modele alındı (#213). 50 çağrılık tam küme yerine 20 çağrılık test kümesi kullanıldı.



## 100 çağrıda yeniden ölçüm (#149)

**Tarih:** 2026-11-07 · **Veri:** 100 sentetik çağrı (#148): 60 geliştirme, 40 dokunulmaz test (`call_011-030`, `call_051-070`) · **Model:** hızlı `nvidia/nemotron-3.5-lightning-30b-a3b`, güçlü `nvidia/nemotron-3.5-super-vl-120b-a12b` (karma, #215 kararı) · **Komut:** `python -m scripts.evaluate --split test` (rapora artık "Agent bazında" tablosu da yazılıyor)

**Önce bir etiket düzeltmesi.** İlk ölçümde `potential_job` (dolu/boş) test kümesinde %75, geliştirme kümesinde %60 çıktı. Hataların 18/24'ü modelin "iş" yazıp etiketin boş olduğu çağrılardı: yeni 50 çağrıda arıza/servis/acil çağrılarında `potential_job` boş bırakılmıştı, oysa ilk 50 çağrıda bu alan iş doğan her çağrıda dolu (41/50), yalnızca bilgi çağrılarında boş. Bu bir model hatası değil, #148'de yazdığım etiketlerin eski kuralla tutarsızlığıydı. Kural eski etiketlerden çıkarıldı, 27 çağrıya model çıktısına bakmadan uygulandı (`call_051-100`); sonra aynı model çıktıları yeni etiketlerle yeniden puanlandı. Bu, test kümesinde etiket değişikliğidir ve aşağıdaki tabloda ayrı sütunla görünür.

### Agent bazında doğruluk: test kümesi (40 çağrı)

| Agent (alanlar) | İlk ölçüm, eski etiket | İlk ölçüm, düzeltilmiş etiket | Prompt sonrası (2 tekrar ort.) |
|---|---|---|---|
| `call_classifier` (çağrı tipi) | %88 (35/40) | %88 (35/40) | %85 (34/40) |
| `crm_extraction` (7 alan) | %90 (252/280) | %94 (262/280) | %94 (262/280) |
| `sales_analyzer` (satış sonucu, kayıp nedeni) | %99 (79/80) | %99 (79/80) | %99 (79-80/80) |
| `summarizer` (özet üretildi) | %100 | %100 | %100 |
| **Genel (11 alan)** | **%92 (406/440)** | **%94,5 (416/440)** | **%94,3-94,5 (415-416/440)** |

Orkestratör (4 agent birleşimi): 40/40 çağrıda durum `tamam` (3 koşuda da), zaman aşımı 0, yedek modele geçen 0.

### Alan bazında: test kümesi

| Alan | İlk (düzeltilmiş etiket) | Prompt sonrası (tekrar 1 / 2) |
|---|---|---|
| call_type | %88 | %85 / %85 |
| request_category | %95 | %95 / %95 |
| service_mode | %80 | %82 / %82 |
| urgency | %95 | %95 / %92 |
| **next_action (sonraki aksiyon)** | **%92** | **%92 / %92** |
| location | %100 | %100 / %100 |
| problem (dolu/boş) | %92 | %95 / %98 |
| potential_job (dolu/boş) | %100 | %95 / %95 |
| sales_outcome | %100 | %100 / %100 |
| loss_reason | %98 | %98 / %100 |
| summary (üretildi) | %100 | %100 / %100 |

### Prompt iyileştirmesi (yalnızca geliştirme kümesine bakılarak)

Geliştirme kümesindeki (60 çağrı) hatalar incelendi; test kümesi hata listelerine bakılmadı. İki kural eklendi:
- `call_classifier.md`: su alma, batma, yangın/duman, yakıt kaçağı, denizde sürüklenme bildirimi usta yönlendirilse de **acil**; mevcut işin ilerlemesini soran, yeni arıza/iş içermeyen çağrı **bilgi** (geliştirmede 6 çağrı yanlıştı).
- `crm_extraction.md`: hizmet biçimi (`service_mode`) iş konuşulmadıysa, yalnızca durum veya fiyat soruluyorsa null (tahmin etme).

| Geliştirme kümesi (60 çağrı) | Önce | Sonra |
|---|---|---|
| call_type | %85 | **%97** |
| service_mode | %83 | %87 |
| potential_job (düzeltilmiş etiket) | %85 | %90 |
| next_action | %97 | %93 |
| Genel | %93,3 | **%94,7** |

### Sonuç ve hedef

- **Hedef "sonraki aksiyon" ≥ %85: karşılandı.** Test kümesinde ilk ölçümde de (%92, 37/40) sonrasında da %92; geliştirmede %93-97. #213'te görülen %80, 20 çağrılık küçük kümenin gürültüsüydü, 40 çağrıda ortaya çıkmıyor. Kalan 3 hata (`call_013`, `call_018`, `call_029`) iki ardışık koşuda aynı: müşteri fiyatı pahalı bulup vazgeçtiği (`call_013`) veya rakibe gittiği (`call_018`) çağrılarda model `teklif_hazirla` öneriyor (doğrusu `aksiyon_yok`); randevu saati teyidinde (`call_029`) `servis_randevusu_olustur` öneriyor (doğrusu `aksiyon_yok`). Yani müşteri vazgeçtiğinde veya yeni iş olmadığında 'aksiyon yok' demek yerine bir sonraki adım uyduruluyor.
- **Prompt değişikliği geliştirmede işe yaradı (call_type %85 → %97) ama test kümesine genellenmedi** (genel %94,5 → %94,3-94,5; çağrı tipi %88 → %85, yani 1 çağrı; `call_020` yeni hata). Dürüst yorum: kazanç gürültü sınırında, kurallar zararsız ama test kümesinde ölçülebilir iyileşme göstermedi.
- **Kalan hata türleri (test):** `service_mode` %82: kaybedilen/ertelenen çağrılarda etiket ile model "hizmet biçimi var/yok" konusunda ayrışıyor (etiketler arasında da tutarsızlık var: kayıp çağrılarda `yerinde_servis` yazılmış); `call_type` %85: acil/servis ve servis/bilgi sınırı; `urgency` ±1 basamak kayması.
- **Cevap hızı (test, 40 çağrı):** çağrı başına ortalama 4,5-6,1 sn (tamamı: 4 agent, süre `ajan_ort` 2,4-2,8 sn, p95 5,8-7,0 sn, en uzun 10-34 sn tek yavaş LLM çağrısı); toplam ~390 bin token / 40 çağrı. Zaman aşımı yok.
- **Sınırlar:** test kümesinde 40 çağrı = alan başına ±%5 duyarlılık; prompt sonrası 2 tekrar (3 değil: kota/süre). İlk ölçüm tek tekrar. `potential_job` yeniden etiketlemesi test kümesinde de yapıldı (yukarıda açıklandı).


## Duygu analizi (#334)

**Tarih:** 2026-11-20 · **Agent:** `sentiment_analyzer` (smart katman, `nvidia/nemotron-3.5-super-vl-120b-a12b`) · **Komut:** `python -m scripts.duygu_olcum`

### Yöntem

- **Veri:** 100 ana sentetik çağrı + bu iş için yazılan 19 ek çağrı (`data/synthetic/duygu_ek/`: 7 olumlu, 6 şikâyetli olumsuz, 6 nötr, 5'i sınır vaka). Ana çağrılar doğası gereği nötr ağırlıklıdır (müşteri arıza veya talep bildirir); olumlu ve olumsuz örnekler bu yüzden az, ek çağrılar bu boşluğu doldurmak içindir.
- **Etiket:** `data/synthetic/duygu_etiketleri.json`; her çağrı için `sentiment` (olumlu/notr/olumsuz), `complaint` (firmaya açık yakınma) ve `zor` (sınır vaka). Etiketler istem yazıldıktan sonra, model çıktısı görülmeden elle verildi. Etiketleyen tek kişi (yapay zekâ asistanı) olduğu için bağımsız ikinci etiketleyici yoktur.
- **Çalıştırma:** agent üretimdeki gibi orkestratör üzerinden koşar (şema doğrulaması, bir düzeltme hakkı, çıktı süzgeci). Yalnızca sentetik ve maskeli metin kullanıldı.
- **Sınır vaka (`zor`, 20 çağrı):** fiyat itirazı ("çok pahalı, vazgeçiyorum"), rutin onay ifadesi ("makul, harika, teşekkürler"), sakin güvensizlik, arızadan bıkkınlık, geçmiş sitem + yeni randevu. İnsanlar arasında da ayrışabilecek çağrılardır; ayrı raporlanır.

### Sonuç: istem v2, 119 çağrı

| Küme | Duygu doğruluğu |
|---|---|
| Tümü | **%97 (116/119)** |
| Ana 100 çağrı | %97 (97/100) |
| Ek 19 çağrı | %100 (19/19) |
| Geliştirme kümesi (ana, 60) | %100 (60/60) |
| Test kümesi (ana, 40) | %92 (37/40) |
| Sınır vakalar hariç (99) | %99 (98/99) |
| Yalnızca sınır vakalar (20) | %90 (18/20) |

Karışıklık tablosu (satır: doğru etiket, sütun: agent):

| doğru \ agent | olumlu | notr | olumsuz | Doğru oran |
|---|---|---|---|---|
| olumlu | 8 | 0 | 0 | %100 (8/8) |
| notr | 0 | 97 | 1 | %99 (97/98) |
| olumsuz | 0 | 2 | 11 | %85 (11/13) |

**Şikâyet bayrağı:** doğru pozitif 11, yanlış pozitif 1, kaçan 0, doğru negatif 107 → duyarlılık %100 (11/11), kesinlik %92 (11/12).
Agent başarısız olmadı, düzeltme gerektiren çalışma yok. 19 çıktıda alıntı verildi (konuşmada geçmeyen alıntı otomatik kaldırılır); ortalama güven 0,86.

**Yanlış etiketlenen 3 çağrı:**

- `call_011` (sınır, test): doğru olumsuz, agent nötr. Müşteri arızadan "sinir bozucu" diye söz ediyor ama firmaya yönelik tepki yok; agent kuralı gereği nötr dedi.
- `call_020` (sınır, test): doğru olumsuz (şikâyetsiz), agent nötr. Müşteri sakin bir dille "güvenemedim" diyor; agent firmaya yönelik açık sitem bulmadı. İki etiket de savunulabilir.
- `call_055` (test): doğru nötr, agent olumsuz + şikâyet. Müşteri takvim uyuşmadığı için başka firmaya yöneliyor ("Salı bana çok geç… zamanım yok"); agent bunu şikâyet saydı. Aynı kalıp ilk ölçümde `call_003` ve `call_030` için de yanlıştı; istem kuralı ikisini düzeltti, `call_055`'i düzeltmedi. Gerçek bir zayıflık.

### İlk ölçüm (istem v1) ve istem değişikliği

İlk ölçüm istem ayarlanmadan yapıldı: **%91 (108/119)**; geliştirme %95, test %82; şikâyet kesinliği **%61** (11 doğru, 7 yanlış pozitif).

| Hata türü (v1) | Çağrı | Neden |
|---|---|---|
| Fiyat itirazı şikâyet sayıldı | `call_005`, `013`, `057` | İstem "fiyattan açıkça yakınmak şikâyettir" diyordu; fiyat itirazı zaten satış kaybı nedeni (`loss_reason=fiyat`) olarak ölçülüyor, şikâyet sayısını şişiriyor |
| Takvim uyuşmazlığıyla iptal şikâyet sayıldı | `call_003`, `030`, `055` | Sakin iptal, firmaya yakınma değil |
| Rutin onay "olumlu" sayıldı | `call_007`, `019`, `070`, `duygu_ek_19` | "Makul, tamam, teşekkürler" tek başına memnuniyet değil |
| Sınır: bıkkınlık, sakin güvensizlik | `call_011`, `020` | Etiketler tartışmalı |

**v2 değişikliği:** üç kural eklendi (fiyat itirazı şikâyet değildir; takvim nedeniyle sakin iptal şikâyet değildir; onay sözleri ve rutin teşekkür olumlu değildir) ve şikâyet tanımından "fiyattan" çıkarıldı (haksız ücret iddiası şikâyet olarak kaldı). Kurallar yalnızca geliştirme kümesindeki hatalardan çıkarıldı (`call_003`, `005`, `007`). **Dürüstlük notu:** ilk raporun tamamını (test hataları dahil) gördükten sonra yazıldı; test kümesi bu yüzden tam bağımsız değildir. v2 sayıları bu nedenle iyimser okunmalı: ilk ölçümdeki test kümesi %82 daha dürüst bir "ayarsız" başlangıç değeridir. Ayrıca ek 19 çağrı ve sınır vakalar da aynı turda raporlandığı için v2'nin %100/%90 değerleri küçük örneklemdir.

### Süre etkisi

Aynı 10 çağrıda (her 10. çağrı) sırayla 4 agent ve 5 agent akışı çalıştırıldı; çalıştırmalar arası 10 sn beklendi (dakikadaki istek sınırı kuyruğu süreyi bozmasın diye):

| Akış | Çağrı | Ortalama sn | Ortanca sn | En uzun sn |
|---|---|---|---|---|
| 4 agent | 10 | 5,2 | 3,6 | 19,9 |
| 5 agent | 10 | 5,7 | 4,2 | 13,5 |

**Fark: ortalama +0,5 sn/çağrı** (ortanca +0,6 sn). Beş agent tek aşamada paralel çalıştığı için uçtan uca süre en yavaş agent'a bağlıdır; duygu agent'ı tek başına tipik olarak 1-1,5 sn sürdü. Tek ölçüm turu ve 10 çağrı olduğundan sağlayıcı oynaklığı (en uzun değerler) farkın yönünü belirsizleştirir: fark ölçüm gürültüsü düzeyindedir. 119 çağrılık ölçümde görülen 43-45 sn'lik uç değerler agent'ın değil, dakikada 30 istek sınırının (kota kuyruğu) eseridir.

### Sınırlar

- Etiketler tek kişiden; olumlu (8) ve olumsuz (13) örnek sayısı az: bu sınıflarda ±%10 ve üzeri belirsizlik vardır.
- Sentetik görüşmeler temiz ve kibar yazılmıştır; gerçek konuşma (yazıya çevirme hataları, kesilen cümleler, bağırma) farklı davranabilir. Ses tonu değil yalnızca yazıya dökülmüş metin değerlendirilir.
- Tek kanallı (mono) kayıtta konuşmacı ayrımı yoktur ("Bilinmiyor"); agent bu durumda metinden müşteri tarafını ayırmaya çalışır ve ölçümde bu durum ayrıca sınanmadı.
- Fiyat itirazı, sakin güvensizlik ve rutin onay gibi sınır vakalarda "doğru" etiket iş kararıdır; istem v2 bu kararı kurallaştırır, farklı bir iş tanımı etiketleri değiştirir.
