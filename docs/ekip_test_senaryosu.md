# Test senaryosu (ekip içi prova)

Amaç: toplantıdan önce **her sayfayı üç kişi kendi bilgisayarında** gerçekten denemek. Herkes yalnızca kendi bölümlerini yapar, sonuçları [`test_sonuclari.md`](test_sonuclari.md) dosyasına yazar. Hocaya göstereceğimiz akış ayrı dosyada: [`hoca_demo_akisi.md`](hoca_demo_akisi.md).

## Kim hangi bölümü test eder?

| Bölüm | Sorumlu | Neden |
|---|---|---|
| 0 Hazırlık | **Herkes** | Herkesin kendi ortamında çalışması gerekir |
| 1 Çağrı Analitiği | **Ahmet** | Ekranı o yaptı |
| 2 Çağrılar listesi ve detay | **Ahmet** | Ekranı o yaptı |
| 3 Çağrı Yükle (canlı yapay zekâ) | **Ahmet** (ekran), **Berkay** (analiz sonucu doğru mu) | İkisi birlikte bakar |
| 4 CRM Önerisi | **Ahmet** (ekran), **Berkay** (öneri içeriği) | Onay akışı ve içerik ayrı kontrol edilir |
| 5 Servis Emirleri | **Melih** | API ve veritabanı onun |
| 6 Miço AI | **Berkay** | Asistanı o yaptı |
| 7 Hata ve sınır durumları | **Melih** (hata, yükleme), **Ahmet** (pencere, klavye) | |
| 8 Veritabanı ve kurulum | **Melih** | Docker, tablolar |

## 0. Hazırlık (herkes, kendi bilgisayarında)

1. Güncel main'i çekin:
   ```bash
   git checkout main
   git pull origin main
   ```
2. Bağımlılıkları güncelleyin (backend klasöründe `uv sync`, frontend klasöründe `npm install`).
3. `backend/.env` içinde `LLM_API_KEY` dolu olsun (Berkay'dan alın, repoya koymayın). Windows 6379 portunu ayırıyorsa `REDIS_URL=redis://localhost:6400/0` yazın (`docs/calistirma.md`).

| # | Kontrol | Beklenen |
|---|---|---|
| 1 | Docker Desktop açık | Konteynerler (postgres, redis) çalışıyor |
| 2 | `uv run python -m scripts.dev` (backend klasöründe) | Hata yok, API ayağa kalkar |
| 3 | `npm run dev` (frontend klasöründe) | http://localhost:3000 açılır |
| 4 | Ses dosyaları üretilmiş ve seed edilmiş | Çağrı detayında ses oynar |
| 5 | Tarayıcı: Chrome, tam ekran, tema açık | |

Ön kontrol: Analitik sayfası **50 çağrı** göstermeli. Göstermiyorsa veri yüklenmemiştir; devam etmeyin, Melih'e haber verin.

Sonuç dosyasına yazın: işletim sistemi, hangi komutla çalıştırdığınız, takıldığınız yer.

## 1. Çağrı Analitiği (Admin) · Ahmet

Beklenen sayılar (50 sentetik çağrı): 7 acil, 18 satışa dönüşen, 16 kaybedilen, 16 beklemede; en yaygın kategori makine (15).

- [ ] Özet kartları dolu ve sayılar yukarıdakilerle uyumlu
- [ ] Grafikler yükleniyor (günlük çağrı, kategori, aciliyet, marina, satış kaybı)
- [ ] Marina filtresi seçilince sayılar değişiyor, "temizle" ile geri dönüyor
- [ ] Tarih aralığı daraltılınca sayılar azalıyor
- [ ] Açık/koyu tema geçişinde okunabilirlik bozulmuyor

## 2. Çağrılar listesi ve detay (Admin) · Ahmet

- [ ] Liste 50 çağrı gösteriyor, sayfalama çalışıyor
- [ ] Arama kutusuna bir müşteri adı yazınca liste daralıyor
- [ ] Aciliyet = acil filtresi **7** kayıt getiriyor
- [ ] Kategori = makine filtresi **15** kayıt getiriyor
- [ ] Bir çağrıya tıkla: ses oynatıcı çalıyor, ileri sarma çalışıyor
- [ ] Konuşma metninde temsilci ve müşteri ayrı etiketli
- [ ] 7 alanlı CRM önerisi dolu (kategori, lokasyon, problem, hizmet biçimi, aciliyet, potansiyel iş, sonraki adım)
- [ ] Satış analizi ve özet görünüyor

Örnek çağrı: ilk çağrı (Tuzla Marina, motor devir sorunu).

## 3. Çağrı Yükle (Admin) · Ahmet + Berkay

Bu adım yapay zekâ servisine bağlı: **15–60 sn sürebilir, kota nedeniyle yavaşlayabilir.**

Test metni:

> Temsilci: Miço Usta, buyurun.
> Müşteri: Merhaba, motorda devir sorunu var, yarın usta gelebilir mi?
> Temsilci: Tabii, yarın sabah gönderelim.
> Müşteri: Tamam, teşekkürler.

**Ahmet (ekran):**
- [ ] Metin sekmesinden yükle: adımlar sırayla ilerliyor (Yüklendi → Analiz → Tamam)
- [ ] Bitince "Sonucu Aç" ve otomatik yönlendirme çalışıyor
- [ ] Sayfa yenilenirse izleme kaldığı yerden devam ediyor
- [ ] Aynı sesi ikinci kez yükleyince mevcut çağrıya yönlendiriyor

**Berkay (analiz sonucu):**
- [ ] Kategori makine, aciliyet yüksek/acil civarı, sonraki adım servis randevusu/usta ata
- [ ] Problem ve lokasyon konuşmayla tutarlı, kanıt cümleleri doğru yerden

## 4. CRM Önerisi (Admin) · Ahmet + Berkay

**Ahmet (akış):**
- [ ] Yeni yüklenen çağrı "Bekliyor" sekmesinde, başlıktaki sayı doğru
- [ ] **Düzenle**: bir alanı değiştir, kaydet, değişen alan görünüyor
- [ ] **Onayla ve Servis Emri Oluştur**: kart "Onaylandı"ya geçiyor
- [ ] Başka bir öneriyi **Reddet** (gerekçe yaz): "Reddedildi" sekmesine geçiyor

**Berkay (içerik):**
- [ ] Müşteri/tekne eşleşmeyen çağrıda "Eşleşmedi" uyarısı çıkıyor, onay düğmesi yerine **Müşteri ve tekne seç** var; seçip kaydedince onay açılıyor ve servis emri oluşuyor
- [ ] Önerilen alanlar çağrının içeriğiyle uyumlu

## 5. Servis Emirleri (Admin) · Melih

- [ ] Az önce onaylanan çağrının servis emri listede
- [ ] Aynı çağrıyı tekrar onaylayınca ikinci servis emri **oluşmuyor**
- [ ] Detayda kaynak çağrıya ve CRM önerisine bağlantı çalışıyor
- [ ] Durum bir sonraki adıma ilerliyor (Yeni atandı → Keşifte → Onaylandı → Devam ediyor → Tamamlandı), aşama atlanamıyor
- [ ] Durum sekmeleri ve marina filtresi sayıyı değiştiriyor

## 6. Miço AI (rol: Tekne Sahibi) · Berkay

Sağ üstten rolü **Tekne Sahibi** yapın.

| Soru | Beklenen |
|---|---|
| Kaç bakım hakkım kaldı? | Sayıyı kod hesaplar; paket kaynak kartı görünür |
| Son bakımım ne zaman yapıldı? | Tarih + kaynak kart |
| Bu ay ne kadar harcadım? | Toplam TL, kaynak kayıtlar |
| Yakında yapılması gereken bir şey var mı? | Yaklaşan bakım listesi |
| Yakıt filtresi ne zaman değişti? | Tekne notlarından, kaynaklı cevap |
| (takip) Peki ne yapılmıştı? | Önceki soruyu hatırlayıp cevaplar |
| Hava nasıl olacak? | Kibarca reddeder |
| Akü değişimine ne kadar ödedim? | **Bilinen sınır:** tutar uydurmaz, kaydı gösterir |

- [ ] Her cevapta kaynak kartı var
- [ ] Geçmiş sohbetler listesinde bu oturum görünüyor
- [ ] Rolü Admin'e çevirince asistan sayfası kullanılamıyor / yetki mantığı çalışıyor (not edin)

## 7. Hata ve sınır durumları · Melih + Ahmet

**Melih:**
- [ ] Hatalı dosya (örn. .txt'yi ses olarak) açık hata mesajı veriyor
- [ ] Çok uzun veya boş metin yüklemek
- [ ] Yapay zekâ cevap vermezse: "Yeniden Analiz Et" düğmesi

**Ahmet:**
- [ ] Pencereyi daraltmak (1024 px): yatay taşma yok
- [ ] Klavye ile gezinme (Tab, Escape ile pencere kapatma)

## 8. Veritabanı ve kurulum · Melih

- [ ] `docker compose -f infra/docker-compose.yml --profile app up -d` ile 6 parça kalkıyor
- [ ] pgAdmin'de (localhost, port 15432, `call_center`) tablolar görünüyor: `calls`, `analysis_results`, `crm_reviews`, `service_orders`, `rag_chunks`
- [ ] `calls` tablosunda 50 kayıt var
- [ ] Backend testleri geçiyor (`uv run pytest`)

## Yedek plan

- Canlı yükleme takılırsa **hazır analiz edilmiş** çağrıyı gösterin, canlı yüklemeyi bonus anlatın
- Yapay zekâ hiç çalışmazsa: önceden alınmış ekran görüntüleri ve hazır çağrı detayı
- Ses oynamazsa: konuşma metnini ve CRM önerisini gösterin

## Sonuçlar

Sonuçları [`test_sonuclari.md`](test_sonuclari.md) dosyasına yazın. Herkes yalnızca kendi bölümünün satırlarını doldursun.
