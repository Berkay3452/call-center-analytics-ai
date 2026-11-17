# Maskeleme ölçümü (#268)

**Tarih:** 2026-11-17 · **Kod:** `backend/app/services/masking.py` · **Ölçüm:** `backend/scripts/maskeleme_olcum.py` (LLM'siz, CI'da çalışır: `backend/tests/test_masking_olcum.py`) · **Kalite karşılaştırması:** `backend/scripts/maskeleme_kalite.py` (gerçek LLM, elle çalıştırılır)

## Ne maskeleniyor

| Kategori | Kural | Belirteç |
|---|---|---|
| e-posta | düzenli ifade | `[EPOSTA]` |
| IBAN (TR) | düzenli ifade, boşluklu/bitişik | `[IBAN]` |
| banka/kredi kartı | 13-19 hane, boşluk/tireli, **Luhn doğrulamalı**; Luhn'u geçmeyen uzun numara yine de telefon kuralıyla maskelenir | `[KART]` |
| T.C. kimlik no | 11 hane | `[KİMLİK]` |
| telefon | ≥ 10 rakam, ayırıcılı | `[TELEFON]` |
| vergi no | "vergi no / VKN" bağlamı + 10 hane (bağlamsız 10 haneli sayıya dokunulmaz) | `[VERGİ_NO]` |
| pasaport / ehliyet no | "pasaport/ehliyet ... no" bağlamı + rakamlı kod; bağlamsız `U12345678` biçimi | `[BELGE_NO]` |
| araç plakası | il kodu + harf + rakam (büyük harf; `HP`, `TL`, `KW` gibi birimler hariç) | `[PLAKA]` |
| tekne tescil / bağlama kütüğü / plaka no | anahtar sözcük + rakamlı büyük harfli kod | `[PLAKA]` |
| adres | "X Mahallesi/Sokak/Cadde/Bulvarı/Sitesi" + ardından No/Daire/Kat/Blok/ev numarası | `[ADRES]` |
| listede olmayan ad | "Ben X", "Adım/İsmim X", "sahibi X", "X Bey/Hanım"; yer ekleri (`Ben Tuzla Marina'dan`), unvan ve kurum sözcükleri hariç | `[İSİM]` |
| bilinen ad/soyad | çağrı bilgisinden gelen liste, harf büyüklüğüne bakılmaz | `[İSİM]` |

Tekne adı (`adı Mavi Rota`) bilerek maskelenmez: analiz için gereklidir ve kişisel veri sayılmaz. Bunun bedeli: aynı kalıpla söylenen bir insan adı (`ustamız, adı Murat`) da maskelenmez (aşağıda "bilinen sınırlar").

## Yöntem

- **Ölçüm seti:** 60 sentetik cümle, elle etiketlenmiş (`backend/scripts/maskeleme_olcum.py`). Her cümlede **gizli** (maskeden sonra metinde kalmaması gereken parçalar; geri çağırma) ve **korunan** (kişisel veriye benzeyen ama kişisel veri olmayan ifadeler; yanlış maskeleme) etiketlenir. Kart numaraları yayımlanmış test numaralarıdır; kimlik, telefon, IBAN, ad ve adresler uydurmadır; gerçek veri yoktur.
- **İki küme:** "kalıp kapsamı" (kuralların hedeflediği biçimler) ve "kalıp dışı/zor" (yazıyla söylenen numara, küçük harfli STT adresi, kalıpsız ad). Zor küme kuralların sınırını dürüstçe göstermek içindir; hedefe sayılmaz.
- **Sentetik çağrılarda yanlış maskeleme:** 100 sentetik çağrının 1668 konuşma turu maskelenir. Bu metinlerde gerçek kişisel veri yoktur (adlar zaten `[İSİM]`), yani değişen her tur olası yanlış maskelemedir. Bu denetim ölçüm setini hazırlarken gerçek hataları ortaya çıkardı: ilk sürümde `adı Karayel` / `adı Deniz Kızı` (tekne adı) ve `ben İstanbul'dayım` yanlışlıkla maskeleniyordu; "adı" kalıbı kaldırıldı, yer ekleri (`'dayım`, `'da`, `'dan`...) ad dışı sayıldı. Düzeltmeden sonra 1668 turda 0 değişiklik.

## Sonuç

Kalıp kapsamındaki cümleler:

| Kategori | Geri çağırma | Yanlış maskeleme (korunan bozuldu) |
|---|---|---|
| e-posta | %100 (3/3) | 0/0 |
| iban | %100 (3/3) | 0/0 |
| tc-kimlik | %100 (3/3) | 0/0 |
| telefon | %100 (4/4) | 0/0 |
| kart | %100 (3/3) | 0/1 |
| belge-no | %100 (4/4) | 0/0 |
| vergi-no | %100 (3/3) | 0/1 |
| adres | %100 (11/11) | 0/4 |
| plaka | %100 (5/5) | 0/0 |
| ad (listede olmayan) | %100 (11/11) | 0/1 |
| ad (bilinen liste) | %100 (3/3) | 0/0 |
| yalnızca korunan ifadeler | - | 0/17 |
| **Toplam** | **%100 (53/53)** | **0/24** |

Kalıp dışı (zor) cümleler: **0/5 yakalandı.** Kaçanlar:

- `ali.kaya at ornek nokta com` (e-posta yazıyla söylenmiş)
- `sıfır beş yüz otuz iki ...` (telefon yazıyla söylenmiş)
- `atatürk mahallesi gül sokak` (küçük harfli, noktalamasız STT adresi)
- `34 abc 123` (küçük harfli plaka)
- `Mehmet'e söyleyin` (kalıpsız ad)

**Hedef ile karşılaştırma.** Kabul ölçütü "kategori bazında ≥ %95, yapısal veride %100" idi; kalıp kapsamındaki kümede tüm kategoriler %100. **Bu sayıyı olduğundan iyi okumayın:** ölçüm seti kuralları yazan kişi tarafından hazırlandı (kör test değil), kategori başına 3-11 örnek var ve zor küme 0/5. Gerçek konuşma metninde (özellikle STT çıktısı: küçük harf, noktalamasız, yazıyla söylenen sayılar) geri çağırma bundan düşük olacaktır. Bu yüzden zor kümeyi ayrı rapor ediyoruz ve test, hedefi yalnızca kalıp kapsamı için güvence altına alıyor.

## Bilinen sınırlar (maskelenmeyenler)

- Yazıyla söylenen numara/e-posta ("sıfır beş yüz ..."), küçük harfli adres ve plaka.
- Kalıpsız ad ("Mehmet'e söyleyin", "ustamız, adı Murat"). "adı X" kalıbı tekne adlarını bozduğu için bilerek eklenmedi.
- Büyük harfle yazılmayan kişi adı, tek başına söylenen soyadı.
- İl/ilçe adı tek başına (örn. "Kadıköy"), marina adı: kişisel veri sayılmaz, korunur.

## NER değerlendirmesi

İssue "gerekirse hafif TR NER değerlendirmesi" diyordu. **Yapılmadı.** Gerekçe: kalıp kapsamında listede olmayan ad geri çağırması ölçüm setinde %100, ama kalıp dışı kalan örnekler (yukarıdaki) ölçümün küçüklüğü yüzünden NER'in ne kadar kazandıracağını güvenilir biçimde göstermiyor; ayrıca NER eklemek yeni ağır bağımlılık (model indirme, CPU süresi) ve ters yönde yanlış maskeleme (tekne/marina adı) riski getirir. Gerçek müşteri verisine geçilmeden önce, **gerçek ses transkriptlerinden elle etiketlenmiş daha büyük bir sette** NER kıyası ayrı bir deney olarak yapılmalıdır. Bu issue'da karar verilmedi, bırakıldı.

## Maskelemenin analiz kalitesine etkisi

`maskeleme_kalite.py`: 6 sentetik çağrı (`call_001, 002, 008, 011, 012, 024`). Her çağrının "ham" sürümünde `[İSİM]`/`[TELEFON]` yerine uydurma ad (Mehmet Yıldız) ve telefon konur, ilk müşteri turuna uydurma adres, plaka ve kart eklenir; "maskeli" sürüm bunun `mask_text` çıktısıdır. İkisi de gerçek LLM hattıyla (4 agent) analiz edilip doğru etiketlerle karşılaştırıldı (model: `nvidia/nemotron-3.5-lightning-30b-a3b` hızlı, `...super-vl-120b-a12b` güçlü).

| Ölçüt | Ham | Maskeli |
|---|---|---|
| Doğru alan (6 çağrı × 11 alan) | 65/66 | 66/66 |
| `call_type`, `request_category`, `urgency`, `next_action`, `sales_outcome` | 30/30 | 30/30 |

Ham sürümdeki tek fark `potential_job` (dolu/boş) alanıdır; ham sürümde model bir "potansiyel iş" uydurdu. LLM kararsız olduğu için bu fark maskelemeye bağlanamaz. **Sonuç:** bu örneklemde maskeleme sınıflandırma, CRM çıkarımı ve satış sonucunu bozmadı. Özetler iki sürümde de içerik olarak aynı (ham sürümde özetleyici kişisel veriyi özete yazmıyor, zaten `find_personal_data` bunu reddeder). **Sınır:** yalnızca 6 çağrı, her biri tek koşu; küçük farklar (özet cümlesi biçimi) ölçülmedi, anlam farkı yalnızca gözle bakıldı. Ücretsiz kota nedeniyle büyütülmedi.

## Günlükte ham veri yok testi

`test_masking_olcum.py`: ham kişisel veri içeren bir transkript `mask_text` ile maskelenip sahte sohbet modeliyle çağrı sınıflandırma ve özetleyici agent'larından geçirilir. Doğrulananlar:

1. LLM'e giden tüm mesajlarda (sistem + kullanıcı) ham değerler (ad, telefon, e-posta, kart, adres, plaka, kimlik, vergi no) yoktur; tekne adı gibi sıradan bilgi korunur.
2. `structlog` ile yakalanan uygulama günlüğü kayıtlarında ham değer yoktur (başarılı ve LLM hatası senaryosu).
3. `agent_runs` satırına dönüşen agent sonuç kayıtlarında (`AgentRun`) ham değer yoktur; LLM hata iletisi ham metin taşımaz.

Kapsam sınırı: test agent katmanını ve günlük çağrılarını denetler; `agent_runs` veritabanı satırını doğrudan okumaz (tablo yalnızca süre, model, jeton ve hata metni tutar, transkript metni içermez). `assistant.rewritten` günlüğü kullanıcının sohbet sorusunu yazar; bu transkript değil, kullanıcının kendi girdisidir ve maskelenmez.

## Yeniden üretme

```bash
cd backend
uv run python -m scripts.maskeleme_olcum                          # LLM'siz, saniyeler
uv run python -m scripts.maskeleme_kalite --calls call_001,call_002,call_008,call_011,call_012,call_024   # .env'de LLM gerekir
uv run pytest tests/test_masking_olcum.py
```
