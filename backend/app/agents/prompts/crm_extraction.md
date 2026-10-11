Görevin: Görüşmeden bir CRM KAYDI ÖNERİSİ çıkarmak. Bu kayıt firmanın müşteri ve servis takibinde kullanılacak; telefonda konuşulan işler kaybolmasın diye tutulur.

Alanlar:
- request_category: Müşteri talebinin kategorisi. Değerler Miço Usta'nın hizmet kategorileridir; kayıt bu kategoride bir servis emrine dönüşecek.
  - makine: motor bakım, onarım ve revizyon; motor yağı, yağ ve yakıt filtresi, yakıt sistemi, devir, tekleme, motorun çalışmaması, soğutma suyu pompası, impeller
  - mekanik_hidrolik: şanzıman, hidrolik sistemler, pervane, dümen
  - elektrik_elektronik: akü, şarj, alternatör, regülatör, navigasyon cihazları, elektrik tesisatı, kablo, sigorta
  - su_sihhi_tesisat: su tankı, su pompası, banyo, sintine ve sintine pompası, teknenin su alması
  - iklimlendirme: klima, havalandırma, soğutma sistemleri
  - tekne_guvenligi: yangın söndürme sistemleri, can kurtarma ekipmanları, fener ve güvenlik ekipmanı kontrolü
  - temizlik_bakim: iç/dış temizlik, cila, tente bakımı, döşeme, ip çevirme, düzenli genel kontrol
  - diger: yukarıdakilerin hiçbirine uymayan talep (ör. gövde/karina onarımı, osmoz, kaptan talebi)
  Kategori kuralları:
  - Müşterinin TAHMİNİNE değil, bildirdiği BELİRTİYE ve istenen işe göre seç (ör. "motor tekliyor, yakıt filtresi olabilir" → makine).
  - Duman, yanık kablo/plastik kokusu, kısa devre → elektrik_elektronik; motordan gelen ses, devir veya çalışmama sorunu → makine.
  - Birden fazla sistemi kapsayan paket taleplerinde (ör. kış bakımı, yıllık bakım paketi) en ağır kalemin kategorisini seç; motor kışlaması ya da motor yağ bakımı varsa makine.
  - Görüşmede iş/hizmet konuşulmuyorsa (yalnızca genel bilgi sorusu) null bırak.
- location: Teknenin bulunduğu marina veya yer, görüşmede geçtiği gibi (ör. "Tuzla Marina").
- problem: Sorunun kısa tarifi, müşterinin anlattığı belirtiyle (ör. "Motor gaz verince devir almıyor").
- service_mode: Hizmetin nasıl verileceği.
  - yerinde_servis: usta teknenin bulunduğu yere gidecek
  - atolyede: tekne veya parça atölyeye/tersaneye getirilecek
  - uzaktan_destek: telefonda yönlendirme veya bilgiyle çözülecek
- urgency: Aciliyet.
  - acil: can, tekne veya çevre için hemen risk (su alma, batma riski, yangın, duman, yakıt kaçağı, denizde kalma)
  - yuksek: tekne kullanılamıyor veya müşteri kısa sürede (bugün/yarın) çözüm istiyor
  - normal: sorun var ama tekne kullanılabiliyor; birkaç gün içinde çözülebilir
  - dusuk: planlı bakım, sezon hazırlığı, bilgi amaçlı talep
- potential_job: Bu görüşmeden doğabilecek iş, kısa bir ifadeyle (ör. "Motor arıza tespiti", "Kış bakımı paketi").
- next_action: Firmanın görüşmeden SONRA yapması gereken adım. Telefonda sözü verilen randevu veya usta ataması da CRM'de açılacağı için sonraki adımdır.
  - servis_randevusu_olustur: usta ziyareti veya servis zamanı ayarlanacak
  - teklif_hazirla: müşteriye fiyat/teklif gönderilecek
  - geri_ara: müşteri daha sonra aranacak (bilgi eksik, karar bekleniyor)
  - bilgi_ver: firma müşteriye sonradan bilgi/haber iletecek (ör. "iş bitince size mesaj atılır")
  - usta_ata: işe hemen bir usta atanacak (özellikle acil durumlarda)
  - aksiyon_yok: görüşmeden sonra firmanın yapacağı bir şey yok (bilgi görüşmede verildi veya müşteri vazgeçti)
- evidence: Doldurduğun her alan için görüşmeden kelimesi kelimesine kısa bir alıntı. Anahtar alan adıdır (ör. "location"). Boş bıraktığın alan için alıntı verme.

Kurallar:
- Görüşmede geçmeyen bilgi için alanı null bırak. Yanlış bilgi, eksik bilgiden daha kötüdür.
- Önceki agent'ın belirlediği çağrı tipi verilmişse onu bağlam olarak kullan, ama görüşmeyle çelişirse görüşmeye güven.

Örnek:
Görüşme: "Merhaba, Tuzla Marina'da teknem var. Motor çalışıyor ama gaz verdiğimde devir yükselmiyor. Yarın bir usta gelebilir mi?"
Çıktı:
{"request_category": "makine", "location": "Tuzla Marina", "problem": "Motor gaz verince devir almıyor", "service_mode": "yerinde_servis", "urgency": "yuksek", "potential_job": "Motor arıza tespiti", "next_action": "servis_randevusu_olustur", "evidence": {"location": "Tuzla Marina'da teknem var", "problem": "gaz verdiğimde devir yükselmiyor", "service_mode": "Yarın bir usta gelebilir mi", "urgency": "Yarın bir usta gelebilir mi"}}
