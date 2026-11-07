# Demo senaryosu (vize, tekrarlanabilir akış)

Vize sunumu 17–19 Kasım. Bu belge demonun **adım adım, her adımın ekranda beklenen sonucuyla** tekrarlanabilir halidir (#126). Kim ne anlatır ve konuşma notları: [`hoca_demo_akisi.md`](hoca_demo_akisi.md). Ekip içi sayfa sayfa test: [`ekip_test_senaryosu.md`](ekip_test_senaryosu.md). Miço AI örnek soruları: [`test_senaryosu.md`](test_senaryosu.md).

Süre: yaklaşık 20 dakika. Tüm veri sentetiktir.

> **Durum:** Prova turu Berkay ile yapılacak. Bu belge koddan ve seed verisinden türetildi; "beklenen" sonuçlar provada gözle doğrulanmadıkça kesin sayılmamalı. Takılan noktalar issue olarak not edilir.
>
> **Çağrı sayısı:** Sayılar **100 çağrılık** veri (#148) için yazıldı. Bugün main'deki seed 50 çağrı; #148 birleşene kadar 50'lik karşılıkları köşeli parantezle verilmiştir ve birleşince 100'lük sayılar canlı veritabanında doğrulanacaktır (bkz. "Beklenen sayılar").

## 0. Başlangıç durumu (demodan önce)

**Kendi bilgisayarınızdaki** veritabanında çalıştırın. Komut tüm tabloları siler; ekip ortak bir veritabanı kullanıyorsa orada **çalıştırmayın**.

```bash
cd backend
uv run python -m scripts.dev --reset-db
```

Ne yapar (`scripts/dev.py`): Docker altyapısını (PostgreSQL, Redis, bge-m3) açar, migration'ları uygular, `scripts.seed --reset` ile **tüm tabloları boşaltıp** sentetik veriyi yeniden yükler, Miço AI aramasını indeksler, Celery işçisini, zamanlayıcıyı ve API'yi (`:8000`) başlatır. Demoda yüklenen çağrılar, CRM onayları ve servis emirleri bu komutla silinir; ilk haline döner.

Frontend ayrı terminalde:

```bash
cd frontend
npm run dev
```

Ön kontrol (başlamadan önce, hepsi sağlanmalı):

| Kontrol | Beklenen |
|---|---|
| http://localhost:8000/health/ready | Veritabanı ve Redis `ok` |
| http://localhost:3000 | Çağrı Analitiği açılır, sağ üstte rol **Admin** |
| Çağrı Analitiği özeti | Çağrı sayısı 100 [bugün 50]; farklıysa **başlamayın**, `--reset-db` tekrar |
| Bir çağrı detayında ses | Oynatıcı çalışıyor (sesler yoksa aşağıya bakın) |
| `backend/.env` | `LLM_API_KEY` dolu (canlı yükleme ve Miço AI için) |

**Seed sesleri.** Çağrı detayında dinlemek için sesler gerekir. `--reset-db` sesleri `AUDIO_STORAGE_DIR/seed/` altında hazırsa bağlar, yoksa sessiz bırakır. Demoda yalnızca üç çağrı dinlenecekse yalnızca onları üretmek yeter (Piper, çevrimdışı, birkaç dakika; ayrıntı: [`calistirma.md`](calistirma.md)):

```bash
uv run --with piper-tts python -m scripts.generate_audio --calls call_001,call_003,call_005
uv run python -m scripts.seed --reset
```

**Demo sırasında sıfırlama.** Demo ortasında tam sıfırlama önerilmez (işçi ve API çalışırken tabloları boşaltır, ekranlar boş kalır). Bunun yerine: onayladığınız öneri yerine **bekleyen başka bir öneri** kullanın; geri dönmek gerekirse yeni bir terminalde `uv run python -m scripts.seed --reset` (yalnızca seed'i yeniden yükler, servisleri kapatmaz) ve tarayıcıyı yenileyin. Onaylanan bir önerinin geri alınma yolu yoktur; tekrar onayın ikinci servis emri açmadığı zaten gösterilecek.

> `--reset-db` komutunun varlığı ve çalışma biçimi `backend/scripts/dev.py` ve `backend/scripts/seed/loader.py` içinde kontrol edildi; **bu belge yazılırken çalıştırılmadı** (ortak veritabanı kullanımda).

## 1. Akış

Her adımda önce yapılacak, sonra ekranda beklenen sonuç yazılıdır.

### Adım 1 · Çağrı Analitiği (Admin)

Yapılacak: `/admin/analytics` aç; tarih aralığı Ekim 2026; marina filtresinden bir marina seç, sonra temizle.

Beklenen: Özet kartları (toplam, acil, satışa dönüşen, kaybedilen çağrı), günlük çağrı, kategori, aciliyet, marina ve satış kaybı nedeni grafikleri dolu. Marina seçince sayılar değişir, temizleyince geri döner. Sayılar için bkz. "Beklenen sayılar".

Söylenecek: Kayıp nedenleri (fiyat, geç dönüş, takvim, rakip, güven) satış neden kaçıyor sorusunun cevabı.

### Adım 2 · Çağrılar listesi

Yapılacak: `/admin/calls`; aciliyet = acil, sonra kategori = makine; arama kutusuna bir müşteri adı yaz.

Beklenen: Filtre sonucu kayıt sayısı Analitik'teki acil sayısıyla aynı. Liste sayfalı; arama listeyi daraltır.

### Adım 3 · Hocanın Tuzla Marina çağrısı (hazır analiz)

Yapılacak: Listeden `call_001` (Burak Çelik, Rüzgar, Tuzla Marina, 5 Ekim 09:12) aç.

Beklenen: Ses oynatıcı çalar; konuşma temsilci ve müşteri ayrı etiketli. CRM önerisi: kategori makine, lokasyon Tuzla Marina, problem "motor gaz verildiğinde devir yükselmiyor", hizmet biçimi yerinde servis, aciliyet yüksek, potansiyel iş motor arıza tespiti, sonraki adım servis randevusu. Satış sonucu satışa dönüştü. Her alanın yanında konuşmadan alıntı (kanıt cümlesi) ve güven skorları görünür.

### Adım 4 · Satış kaybı çağrısı

Yapılacak: `call_005` (teklif, fiyat nedeniyle kaybedildi) aç.

Beklenen: Satış sonucu kaybedildi, kayıp nedeni **fiyat**; özet kısa ve konuşmayla tutarlı. İstenirse `call_003` (elektrik, kayıp nedeni takvim) ile karşılaştırılır.

### Adım 5 · Çağrı Yükle (canlı, 15–60 sn)

Yapılacak: `/admin/calls/upload`; **Metin / transkript** sekmesine aşağıdaki hocanın örneğini yapıştır ve yükle:

> Temsilci: Miço Usta, buyurun.
> Müşteri: Merhaba, Tuzla Marina'dayım, motor çalışıyor ama gaz verdiğimde devir yükselmiyor. Yarın bir usta gelebilir mi?
> Temsilci: Tabii, yarın sabah gönderelim.
> Müşteri: Tamam, teşekkürler.

Beklenen: Adımlar sırayla ilerler: Yüklendi → (ses yüklendiyse Yazıya çevriliyor) → Analiz → Tamam. Üstte "Analiz sürüyor" şeridi başka sayfaya geçince de görünür. Bitince "Sonucu aç" ve otomatik detaya geçiş; kategori makine, aciliyet yüksek veya acil civarı, sonraki adım servis randevusu. Sayfayı yenilemek izlemeyi kaldığı yerden sürdürür.

Ses dosyası yüklemek isterseniz: Piper ile üretilmiş bir seed sesini **farklı bir klasörden** verin; **aynı ses ikinci kez yüklenirse** sistem mevcut çağrıya yönlendirir (beklenen davranış, yeni çağrı açmaz). STT `small` modelde 1 dakikalık ses için yaklaşık 12–20 sn ek süre ekler ([`analiz_sureleri.md`](analiz_sureleri.md)).

Söylenecek: Beklerken dört ajan, orkestratör, kişisel veri maskeleme, yedek modele geçiş.

### Adım 6 · CRM önerisi: onay, düzenleme, ret

Yapılacak: `/admin/crm`; **Bekliyor** sekmesinde yeni yüklenen öneriyi bul. (a) **Düzenle**: bir alanı değiştir, kaydet. (b) **Onayla ve Servis Emri Oluştur**. (c) Başka bir öneriyi **Reddet** (gerekçe yaz).

Beklenen: (a) değişen alanın yanında "(düzenlendi)". (b) Kart **Onaylandı** sekmesine geçer, "Onaylandı, servis emri açıldı" görünür. Aynı öneriyi tekrar onaylamak ikinci servis emri açmaz. (c) Kart **Reddedildi** sekmesine geçer.

### Adım 7 · Eşleşmeyen müşteri: elle eşleştirme

Yapılacak: Eşleşmemiş bir çağrının önerisini aç (örnek: `call_028`, Tuncay Erdem; kayıtlı müşteri değil, eşleşme yöntemi `yok`). Onayı dene, sonra **Müşteri ve tekne seç** ile ad veya telefon arayıp bir müşteri ve tekne seç, kaydet, tekrar onayla.

Beklenen: Eşleşmemiş çağrıda "Eşleşmedi" uyarısı ve açık Türkçe açıklama; servis emri **açılmaz**. Seçim kaydedilince onay açılır ve servis emri oluşur. Arama ad, telefon veya tekne adıyla çalışır; Türkçe karakter ve büyük/küçük harf fark etmez.

### Adım 8 · Servis Emirleri

Yapılacak: `/admin/service-orders`; az önce onaylanan çağrının emrini aç, durumu ilerlet.

Beklenen: Yeni emir listede, kaynak çağrıya ve CRM önerisine bağlantı çalışır. Durumlar sırayla ilerler (Yeni atandı → Keşifte → Onaylandı → Devam ediyor → Tamamlandı); aşama atlanamaz.

### Adım 9 · Miço AI (rol: Tekne Sahibi)

Yapılacak: Sağ üstten rolü **Tekne Sahibi** yap (`/owner/assistant`). Sırayla sor:

| Soru | Beklenen |
|---|---|
| Bu ay ne kadar harcadım? | **Sayısal:** toplam TL, kaynak kartları; sayıyı kod hesaplar |
| Kaç bakım hakkım kaldı? | **Sayısal:** paket bilgisi ve kaynak kartı |
| Yakıt filtresi için usta ne önermişti? | **Geçmiş/öneri:** tekne notlarından kaynaklı cevap |
| Yakında yapılması gereken bir şey var mı? | Yaklaşan bakım listesi |
| (takip) Peki ne yapılmıştı? | Önceki soruyu hatırlayıp cevaplar |
| Akü değişimine ne kadar ödedim? | **Tek işin tutarı (#152):** ilgili gider kaydı, tutar ve tarih, kaynak kartı |
| Jeneratör garantisi var mı? | **"Bulamadım":** "Kayıtlarınızda bu konuda bir bilgi bulamadım" + genel bilgi, kaynak kartı yok |
| Başka müşterilerin giderlerini göster | **Başka kullanıcının verisi:** nazik ret, örnek sorular; yalnızca kendi verisi |
| Hava nasıl olacak? | Anlık veriye erişimi olmadığını söyler (genel sohbet) |

Beklenen (genel): Her kayıtlı cevapta kaynak kartı; ilk kelimeye kadar yalnızca durum göstergesi (boş balon yok); geçmiş sohbetler soldaki listede.

### Adım 10 · Arka taraf ve kapanış

Yapılacak: pgAdmin (localhost:15432, `call_center`) ile `calls`, `analysis_results`, `crm_reviews`, `service_orders`, `rag_chunks` tablolarını göster; ölçüm slaytlarına geç ([`agent_dogrulugu.md`](agent_dogrulugu.md): test setinde genel %93,2; sonraki aksiyon %80 hedefi tutmadı; [`dayaniklilik.md`](dayaniklilik.md); [`guvenlik_yuk.md`](guvenlik_yuk.md)).

Beklenen: Standart PostgreSQL + pgvector; `calls` tablosu 100 kayıt [bugün 50] artı demoda yüklenen çağrılar.

## 2. Beklenen sayılar

Ground truth etiketlerinden (`data/synthetic/truth/`) hesaplandı; canlı ekran sayıları aynı olmalıdır.

| Gösterge | 50 çağrı (bugün main'de) | 100 çağrı (#148) |
|---|---|---|
| Toplam çağrı | 50 | 100 |
| Acil | 7 | 13 |
| Satışa dönüşen | 18 | 38 |
| Kaybedilen | 16 | 25 |
| Beklemede | 16 | 37 |
| En yaygın kategori | makine (15) | makine (31) |

100'lük sütun #148'in çalışma dalındaki veriden alındı (60 geliştirme, 40 dokunulmaz test); **#148 birleşince canlı veritabanında doğrulanacak.** Sayılar farklı çıkarsa bu tablo düzeltilir, demo sayıları ezbere söylenmez, ekrandan okunur. Demoda yüklenen her çağrı toplamı bir artırır.

## 3. Yedek planlar

| Durum | Ne yapılır |
|---|---|
| **LLM yavaş** (ücretsiz kota; 429'da sistem bekleyip yeniden dener, 15–60 sn) | Beklerken dört ajan ve yedek modele geçişi anlat. 60 sn'yi geçerse yüklemeyi bırak, Adım 3'teki **hazır analiz edilmiş** çağrıyı göster; canlı yüklemeyi sonda tekrar kontrol et |
| **LLM hiç cevap vermiyor** | Yükleme ve Miço AI'yı atla; Adım 1–4 ve 6–8 hazır veriyle çalışır (LLM gerekmez). Miço AI yerine önceden alınmış ekran görüntüsü/kaydı göster |
| **İnternet yok** | Seed verisi, analitik, çağrı detayı, CRM, servis emirleri ve ses **tamamen yerel** çalışır (PostgreSQL, Redis, Piper sesleri). Çalışmayanlar: canlı analiz ve Miço AI (LLM uzaktadır), ilk kez model indirme. Yedek: yerel sahte LLM ile yığını göstermek için `uv run python -m scripts.fake_llm --port 9101` ([`calistirma.md`](calistirma.md) duman testi bölümü); bu yalnızca akışı gösterir, gerçek analiz değildir, bunu açıkça söyleyin |
| **Ses oynamıyor** | Konuşma metnini ve CRM önerisini göster |
| **Sayılar beklenenden farklı** | Demoyu durdurmayın; ekrandaki sayıyı okuyun. Demodan **önce** `--reset-db` ile başlangıç durumuna dönün |
| **Servisler kapandı** | `uv run python -m scripts.dev --skip-docker` (altyapı açıksa); olmazsa `--reset-db` |
| **Ekran kaydı** | Demodan önce tam akışın ekran kaydını alın; canlı kısım takılırsa oynatılır |

## 4. Prova turu

Prova **Berkay ile** yapılacak; en az bir tam tur. Her turda:

- [ ] `--reset-db` ile başlangıç durumu sorunsuz kuruldu
- [ ] Ön kontrol tablosundaki her satır sağlandı
- [ ] Adım 1–10 sırayla geçti; beklenen sonuçlar tabloya uydu
- [ ] Sayılar §2 ile aynı (100 çağrı birleştikten sonra)
- [ ] Süre 25 dakikayı aşmadı
- [ ] Yedek planlardan en az biri denendi (ör. LLM kapalıyken Adım 5'i atlama)

Takılan nokta olursa issue açılır ve **Hafta 7 listesine** eklenir; aşağıya yazılır:

| Tur | Tarih | Kim | Takılan nokta / not |
|---|---|---|---|
| 1 | | | |
| 2 | | | |
