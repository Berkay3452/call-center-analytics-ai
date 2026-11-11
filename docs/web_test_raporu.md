# Web uygulaması test raporu (Playwright MCP + canlı e2e)

**Tarih:** 2026-11-11 · **Ortam:** gerçek backend + mock'suz frontend, seed'li veritabanı (102 çağrı: 100 sentetik + 2 elle yüklenmiş) · **Araçlar:** Playwright MCP (`@playwright/mcp`, keşif), `frontend/e2e/live/` (kalıcı canlı testler, 17 test), SQL ile çapraz doğrulama

## Yöntem

- **Keşif (MCP):** Sayfalar gerçek tarayıcıda gezildi; arayüzdeki sayılar API ve veritabanıyla karşılaştırıldı; Miço AI'ye sınır ve güvenlik soruları soruldu; küçük ekran ve dosya yükleme doğrulaması denendi.
- **Kalıcı testler:** Bulgulardan tekrarlanabilir olanlar `e2e/live/*.live.spec.ts` içine yazıldı (`LIVE=1`; CI'da atlanır).
- **Veri değiştirilmedi:** Onay, red, yükleme gönderimi ve yeniden analiz gibi veriyi değiştiren işlemler denenmedi.

## Özet

| Alan | Sonuç |
|---|---|
| Analitik sayıları (arayüz = API = SQL) | ✅ Tutarlı |
| Çağrı listesi ve sayfalama | ✅ 102 kayıt, 11 sayfa |
| Çağrı detayı, transkript, konuşmacılar | ✅ 102 çağrının hepsinde segment ve analiz var |
| CRM ve servis emirleri | ✅ Sayılar tutarlı, konsol hatası yok |
| Dosya yükleme doğrulaması | ✅ Yanlış format reddedilir, 25 MB sınırı çalışır |
| Miço AI güvenlik | ✅ Başka müşteri adı ve kimliği sızdırılmıyor |
| Miço AI doğruluk | ❌ Tekne adı yok sayılıyor (aşağıda) |
| Küçük ekran | ⚠️ `/admin/calls` yatay kayıyor |

## Bulgular

| # | Önem | Bulgu | Nasıl yeniden üretilir |
|---|---|---|---|
| 1 | ✅ Düzeltildi | **Miço AI sorulan teknenin adını yok sayıyor.** "Yelkovan teknesinin son bakımı?" sorusuna Poyraz'ın kaydı cevap olarak geliyor; cevap hangi tekneden bahsettiğini söylemiyor veya yanlış söylüyor. | Miço AI'ye "Yelkovan teknesinin son bakımı ne zaman yapıldı?" yaz. `e2e/live/assistant.live.spec.ts` içinde `test.fixme` |
| 2 | ✅ Düzeltildi | **Tekne bazlı sorularda filtre yok:** "Yelkovan teknesinin giderleri" tüm teknelerin toplamını (164.900 TL, 8 kalem) "toplam giderleriniz" diye veriyor. | Miço AI'ye "Yelkovan teknesinin giderleri" yaz |
| 3 | ✅ Düzeltildi | **Başka müşterinin tekne adı yanlış eşleniyor:** "Zıpkın teknesinin bakım geçmişi" (Zıpkın başka müşterinin teknesi) sorusuna kullanıcının kendi teknesinin notu veriliyor. Veri sızmıyor ama cevap yanıltıcı; "bu tekne sizin değil" denmeli. | Miço AI'ye "Zıpkın teknesinin bakım geçmişi nedir?" yaz |
| 4 | Orta | **Anlamsız ya da saldırı benzeri girdide önceki cevap tekrarlanıyor:** `DROP TABLE customers; --` yazınca bir önceki sorunun (motor yağı) cevabı geliyor. Sorgu çalıştırılmıyor (parametreli), ama cevap alakasız. Takip sorusu yeniden yazımı geçmişi yanlış bağlıyor olabilir. | Önce "Motor yağı kaç saatte bir değişir?", sonra `DROP TABLE customers; --` yaz |
| 5 | Orta | **`/admin/calls` 390 px genişlikte yatay kaydırma** (sayfa düzeyinde). Asistan ve analitik sayfalarında yok. | Pencereyi 390 px yap, Çağrılar sayfasını aç |
| 6 | Düşük | **Varsayılan "Son 30 gün" analitikte 102 çağrının 75'ini gösterir.** Sentetik veri Ekim başında; seçici "Ekim 2026 (demo verisi)" ile 100'e çıkıyor. Demoda varsayılan dönemi bilinçli seçmek gerekir. | Analitik sayfasını aç |
| 7 | Düşük | "Bu ay" cevabının sonuna gereksiz "Servis kayıtlarında eşleşen belge bulunamadı." cümlesi ekleniyor. | Miço AI'ye "Bu ay ne kadar harcadım?" yaz (kayıt yokken) |
| 8 | Düşük | Çağrı detayında teklif çağrısı için "Sorun tanımı çıkarılamadı" ve "Aksiyon gerekmiyor" yazıyor; teklif talebi için beklenebilir ama kullanıcıya kusur gibi görünür. | `Deniz Saygın — Zıpkın` çağrısını aç |
| 9 | Bilgi | Servis emirleri 63, CRM'de onaylanan öneri 2. Seed servis emirleri CRM onayından bağımsız; bilinen durum. | `/admin/service-orders` ve `/admin/crm` |
| 10 | Bilgi | Yerel ortam: `backend/.env`'de `REDIS_URL` şemasızdı (`127.0.0.1`), veritabanı adresi `localhost` idi; düzeltildi. Yeni kurulumlarda `.env.example` kullanılmalı. | Backend'i eski `.env` ile başlat |

## Doğrulanan davranışlar

- Analitik: varsayılan 75, "Ekim 2026" 100, "Son 7 gün" 2, "Son 3 ay" ve "Son 1 yıl" 102; Kalamış Marina 14. SQL ile aynı.
- Çağrı listesi: "Toplam 102 kayıttan 1-10 arası", 11 sayfa.
- API taraması: 102 çağrının tamamı `tamam`, tümünde transkript segmenti ve analiz var; 18'i müşteriyle eşleşmemiş (yeni müşteri), 1'i sesiz (metin yüklemesi).
- Miço AI: başka müşteri adı ("Burak Çelik", "Deniz Saygın") ve kimlik ("owner-002") reddediliyor; anlamsız metin, kural aşma ve hava soruları beklenen cevabı alıyor; "geçen ay" ile toplam farklı sonuç veriyor.
- Çağrı yükleme: `.exe` "Desteklenmeyen format", 26 MB dosya boyut hatası veriyor.

## Önerilen sıra

1. ~~#1, #2, #3~~ (yapıldı, feat/asistan-tekne-cozumleme): Miço AI'de soruda geçen tekne adını çözümle; kullanıcının teknesi değilse söyle; giderleri tekne bazında filtrele.
2. #4: Takip sorusu yeniden yazımını sınırla; anlamsız girdide geçmişi bağlama.
3. #5: `/admin/calls` için küçük ekran düzeni.
4. #6: Demo için varsayılan dönemi sentetik veri dönemine ayarla.

## Yeniden çalıştırma

```bash
# Backend ve frontend (NEXT_PUBLIC_USE_MOCKS=false) açıkken
cd frontend
LIVE=1 npx playwright test e2e/live --project=chromium
```
