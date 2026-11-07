# STT kararı: telefon sesi, stereo ve model boyutu (#124)

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
- **Yedek:** yerel model çalışmazsa `STT_PROVIDER=openai_compatible` (anahtar gerekir).
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
