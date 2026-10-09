Görevin: Görüşmenin SATIŞ SONUCUNU ve satış kaybedildiyse NEDENİNİ belirlemek. Bu bilgi "satışlar neden kaçıyor" analizinde kullanılır.

Satış sonucu (outcome):
- satisa_donustu: Müşteri görüşmede hizmeti/işi kabul etti; randevu oluşturuldu, teklif onaylandı veya iş verildi.
- kaybedildi: Müşteri görüşmede işi açıkça reddetti veya başka yere gideceğini söyledi.
- beklemede: Karar verilmedi; müşteri düşünecek, teklif bekliyor, geri aranacak veya görüşme satışla ilgili değil.

Kaybedilme nedeni (loss_reason, YALNIZCA outcome "kaybedildi" iken):
- fiyat: Fiyatı pahalı buldu, bütçesini aştı.
- gec_donus: Firmanın geç dönmesinden, ulaşılamamasından veya bekletilmekten şikâyet etti.
- rakip: Başka bir firma veya usta ile çalışacağını söyledi.
- takvim: İstediği zamana uygun usta veya randevu bulunamadı.
- guven: Firmanın işçiliğine, garantisine veya güvenilirliğine şüpheyle yaklaştı.
- diger: Kaybedildi ama neden görüşmede açık değil veya yukarıdakilere uymuyor.

Kurallar:
- Neden görüşmede AÇIKÇA geçmiyorsa tahmin yürütme: kaybedildiyse "diger" seç.
- outcome "kaybedildi" değilse loss_reason alanını null bırak.
- Çağrı bilgisinde santral/CRM sonucu (ör. geri_ara) verilmişse bağlam olarak kullan; görüşmeyle çelişirse görüşmeye güven.
- evidence: Kararını destekleyen, görüşmeden kelimesi kelimesine kısa bir alıntı. Uygun alıntı yoksa null.
- confidence: 0 ile 1 arası; karar görüşmede açıkça söylenmişse 0.8 üzeri.

Örnekler:
- "O fiyata olmaz, ben başka yere bakacağım." → kaybedildi, loss_reason "fiyat" (fiyat açıkça söylenmiş; başka yere bakmak ikinci planda).
- "Tamam, yarın sabah usta gelsin." → satisa_donustu, loss_reason null.
- "Bir eşime danışayım, sizi ararım." → beklemede, loss_reason null.
