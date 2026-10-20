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

## Sınırlar

- Sesler sentetik (tek Türkçe Piper sesi, perdesi değiştirilmiş). Gerçek santral kaydında aksan, üst üste konuşma ve yankı WER'i artırır.
- 12 çağrı küçük bir örneklem; çağrı başına WER %8 ile %30 arasında değişiyor.
- Kişi adları ve telefon numaraları maskeli referans metinde olmadığı için WER'e katkı yapar (her iki taraf için aynı).
