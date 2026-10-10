# Miço Usta — Wireframe & Arayüz Tasarım Dokümantasyonu

Bu dizin, **Yapay Zekâ Destekli Sesli Asistan ve Çağrı Analitiği Sistemi** için [micousta.com](https://micousta.com) entegrasyon kurallarına ve kurumsal görsel diline uygun olarak hazırlanan wireframe (ekran taslağı) dosyalarını ve mimari eşleşme detaylarını içerir (Issue #9).

---

## 🎨 Tasarım Dili ve Renk Paleti (Marine / Denizcilik Teması)

Miço Usta'nın mevcut panelleri (Gösterge Paneli, Servis Emirleri, Tekne Sahibi Portalı) ile birebir uyumlu bileşen kütüphanesi:

| Öğe | Hex / Renk Kodu | Tailwind Sınıfı | Kullanım Amacı |
|---|---|---|---|
| **Ana Koyu (Navy)** | `#0F172A` | `bg-slate-900` | Sidebar, üst başlık barları, modal çerçeveleri |
| **Miço Usta Mavisi** | `#0284C7` / `#0369A1` | `bg-sky-600` / `bg-sky-700` | Birincil butonlar, aktif navigasyon, marka ikonları |
| **Vurgu & İkincil Mavi** | `#38BDF8` / `#E0F2FE` | `bg-sky-400` / `bg-sky-100` | Dalga formu, rozet zeminleri, bilgi kutuları |
| **Zemin (Canvas)** | `#F8FAFC` | `bg-slate-50` / `bg-gray-50` | Sayfa genel arka planı |
| **Kart Zeminleri** | `#FFFFFF` | `bg-white` | İçerik panelleri, KPI modülleri, diyalog pencereleri |
| **Kritik / Acil Uyarı** | `#EF4444` / `#DC2626` | `bg-red-500` / `bg-red-600` | Acil servis talepleri, batma/yangın riski, kaybedilen satış |
| **Dikkat / Uyarı** | `#F59E0B` / `#D97706` | `bg-amber-500` / `bg-amber-600` | Kısmi analiz uyarısı, takip bekleyen çağrılar |
| **Başarı / Satış** | `#10B981` / `#16A34A` | `bg-emerald-500` / `bg-emerald-600` | Satışa dönüşen işler, tamamlanan servis emirleri |

---

## 📐 Ekran Hiyerarşisi ve SVG Wireframe Dosyaları

### 1. `01-cagri-analitigi.svg` — Çağrı Analitiği Dashboard (Admin)
- **Konum:** `/admin/analytics`
- **İçerik:**
  - **Üst Bar:** Marina filtre seçimi (*Kalamış, Göcek D-Marin, Bodrum Milta, Tuzla, Yalıkavak*), tarih aralığı filtresi, Rol Seçici (*🛡️ Admin*).
  - **7 Temel KPI Kartı:**
    1. Gelen Çağrı (1,248)
    2. Yeni Müşteri (87 tekne)
    3. Servis Talebi (432)
    4. Teklif Talebi (214)
    5. **Acil Servis (23 — kırmızı vurgulu ve alarm rozetli)**
    6. Satışa Dönüşen (%68)
    7. Ortalama Yanıt Süresi (4:32 dk)
  - **Grafik ve İstatistik Modülleri:**
    - *Günlük Çağrı Sayısı Trendi:* Son 7 güne ait çağrı hacmi sütun grafiği (Issue #36).
    - *En Sık Tekne Arızaları:* Motor & Tahrik (%45), Elektrik & Jeneratör (%35), Sintine & Su Tahliye (%27), Periyodik Bakım (%19), Gövde & Tutya (%14).
    - *En Yoğun Marinalar:* Kalamış (%37), Göcek (%31), Bodrum (%20), Tuzla (%8), Yalıkavak (%4).
    - *Satış Kaçırma Sebepleri:* Fiyat yüksek (%48), Geç dönüş (%34), Rakip usta tercihi (%14), Takvim uyuşmazlığı (%4).
  - **Son Çağrılar Tablosu:** Arayan kişi, tekne adı, marina, konu, süre, analiz durumu rozeti (`tamam`, `kismi`, `basarisiz`), aciliyet rozeti ve tek tıkla servis emrine geçiş linki (Issue #36).

---

### 2. `02-cagri-detay-crm.svg` — Çağrı Detayı ve CRM Servis Emri Önerisi (Admin)
- **Konum:** `/admin/calls/[id]`
- **İçerik:**
  - **Sol Panel (Ses & Transkript):**
    - Ses oynatıcı ve gerçekçi **Audio Waveform (Dalga Formu)** ile oynatma süresi göstergesi.
    - Ayrıştırılmış konuşma balonları: Müşteri (Tekne Sahibi) ve Miço Usta Temsilcisi diyalogları.
    - **Özetleme Agent'ı özeti:** En fazla 3 cümlelik Türkçe özet ve en fazla 3 anahtar madde (`CallSummary`).
  - **Sağ Panel (7 Alanlı CRM Servis Emri):**
    - Hocanın şart koştuğu ve `backend/app/schemas/analysis.py` (`CrmExtraction`) ile tanımlanan **7 Temel CRM Alanı**:
      1. `request_category` (Müşteri Talebi): *Motor Arızası*
      2. `location` (Marina / Lokasyon): *Kalamış Marina İskele C-12*
      3. `problem` (Problem Tanımı): *Ana makine devir almıyor, sintine su seviyesi alarmı aktif*
      4. `service_mode` (Hizmet Biçimi): *Yerinde Servis (yerinde_servis)*
      5. `urgency` (Aciliyet Seviyesi): *🚨 Kritik / Acil (acil)*
      6. `potential_job` (Potansiyel İş): *Motor Arıza Tespiti + Sintine Pompası Revizyonu*
      7. `next_action` (Önerilen Sonraki Aksiyon): *Servis Randevusu Oluştur & Usta Ata (servis_randevusu_olustur)*
    - **Kısmi Analiz Uyarı Rozeti:** Eksik veya şüpheli veri durumunda operatörü uyaran sarı rozet.
    - **Nöbetçi Usta Atama Kartı:** Kalamış Marina'da müsait olan Baş Usta Mehmet Şimşek kartı.
    - **Aksiyon Butonları:**
      - `[✓ ONAYLA VE SERVİS EMRİ OLUŞTUR]` (Miço Usta Mavisi `#0284C7`)
      - `[✏ Düzenle]` / `[✕ Reddet]` (Beyaz zemin / Kırmızı kenarlık)

---

### 3. `03-tekne-sahibi-asistan.svg` — Tekne Sahibi Yapay Zekâ Asistanı
- **Konum:** `/owner/assistant`
- **İçerik:**
  - Tekne Sahibi Portalı görünümü (Poyraz — Motoryat 42 tekne profili bağlı).
  - **Hızlı Soru Öneri Butonları (Prompt Chips):**
    - *"Son motor bakımım ne zaman yapıldı?"*
    - *"Bu ayki marina masrafım ne kadar?"*
    - *"Sintine alarmı neden çalar?"*
  - **Sohbet Akışı ve Yanıtlar:** Asistanın tekne geçmişine vakıf, teknik ve profesyonel yanıtları.
  - **Kaynak Atıf Kartı (Citation Cards - Dizi Formatı):**
    - Bot yanıtlarının altında yer alan doğrulanabilir referans kartları (`citations` dizisi).
    - *Örnek:* `📌 KAYNAK ATFI: 15 Ağustos 2024 tarihli Usta Görüşmesi & Servis Raporu (#SRV-2024-5120)`
    - *Alıntı:* `“Ana makine 250 saatlik bakımı tamamlandı, impeller yenilendi...”`
  - **"Bulamadım" Durumu (Issue #36):**
    - Kayıt bulunamadığında asistan kaynak kartı olmadan sade ve bilgilendirici mesaj döner: *"Bu konuda kayıtlarda bilgi bulamadım. Sigorta bilgileriniz sistemde kayıtlı değil..."*


---

## 🔗 Backend & Şema Eşleşme Tablosu (Issue #14)

| Ekrandaki Alan | Backend Şeması | `backend/app/domain/enums.py` Karşılığı |
|---|---|---|
| **Çağrı Tipi** | `CallClassification.call_type` | `CallType` (`yeni_musteri`, `servis`, `teklif`, `acil`, `bilgi`) |
| **Müşteri Talebi** | `CrmExtraction.request_category` | `RequestCategory` (`motor_arizasi`, `elektrik_arizasi`, `periyodik_bakim`...) |
| **Hizmet Biçimi** | `CrmExtraction.service_mode` | `ServiceMode` (`yerinde_servis`, `atolyede`, `uzaktan_destek`) |
| **Aciliyet** | `CrmExtraction.urgency` | `Urgency` (`dusuk`, `normal`, `yuksek`, `acil`) |
| **Sonraki Aksiyon** | `CrmExtraction.next_action` | `NextAction` (`servis_randevusu_olustur`, `teklif_hazirla`, `usta_ata`...) |
| **Satış Sonucu** | `SalesAnalysis.outcome` | `SalesOutcomeType` (`satisa_donustu`, `kaybedildi`, `beklemede`) |
| **Kayıp Sebebi** | `SalesAnalysis.loss_reason` | `LossReason` (`fiyat`, `gec_donus`, `rakip`, `takvim`, `guven`...) |
| **Analiz Durumu** | `AnalysisResult.status` | `AnalysisStatus` (`tamam`, `kismi`, `basarisiz`) |

---

## 🚀 Doğrulama ve Çalıştırma

Tüm mock veriler ve arayüz tipleri bu şemalarla uyumlu hale getirilmiştir:
```bash
cd frontend
npm run lint   # ESLint doğrulaması
npm run build  # Next.js ve TypeScript sıkı mod derleme doğrulaması
```
