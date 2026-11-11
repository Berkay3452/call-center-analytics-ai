# Canlı test planı (gerçek backend, seed'li veri)

Çalıştırma: backend ve frontend (`NEXT_PUBLIC_USE_MOCKS=false`) açıkken
`LIVE=1 npx playwright test e2e/live --project=chromium`. CI'da atlanır.

## Admin paneli (`e2e/live/admin.live.spec.ts`)
1. Analitik sayfası açılır, sayı içerir, hata uyarısı yok.
2. Çağrılar listesi satır gösterir; olmayan arama listeyi boşaltır.
3. Çağrı detayı: transkript balonları ve yeniden analiz düğmesi.
4. CRM durum sekmelerinde kayıt sayıları var.
5. Servis emirleri durum sekmesi değişir.
6. Çağrı yükle sayfası açılır, takılı "Analiz sürüyor" ekranı yok.
7. Tüm panel sayfaları konsol hatası vermeden açılır.

## Miço AI (`e2e/live/assistant.live.spec.ts`)
1. Başlıkta sabit tekne adı yok; "Yeni sohbet" sağda.
2. Selam hızlı (LLM'siz) cevaplanır.
3. Klavye karalaması "anlayamadım" cevabı alır.
4. Kural aşma girişimi ve başkasının verisi reddedilir.
5. Hava sorusu saat/tarih söylemez.
6. Çok uzun soru doğrulama hatası vermez.
7. Cevap beklenirken kutu yazılabilir; 4000+ karakterde sayaç görünür.
8. "Geçen ay" sorusu toplamdan farklı cevap verir.
9. (fixme) Sorulan teknenin adı cevapta korunur: "Yelkovan" sorusuna Poyraz kaydı veriliyor.

## Sonraki adım
Playwright Test Agents (`.mcp.json`, planner/generator/healer) ile bu plan genişletilebilir; yeni oturumda `frontend/` klasöründe başlatın.
