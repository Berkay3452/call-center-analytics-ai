# Miço AI asistan test senaryosu

Elle deneme için örnek sorular ve beklenen davranış. Otomatik karşılıkları `backend/tests/test_assistant*.py` dosyalarındadır.

## Selam / teşekkür / "sen kimsin" (#161)

LLM ve arama **çağrılmaz**; cevap anında gelir (`app/assistant/planner.py` → `smalltalk_reply`).

| Soru | Beklenen cevap |
|---|---|
| `Selam`, `Merhaba`, `Günaydın`, `Selam, nasılsın?` | "Merhaba! Tekneniz, bakım kayıtlarınız, giderleriniz veya aboneliğiniz hakkında soru sorabilirsiniz." + örnek sorular |
| `Teşekkürler`, `Sağ ol` | "Rica ederim! ..." |
| `Sen kimsin?`, `Ne yapabilirsin?` | Miço AI'nın ne yaptığı + örnek sorular |
| `Görüşürüz` | Kısa veda |
| `Selam, bu ay ne kadar harcadım?` | Sohbet **değil**: gerçek soru olarak planlayıcıya gider (sayısal cevap) |
| Konu dışı (ör. `Hava nasıl olacak?`) | Nazik ret + örnek sorular |

### Süre ölçümü

- Selam / teşekkür / "sen kimsin": hazır cevap kodla seçilir, ağ çağrısı yoktur. 1000 çağrı 0,03 sn sürdü (çağrı başına ~0,03 ms); testte üst sınır 1 sn olarak denetlenir (`test_smalltalk_is_answered_without_llm_or_search`). Hedef: **< 1 sn**.
- Normal sorular (planlayıcı + arama + cevap): hedef **< 10 sn**; sayısal sorular LLM'siz kuralla, tarih/gider sorgusuyla birkaç yüz ms'de döner. Canlı LLM süresi sağlayıcıya bağlıdır; elle ölçmek için arayüzde soruyu gönderip ilk kelimenin geldiği süreye bakın.
