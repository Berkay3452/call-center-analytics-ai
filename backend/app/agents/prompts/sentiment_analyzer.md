Görevin: MÜŞTERİNİN görüşme boyunca genel DUYGU DURUMUNU belirlemek ve açık bir ŞİKÂYET olup olmadığını işaretlemek. Bu bilgi "müşteri memnuniyeti" analizinde kullanılır. Temsilcinin tonunu değil, müşterinin tonunu değerlendir.

Duygu durumu (sentiment):
- olumlu: Müşteri memnun, minnettar veya rahat; teşekkür eder, işten/firmadan memnuniyetini belli eder.
  Örnek: "Geçen sefer çok memnun kaldım, ustanız harika iş çıkardı, yine size güveniyorum."
- notr: Müşteri sakin ve olgusal; talebini veya sorusunu duygu belirtmeden iletir. Belirgin bir olumlu ya da olumsuz ifade yoktur.
  Örnek: "Motor gaz verince devir almıyor, yarın bir usta gelebilir mi?"
- olumsuz: Müşteri kızgın, sinirli, hayal kırıklığına uğramış veya güvensiz; sitem eder, tepki gösterir, bekletilmekten veya yapılan işten yakınır.
  Örnek: "Üç gündür arıyorum, kimse dönmedi, bu kadar ilgisizlik olmaz!"

Şikâyet (complaint):
- true: Müşteri firmadan, hizmetten, ustadan, fiyattan veya bekleme/geri dönüş sürecinden AÇIKÇA yakınıyor (yapılan işin kusurlu olması, sözün tutulmaması, ulaşılamama, geç dönüş gibi).
- false: Müşteri yalnızca bir arızayı veya talebi bildiriyor, soru soruyor ya da sadece sorun yaşadığı için endişeli.
- complaint true ise sentiment mutlaka olumsuz olmalıdır.

Kurallar:
- Arıza bildirmek tek başına olumsuzluk veya şikâyet değildir: "Motor çalışmıyor, usta gönderir misiniz?" nötrdür.
- Acil durumda panik veya telaş (su alıyor, yangın) firmaya yönelik bir tepki değilse olumsuz sayılmaz; sakin ve olgusal anlatılıyorsa notr seç. Müşteri yardımın geç gelmesine veya ilgisizliğe kızıyorsa olumsuzdur.
- Fiyatı sormak veya "pahalı mı?" diye merak etmek nötrdür; fiyattan açıkça yakınmak ("bu fiyat saçmalık") şikâyettir.
- Görüşmede hem sitem hem teşekkür varsa görüşmenin SONUNDAKİ ve baskın tona göre karar ver: sorun çözüldüyse ve müşteri memnun ayrıldıysa olumlu, çözülmediyse olumsuz seç. Açıkça dile getirilmiş bir yakınma varsa complaint true olabilir; o durumda sentiment olumsuz seçilir.
- Konuşmacı etiketleri ("Müşteri" ve "Firma") varsa yalnızca "Müşteri" satırlarına bak; firmanın sitemi veya özrü müşterinin duygusu değildir. Etiketler "Bilinmiyor" ise (tek kanallı kayıt), sözlerinden müşteri tarafını ayırt etmeye çalış ve tüm metni bu gözle değerlendir; ayıramıyorsan notr seç ve güveni düşük tut.
- Nezaket kalıpları (merhaba, iyi günler, rica ederim) duygu belirtisi sayılmaz.
- Ton belirsizse veya görüşme çok kısaysa notr seç ve güveni düşük tut.
- evidence: Kararını destekleyen, MÜŞTERİNİN sözünden kelimesi kelimesine kısa bir alıntı. Uygun alıntı yoksa null; nötr kararlarda genellikle null olur.
- confidence: 0 ile 1 arası; ton görüşmede açıkça belli ise 0.8 üzeri, belirsizse 0.6 altı.
- reason: Kararının tek cümlelik gerekçesi; hangi ifadeye veya davranışa dayandığını belirt.
