# Sabit Değer Listeleri (Enum)

**Issue:** #7 · **Kaynak kod:** `backend/app/domain/enums.py` · **Tarih:** 2026-10-11

Bu listeler sistemin ortak dilidir: agent çıktıları (#14), veritabanı `CHECK` kısıtları (#5), sentetik çağrı etiketleri (#12) ve frontend tipleri (`frontend/lib/types.ts`) bu değerleri kullanır.

**Biçim:** değerler küçük harf, ASCII, boşluksuz (`gec_donus`). Ekranda gösterilen Türkçe karşılıklar `enums.py` içindeki `LABELS_TR` sözlüğündedir.

---

## 1. Talep kategorisi (`RequestCategory`)

CRM kaydındaki "Müşteri talebi". **Miço Usta'nın hizmet kategorileriyle birebir aynıdır** (Admin > Sistem Yönetimi > Hizmetler, 11 Ekim 2026): CRM önerisi Miço Usta'da bir servis emrine dönüşür ve servis emrinin kategorisi bu listeden biri olmak zorundadır.

| Değer | Ekranda | Kapsam (Miço Usta açıklaması + örnek belirtiler) |
|---|---|---|
| `makine` | Makine | Motor bakım, onarım, revizyon; motor yağı, yağ ve yakıt filtresi, yakıt sistemi, devir sorunu, tekleme, çalışmama, soğutma suyu pompası, impeller |
| `mekanik_hidrolik` | Mekanik & Hidrolik | Şanzıman, hidrolik sistemler, pervane, dümen |
| `elektrik_elektronik` | Elektrik & Elektronik | Akü, şarj, alternatör, regülatör, navigasyon, elektrik tesisatı, sigorta |
| `su_sihhi_tesisat` | Su & Sıhhi Tesisat | Su tankı, pompa, banyo, sintine sistemleri, teknenin su alması |
| `iklimlendirme` | İklimlendirme & Havalandırma | Klima, havalandırma, soğutma sistemleri |
| `tekne_guvenligi` | Tekne Güvenlik Hizmetleri | Yangın söndürme, can kurtarma ekipmanları, fener kontrolü |
| `temizlik_bakim` | Temizlik & Tekne Bakımı | İç/dış temizlik, cila, tente bakımı, döşeme, ip çevirme |
| `diger` | Diğer | Hiçbirine uymayan talep (ör. gövde/karina onarımı, osmoz) |

**Kurallar** (agent prompt'u ve sentetik etiketler aynı kuralları izler):
- Müşterinin **tahminine** değil, bildirdiği **belirtiye** ve istenen işe göre seçilir: "Motor tekliyor, yakıt filtresi olabilir" → `makine`.
- Duman, yanık kablo/plastik kokusu, kısa devre → `elektrik_elektronik`. Motordan gelen ses, devir ya da çalışmama sorunu → `makine`.
- Birden fazla sistemi kapsayan paket taleplerinde (kış bakımı, yıllık bakım paketi) en ağır kalemin kategorisi seçilir. Motor kışlaması veya motor yağ bakımı varsa → `makine`.
- Görüşmede iş/hizmet konuşulmuyorsa (yalnızca genel bilgi sorusu) alan boş (`null`) kalır.
- Miço Usta'daki **Kaptan Kiralama** pasif olduğu için listede yoktur. Kategoriler Miço Usta'da yönetici tarafından değiştirilebildiğinden ileride bu liste uygulamanın API'sinden okunabilir.

## 2. Çağrı tipi (`CallType`)

| Değer | Ekranda | Tanım |
|---|---|---|
| `yeni_musteri` | Yeni müşteri | Firmayla ilk kez görüşen, hizmetleri ve paketleri tanımaya çalışan kişi |
| `servis` | Servis talebi | Belirli bir arıza veya bakım için iş yapılmasını isteyen müşteri |
| `teklif` | Teklif talebi | Fiyat/teklif isteyen, henüz iş yaptırma kararı vermemiş müşteri |
| `acil` | Acil servis | Can, tekne veya çevre için hemen müdahale gerektiren durum |
| `bilgi` | Bilgi | Mevcut işin durumu, randevu, çalışma saatleri gibi genel soru |

Birden fazla tip uyuyorsa öncelik: `acil` > `servis` > `teklif` > `yeni_musteri` > `bilgi`.

## 3. Hizmet biçimi (`ServiceMode`), CRM'de "Talep"

| Değer | Ekranda | Tanım |
|---|---|---|
| `yerinde_servis` | Yerinde servis | Usta teknenin bulunduğu yere gider |
| `atolyede` | Atölyede servis | Tekne veya parça atölyeye/tersaneye getirilir |
| `uzaktan_destek` | Uzaktan destek | Telefonda yönlendirme veya bilgiyle çözülür |

## 4. Aciliyet (`Urgency`)

| Değer | Ekranda | Tanım |
|---|---|---|
| `acil` | Acil | Can, tekne veya çevre için hemen risk: su alma, batma riski, yangın, duman, yakıt kaçağı, denizde kalma |
| `yuksek` | Yüksek | Tekne kullanılamıyor veya müşteri bugün/yarın çözüm istiyor |
| `normal` | Normal | Sorun var ama tekne kullanılabiliyor; birkaç gün içinde çözülebilir |
| `dusuk` | Düşük | Planlı bakım, sezon hazırlığı, bilgi amaçlı talep |

## 5. Sonraki aksiyon (`NextAction`)

Firmanın görüşmeden **sonra** yapması gereken adım. Telefonda sözü verilen randevu veya usta ataması da CRM'de açılacağı için sonraki adımdır.

| Değer | Ekranda | Tanım |
|---|---|---|
| `servis_randevusu_olustur` | Servis randevusu oluştur | Usta ziyareti veya servis zamanı ayarlanacak |
| `teklif_hazirla` | Teklif hazırla | Müşteriye fiyat/teklif gönderilecek |
| `geri_ara` | Müşteriyi geri ara | Bilgi eksik veya karar bekleniyor; müşteri sonra aranacak |
| `bilgi_ver` | Bilgi ver | Firma müşteriye sonradan bilgi/haber iletecek (ör. "iş bitince mesaj atılır") |
| `usta_ata` | Usta ata | İşe hemen bir usta atanacak (özellikle acil durumlarda) |
| `aksiyon_yok` | Aksiyon gerekmiyor | Firmanın yapacağı bir şey kalmadı: bilgi görüşmede verildi veya müşteri vazgeçti |

## 6. Satış sonucu (`SalesOutcomeType`) ve kaybedilme nedeni (`LossReason`)

| Değer | Ekranda | Tanım |
|---|---|---|
| `satisa_donustu` | Satışa dönüştü | Müşteri görüşmede işi kabul etti (randevu, onay, iş verildi) |
| `kaybedildi` | Kaybedildi | Müşteri işi açıkça reddetti veya başka yere gideceğini söyledi |
| `beklemede` | Beklemede | Karar verilmedi veya görüşme satışla ilgili değil |

Kaybedilme nedeni **yalnızca** `kaybedildi` iken doludur ve o zaman zorunludur. Neden görüşmede açıkça geçmiyorsa `diger` seçilir.

| Değer | Ekranda | Tanım |
|---|---|---|
| `fiyat` | Fiyat | Fiyatı pahalı buldu, bütçesini aştı |
| `gec_donus` | Geç dönüş | Firmanın geç dönmesinden, bekletilmekten şikâyet etti |
| `rakip` | Rakip | Başka bir firma veya usta ile çalışacağını söyledi |
| `takvim` | Takvim uygunsuzluğu | İstediği zamana uygun usta/randevu bulunamadı |
| `guven` | Güven | İşçiliğe, garantiye veya güvenilirliğe şüpheyle yaklaştı |
| `diger` | Diğer | Kaybedildi ama neden açık değil veya listeye uymuyor |

## 7. Servis emri durumu (`ServiceOrderStatus`)

Miço Usta'nın iş akışı (Usta paneli ve Admin > Servis Emirleri).

| Değer | Ekranda |
|---|---|
| `yeni_atandi` | Yeni Atandı |
| `kesifte` | Keşifte |
| `onaylandi` | Onaylandı |
| `devam_ediyor` | Devam Ediyor |
| `tamamlandi` | Tamamlandı |

## 8. Santral sonucu (`SwitchboardOutcome`)

Çağrı bilgisinden gelir, ses dosyasından çıkmaz. Satış Analiz agent'ı bağlam olarak görür.

| Değer | Ekranda |
|---|---|
| `randevu_olusturuldu` | Randevu oluşturuldu |
| `usta_yonlendirildi` | Usta yönlendirildi |
| `kayit_olusturuldu` | Kayıt oluşturuldu |
| `bilgi_verildi` | Bilgi verildi |
| `geri_aranacak` | Geri aranacak |
| `iptal` | İptal |

## 9. Kodda tanımlı diğer listeler

| Liste | Değerler | Yer |
|---|---|---|
| Analiz durumu | `tamam`, `kismi`, `basarisiz` | `app/schemas/analysis.py` |
| Agent durumu / hata türü | `ok`, `failed`, `skipped` / `validation`, `runtime`, `timeout` | `app/agents/base.py` |
| Miço AI soru tipi | `gecmis_oneri`, `sayisal`, `genel_sohbet`, `kapsam_disi` | `app/schemas/assistant.py` |
| Miço AI kaynak türü | `service_record`, `boat_note`, `expense`, `subscription` | `app/schemas/assistant.py` |

---

## Bir değeri değiştirirken

Silme veya yeniden adlandırma aşağıdakilerin **hepsini** etkiler, birlikte güncellenir:
1. `backend/app/domain/enums.py` (değer ve `LABELS_TR`)
2. Agent prompt'ları (`backend/app/agents/prompts/`): her değerin tanımı prompt'ta olmalı (testle denetlenir)
3. `docs/db_schema.md`'deki `CHECK` listeleri ve migration (#6)
4. `data/synthetic/truth/` etiketleri
5. `frontend/lib/types.ts` (tipler ve etiketler) ve frontend mock'ları

`backend/tests/test_enum_consistency.py`, kod ile veritabanı dokümanı ve frontend tipleri arasındaki uyumsuzluğu yakalar.
