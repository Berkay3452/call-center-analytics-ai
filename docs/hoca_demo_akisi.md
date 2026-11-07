# Hoca toplantısı: canlı demo akışı

Ekran paylaşımıyla, sırayla **tüm sayfaları** gösteriyoruz. Her adımda ne gösterildiği, ne söylendiği ve kimin anlattığı yazılı. Ekip içi hazırlık için: [`ekip_test_senaryosu.md`](ekip_test_senaryosu.md).

Toplam süre: yaklaşık 20–25 dakika.

## Başlamadan önce

- Docker Desktop açık, `uv run python -m scripts.dev` ve `npm run dev` çalışıyor
- Tarayıcı Chrome, tam ekran, http://localhost:3000
- Sağ üstte rol: **Admin**
- Analitik sayfasında 50 çağrı görünüyor (görünmüyorsa başlamayın)
- Yedek: hazır analiz edilmiş bir çağrı, pgAdmin açık (localhost:15432, `call_center`)

## Akış

| # | Sayfa | Ne gösterilir | Ne söylenir | Kim |
|---|---|---|---|---|
| 1 | PDF, mimari şema | Çağrı hattı: yükle → yazıya çevir → analiz → CRM → servis emri | Problem ve üç parça; Miço Usta sitesine eklenecek şekilde tasarlandı | Berkay |
| 2 | **Çağrı Analitiği** | Özet kartları, grafikler, marina filtresi, tarih aralığı | 50 sentetik çağrı: 7 acil, 18 satışa dönüşen, 16 kaybedilen. Satış neden kaçıyor, hangi marina yoğun | Ahmet |
| 3 | **Çağrılar** listesi | Arama, aciliyet = acil (7), kategori = makine (15) | Liste filtreleri doğrudan veritabanından | Ahmet |
| 4 | **Çağrı Detayı** | İlk çağrı (Tuzla Marina, motor devir sorunu): ses oynat, konuşmacı etiketli metin, 7 alanlı CRM önerisi, özet | Sol kanal temsilci, sağ kanal müşteri; yapay zekâ 7 alanı konuşmadan kanıt cümlesiyle çıkarıyor | Ahmet + Berkay |
| 5 | **Çağrı Yükle** (canlı) | Test metnini yapıştır, ilerlemeyi göster (Yüklendi → Yazıya çevriliyor → Analiz → Tamam; üstte "Analiz sürüyor" şeridi başka sayfalarda da görünür) | Beklerken: 4 ajan, orkestratör, kişisel veri maskeleme, yedek modele geçiş. **15–60 sn sürebilir** | Ahmet anlatır, Berkay açıklar |
| 6 | Yüklenen çağrının sonucu | Kategori makine, aciliyet, sonraki adım | Canlı çıkan sonuç ile hazır çağrıyı karşılaştırır | Berkay |
| 7 | **CRM Önerisi** | Bekleyen öneri → Düzenle → **Onayla ve Servis Emri Oluştur**; bir diğerini Reddet. Müşterisi eşleşmeyen çağrıda **Müşteri ve tekne seç** ile eşleştirip onayla | İnsan onayı mantığı; onayda servis emri açılır, tekrar onayda ikinci emir açılmaz; eşleşmeyen çağrıya servis emri açılmaz | Ahmet |
| 8 | **Servis Emirleri** | Yeni emir listede, kaynak çağrıya bağlantı, durumu ilerlet | Durumlar sırayla ilerler, aşama atlanamaz | Melih |
| 9 | **Miço AI** (rol: Tekne Sahibi) | "Kaç bakım hakkım kaldı?", "Bu ay ne kadar harcadım?", "Yakında yapılması gereken bir şey var mı?", takip sorusu, "Hava nasıl olacak?" | Sayıları model değil kod hesaplar; her cevapta kaynak kartı; sadece kendi verisi; kapsam dışı reddedilir | Berkay |
| 10 | Sistemin arkası | pgAdmin: `calls`, `analysis_results`, `service_orders`, `rag_chunks` | Standart PostgreSQL + pgvector, Docker ile tek komutta kurulum, testler | Melih |
| 11 | PDF: ölçümler ve eksikler | Başarı kriterleri, doğruluk tablosu, tamamlanma yüzdesi | Dürüstçe: veri sentetik, gerçek veriyle doğruluk düşebilir | Berkay |
| 12 | PDF: sorular | Entegrasyon zamanı ve veritabanı | Entegrasyonu vizeye almak istiyoruz | Berkay |

## Yedek planlar

- Canlı yükleme takılırsa: hazır analiz edilmiş çağrıyı göster, canlı yüklemeyi anlat
- Yapay zekâ hiç cevap vermezse: Miço AI yerine ekran görüntüleri ve çağrı detayı
- Ses oynamazsa: konuşma metni ve CRM önerisini göster
- Yavaşlık sorulursa: ücretsiz yapay zekâ kotası kullanıyoruz, bu yüzden bazen 15–60 sn sürüyor

## Konuşmada dikkat

- "Gerçek veri yok, her şey sentetik" diye başta açıkça söyleyin
- Bilinen sınır: tek işin ücreti gibi sorularda tutar uydurmaz, kaydı gösterir
- Rol seçici gerçek giriş değil, simülasyon

## Toplantı sonrası

Hocanın istediği değişiklikleri buraya yazın:

-
