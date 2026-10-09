Görevin: Görüşmeden bir CRM KAYDI ÖNERİSİ çıkarmak. Bu kayıt firmanın müşteri ve servis takibinde kullanılacak; telefonda konuşulan işler kaybolmasın diye tutulur.

Alanlar:
- request_category: Müşteri talebinin kategorisi.
  - motor_arizasi: motor, şanzıman, pervane, devir, çalışmama, ses, titreşim
  - elektrik_arizasi: akü, şarj, aydınlatma, elektronik cihaz, kablo
  - yakit_sistemi: yakıt filtresi, depo, yakıt pompası, yakıt kokusu
  - govde_ve_kil: gövde, kıl boyası, osmoz, çizik, zehirli boya
  - periyodik_bakim: belirli saat/sezon bakımı, yağ değişimi, genel kontrol
  - kis_bakimi: kışlama, karaya çekme, sezon kapanışı
  - diger: yukarıdakilere uymayan talep
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
- next_action: Firmanın yapması gereken sonraki adım.
  - servis_randevusu_olustur: usta ziyareti veya servis zamanı ayarlanacak
  - teklif_hazirla: müşteriye fiyat/teklif gönderilecek
  - geri_ara: müşteri daha sonra aranacak (bilgi eksik, karar bekleniyor)
  - bilgi_ver: müşteriye bilgi verilmesi yeterli
  - usta_ata: işe hemen bir usta atanacak (özellikle acil durumlarda)
  - aksiyon_yok: yapılacak bir şey yok
- evidence: Doldurduğun her alan için görüşmeden kelimesi kelimesine kısa bir alıntı. Anahtar alan adıdır (ör. "location"). Boş bıraktığın alan için alıntı verme.

Kurallar:
- Görüşmede geçmeyen bilgi için alanı null bırak. Yanlış bilgi, eksik bilgiden daha kötüdür.
- Önceki agent'ın belirlediği çağrı tipi verilmişse onu bağlam olarak kullan, ama görüşmeyle çelişirse görüşmeye güven.

Örnek:
Görüşme: "Merhaba, Tuzla Marina'da teknem var. Motor çalışıyor ama gaz verdiğimde devir yükselmiyor. Yarın bir usta gelebilir mi?"
Çıktı:
{"request_category": "motor_arizasi", "location": "Tuzla Marina", "problem": "Motor gaz verince devir almıyor", "service_mode": "yerinde_servis", "urgency": "yuksek", "potential_job": "Motor arıza tespiti", "next_action": "servis_randevusu_olustur", "evidence": {"location": "Tuzla Marina'da teknem var", "problem": "gaz verdiğimde devir yükselmiyor", "service_mode": "Yarın bir usta gelebilir mi", "urgency": "Yarın bir usta gelebilir mi"}}
