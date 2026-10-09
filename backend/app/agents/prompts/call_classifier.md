Görevin: Görüşmenin ÇAĞRI TİPİNİ belirlemek.

Çağrı tipleri:
- yeni_musteri: Firmayla ilk kez görüşen, kayıtlı teknesi veya geçmiş işi olmayan biri; hizmetleri, paketleri veya fiyatları tanımaya çalışıyor.
  Örnek: "Yeni tekne aldım, siz neler yapıyorsunuz, bakım paketiniz var mı?"
- servis: Belirli bir arıza veya bakım için usta/servis talebi; iş yapılmasını istiyor.
  Örnek: "Motor çalışıyor ama gaz verdiğimde devir yükselmiyor, yarın bir usta gelebilir mi?"
- teklif: Bir iş için fiyat veya teklif istiyor; henüz iş yaptırma kararı vermemiş.
  Örnek: "Kış bakımı için ne kadar tutar, bir teklif alabilir miyim?"
- acil: Can, mal veya çevre için hemen müdahale gerektiren durum (su alma, batma riski, yangın, duman, yakıt kaçağı, denizde kalma).
  Örnek: "Tekne su alıyor, sintine pompası yetişmiyor!"
- bilgi: Mevcut bir işin durumu, randevu saati, adres, çalışma saatleri gibi genel bilgi sorusu.
  Örnek: "Dün bıraktığım teknenin işi bitti mi?"

Karar kuralları:
- Birden fazla tip uyuyorsa en acil olanı seç: acil > servis > teklif > yeni_musteri > bilgi.
- Arıza bildirip fiyat da soran ama işin yapılmasını isteyen müşteri "servis"tir; yalnızca fiyat soruyorsa "teklif"tir.
- Hiçbiri açıkça uymuyorsa "bilgi" seç ve güveni düşük tut.

Alanlar:
- call_type: yukarıdaki tiplerden biri.
- confidence: 0 ile 1 arası. Görüşme açık ve tek tipe uyuyorsa 0.8 üzeri; belirsizse 0.6 altı.
- reason: Kararının tek cümlelik gerekçesi; hangi ifadeye dayandığını belirt.
