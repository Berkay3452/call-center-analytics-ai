# STT kararı: telefon sesi, stereo ve model boyutu (#124)

> **Güncel karar (#330, 2026-11-20):** varsayılan model `large-v3-turbo` (beam 1, VAD 0,2, mevcut `initial_prompt`, hotwords kapalı) ve alan düzeltme sözlüğü açık. Aşağıdaki `small` kararları tarihsel kayıttır; ölçümler için "Parametre deneyi (#329)" ve "Alan düzeltme sözlüğü (#330)" bölümlerine bakın. Bellek kısıtlıysa `WHISPER_MODEL=small`.

**Tarih:** 2026-10-20 · **Ses:** 12 sentetik çağrı (Piper, Türkçe), toplam ~15 dk · **Donanım:** CPU (int8)

## Ne ölçüldü

- **Temiz ses:** Piper ile üretilen 16 kHz kayıt.
- **Telefon sesi:** aynı kayıt `scripts.telephone_audio` ile bozuldu: 300–3400 Hz bant, 8 kHz, μ-law (G.711), 18 dB gürültü ve 50 Hz uğultu, ±3 dB seviye dalgası.
- **Mono ve stereo:** stereo kayıtta temsilci sol, müşteri sağ kanalda; müşteri sesinin perdesi yükseltildi (tek Türkçe Piper sesi olduğu için iki kişi gibi duyulsun diye).
- **Ölçütler:** WER (kelime hata oranı, düşük iyi), konuşmacı WER'i (temsilci ve müşteri metni ayrı karşılaştırılır; konuşmacılar ayrılamazsa %100'e yaklaşır), RTF (işlem süresi / ses süresi; 1'in altı gerçek zamandan hızlı).
- **Komut:** `python -m scripts.stt_benchmark --audio <klasör> --model small --layout stereo_rep_left`

## Sonuç

| Yapılandırma | Ses | WER | Konuşmacı WER'i | RTF |
|---|---|---|---|---|
| faster-whisper `small`, mono | temiz | %15,2 | %100 (ayrım yok) | 0,45 |
| faster-whisper `small`, mono | telefon | %21,5 | %100 (ayrım yok) | 0,21 |
| faster-whisper `small`, stereo | temiz | %15,8 | **%14,8** | 0,32 |
| faster-whisper `small`, stereo | telefon | %24,8 | **%24,1** | 0,20 |
| faster-whisper `medium`, stereo | temiz | **%11,4** | **%11,3** | 0,47 |
| faster-whisper `medium`, stereo | telefon | **%15,4** | **%15,0** | 0,49 |

Bulut sağlayıcı (OpenAI uyumlu Whisper API, ör. Groq) ölçülmedi: API anahtarı yok. Altyapı hazır (`STT_PROVIDER=openai_compatible`), anahtar alınınca aynı komutla ölçülebilir.

## Ölçüm sırasında bulunan iki hata (düzeltildi)

1. **Stereo'da konuşma sırası bozuluyordu.** Her kanal ayrı çözülüp zamana göre birleştiriliyor. Whisper segmentleri bir konuşmacının sessizliğini aşıp onun iki sırasını tek segmentte birleştirdiği için müşterinin cevabı temsilcinin sorusundan önce sıralanıyordu (WER %48). Kanal çözümünde kelime zamanları açıldı ve segmentler 0,8 sn'den uzun duraklamalardan bölünüyor; WER %15,8'e indi, tur sayısı doğru.
2. **Dar bant telefon sesinde konuşma atılıyordu.** Whisper'ın ses etkinliği filtresi (VAD) varsayılan 0,5 eşikte telefon sesindeki konuşmayı sessizlik sandı: bir kanalda 97 kelimeden 28'i kaldı (WER %82). Eşik ayarlanabilir yapıldı (`WHISPER_VAD_THRESHOLD`, varsayılan 0,2); telefon sesinde WER %24,8'e indi. Temiz seste etkisi yok (mono temiz: 0,5 eşikte %15,4, 0,2 eşikte %15,2).

## Karar

- **Kanal düzeni: stereo, temsilci sol** (`STT_CHANNEL_LAYOUT=stereo_rep_left`, yeni varsayılan). Santral kayıtları iki kanallıdır; konuşmacı ayrımı yalnızca stereo ile mümkün (mono'da konuşmacı WER'i %100). Mono yüklenen dosyalar otomatik mono işlenir, konuşmacı "bilinmiyor" olur.
- **Mono için ayrı bir konuşmacı ayrımı yöntemi şimdilik eklenmedi.** Sıra tahmini gibi basit yöntemler kısa ve üst üste binen konuşmalarda güvenilmez; demo ve santral senaryosu stereo.
- **Model:** geliştirme ve demo için `small` varsayılan kalır (telefon sesinde RTF 0,2: 3 dakikalık çağrı ~40 sn). Doğruluk öncelikliyse `medium` (telefon sesinde WER %24,8 → %15,4, RTF 0,49: 3 dakikalık çağrı ~1,5 dk). Canlıda GPU varsa `large-v3` denenmeli.
- **Yedek:** yerel model çalışmazsa `STT_PROVIDER=openai_compatible` (anahtar ve `STT_ALLOW_EXTERNAL=true` gerekir). **Dikkat:** bu sağlayıcı ham sesi üçüncü tarafa gönderir; maskeleme sesten önce uygulanamaz, kişisel veri dışarı çıkar. Bu yüzden varsayılan kapalıdır (#270).
- **Seed sesleri** artık varsayılan olarak stereo üretilir: `uv run --with piper-tts python -m scripts.generate_audio --force`.

## Hız ayarı ölçümü (#163)

**Tarih:** 2026-10-31 · **Ses:** `call_001-003` seed kayıtları (stereo, ~60-74 sn) · **CPU:** int8 · **Komut:** `python -m scripts.stt_benchmark --audio <klasör> --layout stereo_rep_left --model small --beam 1 --threads 0`

| Yapılandırma | WER | RTF | 1 dk'lık çağrı STT |
|---|---|---|---|
| `small`, beam 5 | %20,2 | 0,26 | ~16 sn |
| `small`, beam 2 | %20,4 | 0,19 | ~11 sn |
| **`small`, beam 1** | **%20,7** | **0,18-0,21** | **~11-13 sn** |
| `base`, beam 1 | %27,4 | 0,12 | ~7 sn |
| `medium`, beam 1 | %15,6 | 0,56 | ~34 sn |

- Beam 5 → 1: doğruluk farkı 0,5 puan altında (örnek küçük), süre yaklaşık %30 azalıyor. Varsayılan `WHISPER_BEAM_SIZE=1` yapıldı.
- `base` 6-7 puan daha yanlış; kazanç (~4 sn) buna değmez. `medium` daha doğru ama 1 dk'lık çağrı ~34 sn: 30 sn hedefini aşıyor, doğruluk öncelikliyse seçilebilir.
- Thread: otomatik (0) en iyisi; 4 thread belleği sıkıştırıp hata verdi, hız kazancı görülmedi.
- **Model yeniden yüklenmiyor:** model süreç başına bir kez yüklenir (`_transcriber()` ve `_load_whisper` önbelleği, testi `test_whisper_model_is_loaded_once_per_process`). İlk görevdeki soğuk yükleme `small` için ~3 sn; darboğaz değil.
- İki kanalı paralel çözmek CPU'da kazanç getirmez (CTranslate2 zaten tüm çekirdekleri kullanır, modelde kilit var). Bulut Whisper (Groq) anahtar olmadığı için ölçülmedi.
- **Sonuç:** 1 dk'lık çağrıda STT ≈ 11-13 sn (hedef ≤ 30 sn tutuyor). Not: ölçüm sırasında bellek daraldığında RTF 1'e fırladı (aynı dosyada 0,2 → 1,19); STT sırasında RAM boş olmalı, Docker'da `stt` kuyruğu tek eşzamanlılıkla çalışmalı.

## Ses üretim yöntemi: Piper ve Edge TTS (#214)

**Tarih:** 2026-11-07 · **Ses:** `call_001, 005, 010, 017, 023, 031` (stereo, temsilci sol; 6 çağrı, Edge ~9,5 dk / Piper ~6,3 dk) · **Model:** `small`, beam 1, VAD 0,2, CPU int8 · **Komut:** `python -m scripts.stt_benchmark --audio <klasör> --providers faster_whisper --model small --beam 1 --layout stereo_rep_left`

Telefon bozulması: `scripts.telephone_audio` (8 kHz dar bant, SNR 18 dB). Edge sesleri: temsilci `tr-TR-EmelNeural`, müşteri `tr-TR-AhmetNeural` (iki ayrı nöral ses; Piper'da tek ses, müşteri perdesi 1,15 ile ayrılıyor).

| TTS | Ses | WER | Konuşmacı WER | Toplam RTF | Tepe bellek | Model yükleme |
|---|---|---|---|---|---|---|
| Piper (tr_TR-dfki-medium) | temiz | %20,0 | %19,1 | 0,19 | 726 MB | 2,7 sn |
| Piper | telefon | %29,1 | %27,9 | 0,19 | 1061 MB | 1,9 sn |
| **Edge TTS** | temiz | **%16,4** | **%16,2** | 0,17 | 1067 MB | 5,3 sn |
| **Edge TTS** | telefon | **%28,6** | **%27,4** | 0,25 | 1043 MB | 2,9 sn |

- Edge sesleri daha doğal ve daha yavaş/akıcı (aynı çağrı ~%40 daha uzun: 103 sn / 73 sn); temiz seste WER 3,6 puan daha iyi, telefonda fark yok (0,5 puan). Yani Edge, Piper'a göre kolay bir test değil; "daha gerçekçi ses" beklentisi karşılandı.
- Tepe bellek sürecin çalışma kümesi tepesidir ve ölçüm sırasındaki bellek baskısına göre dalgalanıyor (726-1067 MB); `small` için ~1,1 GB'a göre planlayın.
- RTF dalgalanması (0,10 - 0,66, tek dosyalarda) ölçüm sırasında diğer süreçlerin bellek baskısındandır; toplam RTF 0,17-0,25: 1 dk'lık çağrı için ~10-15 sn.
- Telefon kalitesinde WER ~%29 (her iki TTS): yalnızca sentetik, dar bant bozulmalı ses; gerçek santral kaydı için aşağıdaki betik kullanılacak.

**Karar:**
- Model **değişmiyor**: faster-whisper `small`, beam 1, stereo. Medium/large bu ölçümde çalıştırılmadı (bellek kısıtı); önceki ölçüm (#124/#163) geçerli. `distil-whisper` yalnızca İngilizce olduğu için Türkçede uygun değil; bulut STT için API anahtarı yok.
- **Seed/demo sesleri için Edge TTS önerilir** (iki ayrı nöral ses, daha gerçekçi tempo). Piper çevrimdışı yedek olarak kalır ve varsayılan motordur: `uv run --extra stt --with edge-tts python -m scripts.generate_audio --engine edge`. Edge internet gerektirir; üretilen `.wav` dosyaları üretildikten sonra çevrimdışı çalışır, dolayısıyla demo internetsiz de çalışır.
- Üretim akışı değişmedi: STT hâlâ yerel faster-whisper; yalnızca sentetik ses üretim aracına bir motor seçeneği eklendi.

## Hata tablosu ve alan terimi ölçümü (#328)

**Tarih:** 2026-11-20 · **Ses:** `call_001, 005, 010, 017, 023, 031` (Edge TTS, stereo, telefon bozulmalı 8 kHz SNR 18 dB; 6 çağrı, ~9,5 dk) · **Model:** `small`, beam 1, VAD 0,2, int8 · **Komut:**

```
python -m scripts.stt_benchmark --audio <klasör> --model small --beam 1 --layout stereo_rep_left --out sonuc.json
python -m scripts.stt_hata_tablosu sonuc.json
```

Genel WER, "ve" ve "bir" gibi sözcüklerle seyrelir. Bu yüzden benchmark artık **alan terimi doğruluğunu** da yazdırır: marka, parça, yer, tekne adı, gün/ay ve sayı sözcüklerinin doğru yazılma oranı. Sözlük `backend/tests/data/stt_referans/terimler.json` (kök bazlı: `akü` için `aküyü` de sayılır; `=` önekli kısa kökler yalnız tam eşleşir). Referans metin `data/synthetic/calls` içindeki sentetik görüşmelerdir. Taban ölçüm çıktısı `backend/tests/data/stt_referans/small_telefon_baz.json`.

**Ölçüm düzeltmesi:** Whisper sayıları rakamla yazar ("1300", "15"), referans sözcükle ("bin üç yüz", "on beş"); ayrıca "Marina'da" referansta iki sözcük, çıktıda tek sözcüktür. Bunlar tanıma hatası değildir. Sayı terimi ölçümünde rakamlar sözcüğe çevrilir ve bu farklar hata tablosunda ayrı `biçim` sınıfına girer. Genel WER'in tanımı **değişmedi**, önceki ölçümlerle karşılaştırılabilir.

| Ölçüt | Değer |
|---|---|
| WER (telefon, `small`) | %25,3 (çağrı başına %17,8 - %37,6) |
| Konuşmacı WER'i | %24,6 |
| RTF | 0,10 (tepe bellek ~720 MB) |
| **Alan terimi doğruluğu** | **%72,5 (66/91)** |

| Terim sınıfı | Doğru / toplam | Doğruluk |
|---|---|---|
| marka | 0 / 2 | %0 |
| parça | 13 / 21 | %62 |
| yer | 16 / 24 | %67 |
| tekne adı | 4 / 5 | %80 |
| gün/ay | 1 / 3 | %33 |
| sayı | 32 / 36 | %89 |

Hata öbekleri (109): genel sözcük 67, biçim farkı 15, parça 9, yer 8, sayı 6, marka 2, gün/ay 1, tekne adı 1.

### Hata sınıfları ve çözüm notları

| Sınıf | Örnek (beklenen → yazılan) | Kök neden | Hangi çözüm işe yarar |
|---|---|---|---|
| Marka/model | Jeanneau Sun Odyssey → "ve anne husan odisi"; Lagoon 42 → "le boncris 2" | Yabancı ad, Türkçe okunuşla duyuluyor | `initial_prompt`/`hotwords` ile marka listesi; büyük model; düzeltme sözlüğü (çok sınırlı sayıda yazım) |
| Parça adı | akü → "aki"/"akı"; devir → "delil"; vinç → "winch"; jeneratör → "generator"; egzoz → "exozdan"; bimini → "diminin" | Benzer sesli Türkçe sözcüğe kayma ya da İngilizce yazım | `hotwords`; `medium`; düzeltme sözlüğü (`generator`→`jeneratör`, `winch`→`vinç` güvenli; "aki" gerçek Türkçe sözcük olduğu için bağlam gerekir) |
| Yer/marina | Tuzla → "buza"/"suzla"; Milta → "miysa"; Fora Göcek D-Marin → "bora göcekdemarin" | Özel ad, ek, birleştirme | `hotwords`/`initial_prompt` yer listesi; düzeltme sözlüğü |
| Sayı | yirmi dakika → "yemin akika"; üç adet → "müşadet" | Dar bant sesinde heceler karışıyor | Büyük model; ses ön işleme |
| Biçim | on beş ↔ "15"; Marina'da ↔ "marinada" | Yazım tercihi | Düzeltme gerekmez; ölçümde ayrı tutulur |
| Genel | Terim olmayan sözcükler | Ses kalitesi, model kapasitesi | Büyük model |

**Sonuç (#329 ve #330 için):** terim hatalarının çoğu `small`'ın dar bant sesinde özel ad ve yabancı sözcükte yanılmasından geliyor. Önce model/`hotwords`/`initial_prompt` deneyi (#329), sonra yalnızca güvenli, bağlamdan bağımsız yazım hataları için düzeltme sözlüğü (#330) mantıklı.

**Berkay'ın gözlemleri:** gerçek kullanımda gördüğü yanlış yazımlar (ses/çağrı → beklenen → yazılan) henüz eklenmedi; geldiğinde bu tabloya ve `terimler.json`'a işlenecek.

**Sınırlar:** 6 sentetik çağrı, tek TTS motoru (Edge). Terim sayısı küçük (91 geçiş), yüzdeler ±birkaç puan oynar. Gerçek aksan ve gürültüde farklı çıkabilir.

## Parametre deneyi: model, beam, VAD, hotwords ve initial_prompt (#329)

**Tarih:** 2026-11-20 · **Ses:** #328'deki 6 sentetik çağrı (Edge TTS, stereo, telefon bozulmalı, ~9,5 dk) · **CPU:** int8, GPU yok · **Her satır ayrı süreçte**, stereo temsilci sol, VAD 0,2 (aksi belirtilmedikçe), beam 1 (aksi belirtilmedikçe) · **Komut:** `python -m scripts.stt_benchmark --audio <klasör> --model <m> [--beam 5] [--vad-threshold 0.3] [--initial-prompt "..."] [--hotwords "..."] --out sonuc.json`

Ölçütler: WER (çağrı ortalaması), **terim doğruluğu** (#328, 91 terim geçişi), toplam RTF, tepe çalışma kümesi. Süre bütçesi: 3 dakikalık çağrı için STT ≤ 2 dk, yani **RTF ≤ 0,67** (1 dk'lık çağrıda ≤ 40 sn).

| Yapılandırma | WER | Terim doğruluğu | RTF | Tepe bellek |
|---|---|---|---|---|
| `small`, beam 1, mevcut istem (**şimdiki varsayılan**) | %25,3 | %72,5 (66/91) | 0,09 | 723 MB |
| `small`, beam 5 | %23,3 | %78,0 (71/91) | 0,14 | 723 MB |
| `small`, istem kapalı | %28,0 | %69,2 (63/91) | 0,15 | 1063 MB |
| `small`, genişletilmiş istem | %25,6 | %82,4 (75/91) | 0,15 | 723 MB |
| `small`, yalnız hotwords | %26,9 | %84,6 (77/91) | 0,20 | 1106 MB |
| `small`, genişletilmiş istem + hotwords | %27,2 | %86,8 (79/91) | 0,15 | 1095 MB |
| `small`, VAD 0,3 | %24,3 | %75,8 (69/91) | 0,10 | 723 MB |
| `small`, beam 5 + istem + hotwords + VAD 0,3 | **%22,2** | %82,4 (75/91) | 0,23 | 736 MB |
| `medium`, beam 1 | %15,0 | %83,5 (76/91) | 0,27 | 1771 MB |
| `medium`, istem + hotwords | %16,9 | %91,2 (83/91) | 0,47 | 2842 MB |
| **`large-v3-turbo`, beam 1** | **%14,1** | **%91,2 (83/91)** | 0,28 | 1936 MB |
| `large-v3-turbo`, istem + hotwords | %18,1 | **%92,3 (84/91)** | 0,35 | 1908 MB |

Genişletilmiş istem: mevcut istem + parça (jeneratör, enjektör, şanzıman...), marka (Jeanneau, Bavaria, Cummins...) ve yer (Tuzla, Göcek, Bodrum...) adları. Hotwords: aynı sözcüklerin istemsiz listesi. Metinler `scratchpad/matris.py` deney betiğinde; varsayılan değişirse `config.py`'ye taşınır (#330).

### Bulgular

- **Model en büyük kaldıraç.** `large-v3-turbo`, `medium`'dan hem daha doğru (WER %14,1 - %15,0) hem de daha az bellek kullanıyor ve aynı hızda (RTF 0,28): `small`'a göre WER 11 puan düşüyor, RTF 3 kat artıyor ama süre bütçesinin çok altında (3 dk'lık çağrı ~50 sn). Bellek 0,7 GB → ~1,9 GB; 15,7 GB RAM'de makul, ama Docker ile birlikte çalışırken boş bellek daralıyor.
- **Alan sözlüğü (istem + hotwords) terimi düzeltir, genel WER'i bozar.** `small`'da terim doğruluğu %72,5 → %86,8 (WER +1,9 puan); `medium` ve `turbo`'da WER 2-4 puan kötüleşiyor (terim dışı sözcüklerde uydurma ve yanlış öneri). Güçlü modelde sözlük gereksiz, `small`'da değerli.
- **Beam 5**: `small`'da WER -2 puan, terim +5,5 puan, ama RTF 0,09 → 0,14 (#163'teki "fark <0,5 puan" bulgusu bu sette geçerli değil; telefon sesinde ve terim ölçümünde fark var).
- **VAD 0,3** telefon sesinde zararsız ve hafif iyi (WER -1 puan, RTF aynı). Daha fazla deney gerekir; varsayılan 0,2 kalır.
- **İstemi kapatmak** her ölçütü kötüleştirir; mevcut istem değerli.
- **Hepsi bir arada** (beam 5 + istem + hotwords + VAD 0,3) `small`'da en düşük WER'i (%22,2) verir, ama terim doğruluğu yalnız istem + hotwords kadar yüksek değil; `turbo` bunun hepsini geçer.

### Sınırlar

- 6 çağrı, ~9,5 dk, tek TTS motoru; WER çağrı başına %8-%38 dalgalanır, 1-2 puanlık farklar gürültü sınırında. Terim sayısı 91; terim yüzdeleri ±birkaç puan oynar.
- Tepe bellek çalışma kümesidir ve ölçüm sırasında açık Docker/uygulamalara göre dalgalanır (aynı model 723-1106 MB).
- `large-v3-turbo` ilk çalıştırmada ~1,6 GB iner (yükleme süresi 100 sn bunu içerir; sonraki yükleme ~4 sn).
- Dar bant ön işleme (8 kHz yeniden örnekleme etkisi): bu sette ses zaten 8 kHz telefon bozulmalı; temiz ses (16 kHz) ayrıca ölçülmedi, #332'de ele alınır.

### Karar ve sonraki adım

Bu issue yalnız ölçer; **varsayılan değişikliği #330'da** yapılır (`config.py` ve `.env.example`). Öneri: `large-v3-turbo`, beam 1, mevcut istem (hotwords kapalı); bellek kısıtlı ortamda yedek: `small` + genişletilmiş istem + hotwords. Karar #332'deki model karşılaştırmasıyla birlikte netleşir (aynı turbo adayı).

## Alan düzeltme sözlüğü ve varsayılan ayarın güncellenmesi (#330)

**Tarih:** 2026-11-20 · **Ses:** #328/#329'daki 6 sentetik telefon çağrısı · **Komut:** `python -m scripts.stt_benchmark --audio <klasör> --model <m> --beam 1 --layout stereo_rep_left`

### Düzeltme sözlüğü

`backend/app/stt/duzeltme.py` + `duzeltme_sozlugu.json`. Sağlayıcı katmanında segment metnine uygulanır (normal, canlı, mono/stereo ve benchmark aynı yolu kullanır). Sıra: **STT çıktısı → düzeltme → maskeleme** (`store_segments`); düzeltme yalnız alan sözcüklerine dokunur, kişisel veriye ve günlüğe dokunmaz.

- **Yalnız Türkçe'de karşılığı olmayan yazımlar** var: `generator`→`jeneratör`, `winch`→`vinç`, `exoz/eksoz`→`egzoz`, `malina`→`marina`, `akdemiz`→`akdeniz`, `suzla/duzla`→`tuzla`, `aküller`→`aküler`, `dimini`→`bimini`. Hata tablosunda en sık görünen ama **gerçek Türkçe sözcüğe** dönüşenler (`akı`, `delil`, `buza`, `bora`, `limin`) bilerek yok: bağlam olmadan doğru kelimeyi bozarlar.
- Tam sözcük eşleşir, büyük/küçük harf korunur, `ek: true` kuralda Türkçe ek korunur (`exozdan`→`egzozdan`), tek geçiştir.
- Ayarlar: `STT_CORRECTION_ENABLED` (varsayılan açık), `STT_CORRECTION_FILE` (ek kurallar, varsayılanları geçersiz kılamaz).
- **Yanlış pozitif testi:** 100 sentetik görüşmenin (>1000 tur) ve usta notlarının doğru metninde sıfır değişiklik (`tests/test_stt_duzeltme.py`).

### LLM ile düzeltme (yalnız denendi, eklenmedi)

STT çıktısı (sentetik, kişisel veri yok) LLM'e "yalnız açıkça yanlış duyulmuş parça/marka/yer adlarını düzelt" istemiyle verildi.

| STT | WER önce → sonra | Terim doğruluğu önce → sonra | LLM süresi |
|---|---|---|---|
| `small` | %25,3 → %24,7 | 66/91 → 68/91 | ~5 sn/çağrı |
| `large-v3-turbo` | %14,1 → %13,9 | 83/91 → 84/91 | ~3 sn/çağrı |

Kazanç 1-2 terim; çağrıların bir kısmında LLM geçerli çıktı üretemedi (şema hatası), ek gecikme ve harici servise metin gitmesi var. **Eklenmedi:** sözlük aynı kazancın çoğunu bedavaya veriyor.

### Önce / sonra

| Yapılandırma | WER | Terim doğruluğu | RTF | Bellek |
|---|---|---|---|---|
| `small`, beam 1, sözlük yok (önceki varsayılan) | %25,3 | %72,5 (66/91) | 0,09 | 723 MB |
| `small`, beam 1, + sözlük | %24,5 | %79,1 (72/91) | ~0,1* | 723 MB |
| `large-v3-turbo`, beam 1, sözlük yok | %14,1 | %91,2 (83/91) | 0,28 | 1936 MB |
| **`large-v3-turbo`, beam 1, + sözlük (yeni varsayılan)** | **%13,8** | **%93,4 (85/91)** | 0,30 | 1908 MB |

\* `small` + sözlük koşusunda RTF 0,33 görünüyor; aynı anda LLM deneyi koştuğu için gürültü. Sözlük metin üzerinde çalışır, STT süresine ölçülebilir katkısı yoktur.

Toplam kazanç: **WER %25,3 → %13,8** (11,5 puan), **terim doğruluğu %72,5 → %93,4** (+21 puan), RTF 0,09 → 0,30 (3 dk'lık çağrıda ~54 sn; bütçe ≤ 2 dk).

### Karar

- **Varsayılan model `small` → `large-v3-turbo`** (`config.py`, `.env.example`; beam 1, VAD 0,2, mevcut `initial_prompt`, hotwords kapalı). #329'da genel WER'i bozduğu için `initial_prompt` genişletmesi ve hotwords varsayılan yapılmadı; `small`'a düşen ortamlarda `WHISPER_INITIAL_PROMPT` + `WHISPER_HOTWORDS` ile terim doğruluğu %72,5 → %86,8 çıkarılabilir.
- **Bedel:** bellek 0,7 → ~1,9 GB, ilk çalıştırmada ~1,6 GB indirme. Bellek kısıtlı makinede `WHISPER_MODEL=small`.
- **Sözlük açık.** Yeni kural ekleme: Berkay'ın gerçek kullanımdaki yanlış yazımları geldikçe `duzeltme_sozlugu.json`'a eklenir; her yeni kural yanlış pozitif testinden geçmelidir.

### Sınırlar

- Sözlük kuralları bu 6 çağrının hatalarından türetildi; **aynı sette ölçülen kazanç iyimserdir** (kapalı bir sınama kümesi yok). Yanlış pozitif tarafı 100 görüşmeyle güvence altında, ama gerçek ses ve gerçek yanlış yazımlar farklı olabilir.
- 6 sentetik çağrı, 91 terim: yüzdeler ±birkaç puan oynar; gerçek aksan/gürültüde fark değişir.

## Karşılaştırma adayları ve elenenler (#331)

**Tarih:** 2026-11-20 · Bilgiler Hugging Face model sayfaları ve API'sinden alındı (boyut, lisans, Türkçe etiketi, CT2 yapısı). Model kartlarındaki WER değerleri **yazarların kendi doğrulama setlerinden** ve okuma sesindendir; telefon sesi için karşılaştırılamaz, bu yüzden karar yalnız bizim sentetik telefon setimizdeki ölçümle verilir (#332).

### Ölçülecek adaylar (`app/stt/adaylar.py`)

| Aday | Sağlayıcı / model | İndirme | Lisans | Zaman damgası | Not |
|---|---|---|---|---|---|
| `small` | faster-whisper `small` | 0,48 GB | MIT | segment + kelime | Önceki varsayılan (referans) |
| `medium` | faster-whisper `medium` | 1,53 GB | MIT | segment + kelime | #124/#329'da ölçüldü |
| `large-v3` | `Systran/faster-whisper-large-v3` | 3,09 GB | MIT | segment + kelime | int8 ~2-3 GB bellek |
| `large-v3-turbo` | faster-whisper `large-v3-turbo` | 1,62 GB | MIT | segment + kelime | **Mevcut varsayılan** (#330) |
| `large-v3-tr` | `oguzhangokboru/whisper-large-v3-tr` (CT2) | 3,09 GB | Apache-2.0 | segment + kelime | large-v3'ün Türkçe ince ayarı, ~272 saat herkese açık Türkçe ses |
| `turbo-tr-itu` | `RsGoksel/RsGoksel_ITU_Mainframe-ct2` (CT2) | 1,62 GB | MIT | segment + kelime | large-v3-turbo'nun Türkçe ince ayarı |
| `xlsr-tr` | `mpoyraz/wav2vec2-xls-r-300m-cv8-turkish` (CTC) | 1,26 GB | Apache-2.0 | kelime (CTC çerçevesi) | Kart WER %10,6 (Common Voice 8, okuma sesi); noktalama, büyük harf, rakam yok |
| `groq-large-v3` | OpenAI uyumlu API (Groq `whisper-large-v3`) | — | MIT (model) | segment | Ses üçüncü tarafa gider; yalnız sentetik ses; **`STT_API_KEY` gerekir** |

Tüm Whisper adayları Türkçeyi (`tr`) destekler (model sayfası etiketi); CT2 adayları `faster-whisper` ile doğrudan çalışır (repo adı `--model` olarak verilir). 15,7 GB RAM ve GPU'suz CPU sınırı: `large-v3` ve `large-v3-tr` bellek bakımından sınırda.

### Elenenler

| Aday | Gerekçe |
|---|---|
| `distil-whisper` | Yalnız İngilizce (daha önce elendi, #124). |
| `facebook/mms-1b-all` (Türkçe adaptör) | Lisans **CC-BY-NC-4.0** (ticari olmayan), ~3,9 GB / 1 milyar parametre, CTC (noktalama ve rakam yok); CPU ve bellek bütçesine ve lisansa uymuyor. |
| `m3hrdadfi/wav2vec2-large-xlsr-turkish`, `cahya/wav2vec2-large-xlsr-turkish` | Eski XLSR-53 modelleri, kartlarda Common Voice TR WER %27,5 ve %21,1; aynı aileden `mpoyraz` (%10,6) daha iyi ve daha yeni, o ölçülür. |
| `Huseyin/whisper-large-v3-turkish-finetuned`, `BuzzASR/turkish`, `selimc/whisper-large-v3-turbo-turkish` | Kartlarda CTranslate2 (faster-whisper) yapısı yok; PyTorch Transformers ile çalışır, CPU'da ağır ve canlı transkript yolu (faster-whisper) dışında kalır. CT2 dönüşümü ayrı iş; ölçüm sonucu Türkçe ince ayarın değer kattığını gösterirse (`large-v3-tr`, `turbo-tr-itu`) yeniden bakılır. |
| Ücretsiz kotalı bulut (Groq) | Elenmedi, ama **ölçülemiyor**: projede Groq anahtarı yok (`LLM_PROVIDER=nvidia`). Altyapı hazır; anahtar alınırsa aynı komutla ölçülür. |

### Tek komutla çalıştırma

```
cd backend
uv run --extra stt --with torch --with transformers python -m scripts.stt_aday_kosusu --audio <ses klasörü> --out-dir <sonuç klasörü>
uv run --extra stt python -m scripts.stt_benchmark --list-candidates          # adaylar
uv run --extra stt python -m scripts.stt_benchmark --candidate large-v3 --audio <klasör>   # tek aday
```

Her aday ayrı süreçte koşar (tepe bellek ve model yükleme süresi karışmaz); sonunda Markdown tablo basılır. Harici aday için `STT_API_KEY` ortam değişkeni gerekir; yoksa atlanır. `STT_ALLOW_EXTERNAL=false` varsayılanı ve `.env` değişmez: harici izin yalnız o koşunun sürecinde verilir. Üretim varsayılanı bu adaylardan etkilenmez. `torch` ve `transformers` projenin bağımlılığı değildir; yalnız `xlsr-tr` için geçici eklenir.

## Model karşılaştırması: ölçüm sonuçları ve karar (#332)

**Tarih:** 2026-11-20 · **Ses:** #328'deki 6 sentetik çağrı (`call_001, 005, 010, 017, 023, 031`), **Edge TTS, stereo, telefon bozulmalı** (8 kHz, SNR 18 dB; ~9,5 dk) · **Ayar:** beam 1, VAD 0,2, mevcut `initial_prompt`, düzeltme sözlüğü açık (#330) · **CPU:** int8, GPU yok, 15,7 GB RAM (ölçüm sırasında ~3 GB boş) · **Komut:** `python -m scripts.stt_aday_kosusu --audio <klasör> --out-dir <klasör>` (her aday ayrı süreçte)

| Aday | WER | Konuşmacı WER | Terim doğruluğu | RTF | Tepe bellek | Model yükleme |
|---|---|---|---|---|---|---|
| `small` | %24,5 | %23,8 | %79,1 (72/91) | 0,11 | 731 MB | 5,8 sn |
| `medium` | %14,7 | %15,0 | %86,8 (79/91) | 0,29 | 1778 MB | 5,5 sn |
| `large-v3` | ölçülemedi | | | | | `mkl_malloc` bellek hatası |
| **`large-v3-turbo`** (varsayılan) | **%13,8** | %12,6 | **%93,4 (85/91)** | 0,29 | 1916 MB | 5,1 sn |
| `large-v3-tr` (Türkçe ince ayar) | ölçülemedi | | | | | `mkl_malloc` bellek hatası |
| `turbo-tr-itu` (turbo Türkçe ince ayar) | %13,0 | **%10,1** | %87,9 (80/91) | 0,32 | 1940 MB | 100,5 sn* |
| `xlsr-tr` (wav2vec2 CTC) | %93,3 | %69,1 | %33,0 (30/91) | 1,31 | 3203 MB | — |
| `groq-large-v3` (bulut) | ölçülemedi | | | | | API anahtarı yok |

\* `turbo-tr-itu`'nun yükleme süresi ilk indirmeyi içerir (~1,6 GB); sonraki yüklemeler diğer turbo gibi ~5 sn.

### Bulgular

- **`large-v3-turbo` en iyi denge:** `small`'a göre WER 10,7 puan ve terim doğruluğu 14 puan daha iyi; `medium`'dan hem daha doğru hem aynı hızda. 3 dakikalık çağrı ~52 sn (bütçe ≤ 2 dk).
- **Türkçe ince ayar (`turbo-tr-itu`) turbo'yu geçmiyor:** genel WER 0,8 puan ve konuşmacı WER'i 2,5 puan düşük, ama terim doğruluğu 5,5 puan kötü ve RTF biraz yüksek. Fark 6 çağrıda gürültü sınırında; model kartındaki ölçütler yazarın kendi setinden. Değiştirmeye değmez.
- **`xlsr-tr` (wav2vec2) bu veride işe yaramıyor:** WER %93, RTF 1,31 (gerçek zamandan yavaş), ~3,2 GB bellek. Model okuma sesiyle (Common Voice) eğitilmiş; 8 kHz μ-law dar bant telefon sesine ve TTS tempolarına uymuyor; ayrıca noktalama/rakam üretmez. Elendi.
- **`large-v3` ve `large-v3-tr` bu makinede yüklenemedi:** `RuntimeError: mkl_malloc: failed to allocate memory`. Boş RAM ~3 GB ve C: diski dolu olduğu için sayfa dosyası da dar; model 3,09 GB (int8 yükleme ~3 GB+). Bu, "15,7 GB RAM, GPU yok, Docker açıkken" koşulunda bu iki adayın **kullanılamaz** olduğu anlamına gelir; ayrıca turbo (`large-v3`'ün damıtılmışı) zaten benzer doğruluk veriyor.
- **Bulut (Groq) ölçülemedi:** projede anahtar yok (`LLM_PROVIDER=nvidia`). Altyapı hazır (`STT_PROVIDER=openai_compatible`); anahtar alınırsa aynı komutla ölçülür. Ses üçüncü tarafa gideceği için güvenlik katmanı gereği yine yalnız sentetik ses ve bilinçli onayla.

### Karar

**Model değişmiyor:** varsayılan `large-v3-turbo` (beam 1, #330) kalır. Hiçbir aday doğruluk, hız ve bellek bütçesini birlikte turbo'dan daha iyi karşılamıyor. Değişiklik gerektirirse (ör. gerçek ses sonrası) `turbo-tr-itu` ilk bakılacak adaydır; bunun için `stt/registry.py` değişikliği gerekmez (`WHISPER_MODEL=RsGoksel/RsGoksel_ITU_Mainframe-ct2`).

### Sınırlar

- **Yalnız Edge + telefon seti ölçüldü** (6 çağrı, ~9,5 dk). Issue'nun istediği Piper ve temiz ses setleri koşulmadı; kalan zamanda adayların çoğu elendi ya da ölçülemedi, tablodaki sıralamanın temiz seste değişmesi beklenmez ama doğrulanmadı.
- **Gerçek müşteri sesi kullanılmadı.** Sentetik seste (TTS, düz tempo) sonuçlar gerçek aksan, gürültü ve üst üste konuşmada farklı olabilir; telefon bozulması simülasyondur.
- 6 çağrı, 91 terim: yüzdeler ±birkaç puan oynar; 1-2 puanlık farklar (ör. turbo ile turbo-tr arasındaki WER) anlamlı sayılmamalı.
- Tepe bellek çalışma kümesidir ve ölçüm sırasındaki bellek baskısına göre dalgalanır. `large-v3`/`large-v3-tr` bu makinedeki o anki boş belleğe göre yüklenemedi; 16 GB'ın tamamı boş bir makinede çalışabilir.

## Gerçek ekip kayıtları (#150): betik hazır, kayıt bekleniyor

Gerçek kayıtlar henüz yok; üretilmiş seslerle yetinilmiyor, issue açık kalır. Kayıt geldiğinde (kişisel veri: repoya koymayın, repo dışı bir klasör, ör. `D:\gercek_kayitlar`):

```
kayit_01.wav          # stereo ise temsilci sol kanal
kayit_01.txt          # isteğe bağlı: elle yazılmış doğru metin ("Temsilci: ..." / "Müşteri: ..." satırları) -> WER/CER
kayit_01.truth.json   # isteğe bağlı: beklenen alanlar (data/synthetic/truth ile aynı biçim) -> 7 alan doğruluğu
```

```
cd backend
uv run --extra stt python -m scripts.real_recordings_eval --dir D:\gercek_kayitlar --out D:\gercek_kayitlar\sonuc.json
uv run --extra stt python -m scripts.real_recordings_eval --dir D:\gercek_kayitlar --stt-only   # LLM kullanmadan yalnızca STT
```

Betik her kayıt için WER/CER, RTF, STT ve analiz süresini ve (truth varsa) 7 CRM alanının doğruluğunu (`request_category`, `location`, `problem`, `service_mode`, `urgency`, `potential_job`, `next_action`) yazdırır; sonda Markdown tabloyu bu belgeye yapıştırılabilir biçimde basar. Mono kayıtlarda `--layout mono` kullanın (konuşmacı ayrımı olmaz; WER geçerli, konuşmacıya göre alanlar etkilenir).

## Sınırlar

- Sesler sentetik (Piper tek ses, perdesi değiştirilmiş; Edge TTS iki nöral ses). Gerçek santral kaydında aksan, üst üste konuşma ve yankı WER'i artırır.
- 12 çağrı küçük bir örneklem; çağrı başına WER %8 ile %30 arasında değişiyor.
- Kişi adları ve telefon numaraları maskeli referans metinde olmadığı için WER'e katkı yapar (her iki taraf için aynı).
