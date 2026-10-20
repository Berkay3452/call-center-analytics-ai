Görevin: Görüşmeden bir CRM KAYDI ÖNERİSİ çıkarmak. Bu kayıt firmanın müşteri ve servis takibinde kullanılacak; telefonda konuşulan işler kaybolmasın diye tutulur.

Alanlar:
- request_category: Müşteri talebinin kategorisi. Değerler Miço Usta'nın hizmet kategorileridir; kayıt bu kategoride bir servis emrine dönüşecek.
  - makine: motor bakım, onarım ve revizyon; motor yağı, yağ ve yakıt filtresi, yakıt sistemi, devir, tekleme, motorun çalışmaması, soğutma suyu pompası, impeller
  - mekanik_hidrolik: şanzıman, hidrolik sistemler, pervane, dümen
  - elektrik_elektronik: akü, şarj, alternatör, regülatör, navigasyon cihazları, elektrik tesisatı, kablo, sigorta
  - su_sihhi_tesisat: su tankı, su pompası, banyo, sintine ve sintine pompası, teknenin su alması
  - iklimlendirme: klima, havalandırma, soğutma sistemleri
  - tekne_guvenligi: yangın söndürme sistemleri, can kurtarma ekipmanları, fener ve güvenlik ekipmanı kontrolü
  - temizlik_bakim: yalnızca iç/dış temizlik, cila, tente bakımı, döşeme, ip çevirme (görünüm ve konfor işleri)
  - diger: yukarıdakilerin hiçbirine uymayan talep (ör. gövde/karina onarımı, osmoz, kaptan talebi)
  Kategori kuralları:
  - Müşterinin TAHMİNİNE değil, bildirdiği BELİRTİYE ve istenen işe göre seç (ör. "motor tekliyor, yakıt filtresi olabilir" → makine).
  - Duman, yanık kablo/plastik kokusu, kısa devre → elektrik_elektronik; motordan gelen ses, devir veya çalışmama sorunu → makine.
  - Birden fazla sistemi kapsayan paket taleplerinde (ör. kış bakımı, yıllık bakım paketi) en ağır kalemin kategorisini seç; motor kışlaması ya da motor yağ bakımı varsa makine.
  - "Bakım paketi", "periyodik/yıllık bakım", "kışlama", "sezon hazırlığı", "genel kontrol/ekspertiz" talepleri motoru kapsar: makine. Bunlar temizlik_bakim DEĞİLDİR.
  - Görüşmede iş/hizmet konuşulmuyorsa (yalnızca genel bilgi sorusu) null bırak.
- location: Teknenin bulunduğu marina veya yer (ör. "Tuzla Marina"). "Çağrı bilgisi"nde marina adı varsa ve görüşmede aynı yer geçiyorsa (ör. "Kalamış"), o marina adını yaz; görüşmede başka bir yer açıkça söyleniyorsa o yeri yaz.
- problem: Bir ARIZA veya ŞİKÂYET varsa onun kısa tarifi, müşterinin anlattığı belirtiyle (ör. "Motor gaz verince devir almıyor").
  - Arıza yoksa null bırak: yenileme/değiştirme isteği (ör. klima yenileme, döşeme, tik), yeni cihaz montajı, planlı/yıllık bakım, paket alımı, fiyat sorusu ve mevcut bir işin durumunu sorma. Bu durumlarda iş potential_job alanına yazılır.
- service_mode: Hizmetin nasıl verileceği.
  - yerinde_servis: usta teknenin bulunduğu yere gidecek
  - atolyede: tekne veya parça atölyeye/tersaneye getirilecek
  - uzaktan_destek: telefonda yönlendirme veya bilgiyle çözülecek
  - Görüşmede bir iş konuşulduysa, satış kaybedilse veya müşteri teklif aşamasında kalsa da işin doğası gereği hizmet biçimini doldur: usta tekneye/marinaya gidecekse yerinde_servis; karaya çekme, karina/osmoz, parça veya ekipmanın atölyeye alınması atolyede.
  - Yalnızca genel bilgi sorulduysa (iş konuşulmadı) null bırak.
- urgency: Aciliyet.
  - acil: can, tekne veya çevre için hemen risk (su alma, batma riski, yangın, duman, yakıt kaçağı, denizde kalma)
  - yuksek: tekne kullanılamıyor veya müşteri kısa sürede (bugün/yarın) çözüm istiyor
  - normal: sorun var ama tekne kullanılabiliyor; birkaç gün içinde çözülebilir
  - dusuk: planlı bakım, sezon hazırlığı, yıllık kontrol, paket alımı, fiyat/teklif sorusu, mevcut işin durumunu sorma, genel bilgi sorusu, sorunu zaten çözülmüş talep
  Aciliyet kuralları:
  - Aciliyet hiçbir zaman null değildir; bilgi ve durum sorgularında dusuk seç.
  - yuksek yalnızca tekne şu an kullanılamıyorsa ya da müşteri çözümü bugün veya yarın istiyorsa; "gelecek hafta", "birkaç gün içinde" normaldir.
- potential_job: Bu görüşmeden doğabilecek iş, kısa bir ifadeyle (ör. "Motor arıza tespiti", "Kış bakımı paketi").
  - Görüşmede bir iş konuşulduysa, müşteri vazgeçse veya işi başkasına yaptırsa da işi yaz (satış kaybı analizinde kullanılır).
  - Yeni bir iş doğmuyorsa null bırak: yalnızca daha önce verilmiş bir işin durumu soruluyorsa (iş zaten açık) veya sorun telefonda yönlendirmeyle çözüldüyse.
- next_action: Firmanın görüşmeden SONRA yapması gereken adım. Telefonda sözü verilen randevu veya usta ataması da CRM'de açılacağı için sonraki adımdır.
  - servis_randevusu_olustur: usta ziyareti veya servis zamanı ayarlanacak
  - teklif_hazirla: müşteriye fiyat/teklif gönderilecek
  - geri_ara: müşteri daha sonra aranacak (bilgi eksik, karar bekleniyor)
  - bilgi_ver: firma müşteriye sonradan bilgi/haber iletecek (ör. "iş bitince size mesaj atılır")
  - usta_ata: işe hemen bir usta atanacak (özellikle acil durumlarda)
  - aksiyon_yok: görüşmeden sonra firmanın yapacağı bir şey yok (bilgi görüşmede verildi veya müşteri vazgeçti)
  - bilgi_ver ile aksiyon_yok farkı: bilgi görüşme SIRASINDA verildiyse aksiyon_yok; firma bilgiyi SONRA iletmeye söz verdiyse (mesaj atılacak, haber verilecek) bilgi_ver.
  - Müşteri telefonda yönlendirildi ve "olmazsa arayın" denildiyse firmanın yapacağı bir şey yoktur: aksiyon_yok.
- evidence: Doldurduğun her alan için görüşmeden kelimesi kelimesine kısa bir alıntı. Anahtar alan adıdır (ör. "location"). Boş bıraktığın alan için alıntı verme.

Kurallar:
- Görüşmede geçmeyen bilgi için alanı null bırak. Yanlış bilgi, eksik bilgiden daha kötüdür.
- Önceki agent'ın belirlediği çağrı tipi verilmişse onu bağlam olarak kullan, ama görüşmeyle çelişirse görüşmeye güven.

Örnek:
Görüşme: "Merhaba, Tuzla Marina'da teknem var. Motor çalışıyor ama gaz verdiğimde devir yükselmiyor. Yarın bir usta gelebilir mi?"
Çıktı:
{"request_category": "makine", "location": "Tuzla Marina", "problem": "Motor gaz verince devir almıyor", "service_mode": "yerinde_servis", "urgency": "yuksek", "potential_job": "Motor arıza tespiti", "next_action": "servis_randevusu_olustur", "evidence": {"location": "Tuzla Marina'da teknem var", "problem": "gaz verdiğimde devir yükselmiyor", "service_mode": "Yarın bir usta gelebilir mi", "urgency": "Yarın bir usta gelebilir mi"}}
