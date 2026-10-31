# Analiz uçtan uca süresi: aşama aşama (#162)

**Tarih:** 2026-10-31 · **Çağrı:** `call_001` (sentetik) · **LLM:** NVIDIA Nemotron (ücretsiz katman)

## Aşamalar ve nereden okunur

Yüklemeden sonuca kadar her aşama günlüğe yazılır (kimlik: `call_id`):

| Aşama | Günlük olayı / alan | Ölçüm |
|---|---|---|
| Kuyrukta bekleme (STT görevi başlayana kadar) | `stt.saved` → `queue_wait_s` | yükleme → STT başlangıcı |
| STT (yazıya çevirme) | `stt.saved` → `processing_s` | Whisper işlem süresi |
| STT sonucunu kaydetme | `stt.saved` → `save_s` | veritabanı yazımı |
| Analiz görevinin başlangıcı | `analysis.timing` → `since_created_s` | yüklemeden beri geçen toplam (STT + kuyruk dahil) |
| Bağlam yükleme | `analysis.timing` → `load_s` | transkript okuma |
| Agent'lar | `analysis.timing` → `agents_s`, `agent_s{}` | toplam ve her agent ayrı |
| Sonucu kaydetme | `analysis.timing` → `save_s` | analiz + eşleştirme yazımı |

Her agent'ın süresi ayrıca `agent_runs.latency_ms` alanında durur.

## Ölçülen LLM aşaması (canlı, tek çağrı, 2 yan yana deneme)

| Düzen | Sınıflandırma | CRM | Satış | Özet | Toplam |
|---|---|---|---|---|---|
| Eski: sınıflandırma → (CRM ‖ Satış ‖ Özet) | 5,9 sn | 1,6 | 1,0 | 4,3 | **10,2 sn** |
| Yeni: dördü paralel | 3,8 sn | 2,5 | 1,9 | 4,9 | **7,5 sn** |

Sağlayıcı süresi çok oynaktur (aynı agent 1–32 sn arasında değişti; ölçümler 7–25 sn toplam verdi), bu yüzden tek tek sayılardan çok yapı önemlidir: toplam artık dört agent'ın en yavaşı kadardır, ikisinin toplamı kadar değil.

## Darboğazlar ve giderilenler

1. **Sınıflandırma sırası.** İkinci aşamadaki hiçbir agent sınıflandırma çıktısını kullanmıyor; yine de sınıflandırmayı bekliyordu (3–9 sn boşa). Dört agent artık tek aşamada paralel çalışır (`ANALYSIS_CLASSIFIER_FIRST=true` eski sırayı geri getirir).
2. **"Event loop is closed" (#160).** Sınıflandırma ve bazen diğer agent'lar ikinci görevde 10 ms'de düşüyor, çağrı "kısmi" bitiyordu; yeniden çalıştırma ve yedek model denemeleri süre ekliyordu. LLM istemcisi artık olay döngüsüne bağlı (PR #181).
3. **Hız sınırlayıcı:** `LLM_REQUESTS_PER_MINUTE=30` ve bir analizde 4 istek var; tek çağrıda bekleme çıkmadı (`agent.rate_limited` günlüğü yok). Aynı anda 7'den fazla analiz yüklenirse bekleme başlar.

## STT ve hedefler

STT süresi bu sprintte ayrıca ele alınıyor (#163; sonuçlar `docs/stt_karari.md`). Eski ölçüme göre (RTF 0,2–0,3, `small`) 1 dakikalık çağrı ≈ 12–20 sn STT eder. Bu makinede ölçüm sırasında bellek tükendiği için (sistem sanal belleği doldu) yeni STT ölçümü yapılamadı.

Hedef (1 dk'lık çağrı, yüklemeden sonuca ≤ 60 sn): ~15–20 sn STT + ~8–15 sn LLM + kuyruk ≈ 25–40 sn beklenir; canlı doğrulama için yeni günlük alanlarına bakın.
