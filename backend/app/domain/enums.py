"""Sabit değer listeleri (enum). Değerler küçük harf, Türkçe karakter ve boşluk içermez.

Kesinleşti (#7). Talep kategorileri ve servis emri durumları Miço Usta uygulamasından alındı
(Sistem Yönetimi > Hizmetler ve Operasyon & CRM > Servis Emirleri, 11 Ekim 2026). Ayrıntılı
tanımlar ve kurallar: docs/enums.md.

Değer eklemek serbesttir; silmek veya yeniden adlandırmak veritabanını (CHECK), agent
prompt'larını, sentetik etiketleri ve frontend tiplerini etkilediği için hepsi birlikte
güncellenir.

Arayüzde gösterilecek Türkçe karşılıklar `LABELS_TR` sözlüğündedir.
"""

from enum import StrEnum


class CallType(StrEnum):
    """Çağrı tipi (Çağrı Sınıflandırma Agent'ı)."""

    YENI_MUSTERI = "yeni_musteri"
    SERVIS = "servis"
    TEKLIF = "teklif"
    ACIL = "acil"
    BILGI = "bilgi"


class RequestCategory(StrEnum):
    """Müşteri talebinin kategorisi (CRM: "Müşteri talebi").

    Miço Usta'nın hizmet kategorileriyle birebir aynıdır; CRM önerisi servis emrine dönüşürken
    kategorisi bu listeden biri olmak zorundadır. Kategoriler Miço Usta'da yönetici tarafından
    değiştirilebildiği için ileride bu liste uygulamanın API'sinden okunabilir. Pasif olan
    "Kaptan Kiralama" bilerek yoktur (servis emri açılamaz).
    """

    MAKINE = "makine"
    MEKANIK_HIDROLIK = "mekanik_hidrolik"
    ELEKTRIK_ELEKTRONIK = "elektrik_elektronik"
    SU_SIHHI_TESISAT = "su_sihhi_tesisat"
    IKLIMLENDIRME = "iklimlendirme"
    TEKNE_GUVENLIGI = "tekne_guvenligi"
    TEMIZLIK_BAKIM = "temizlik_bakim"
    DIGER = "diger"


class ServiceMode(StrEnum):
    """Hizmetin veriliş biçimi (CRM: "Talep", örn. "Yerinde servis")."""

    YERINDE_SERVIS = "yerinde_servis"
    ATOLYEDE = "atolyede"
    UZAKTAN_DESTEK = "uzaktan_destek"


class Urgency(StrEnum):
    """Aciliyet seviyesi."""

    DUSUK = "dusuk"
    NORMAL = "normal"
    YUKSEK = "yuksek"
    ACIL = "acil"  # batma, yangın, yakıt kaçağı gibi güvenlik riski


class NextAction(StrEnum):
    """Önerilen sonraki aksiyon."""

    SERVIS_RANDEVUSU_OLUSTUR = "servis_randevusu_olustur"
    TEKLIF_HAZIRLA = "teklif_hazirla"
    GERI_ARA = "geri_ara"
    BILGI_VER = "bilgi_ver"
    USTA_ATA = "usta_ata"
    AKSIYON_YOK = "aksiyon_yok"


class SalesOutcomeType(StrEnum):
    """Satışın sonucu."""

    SATISA_DONUSTU = "satisa_donustu"
    KAYBEDILDI = "kaybedildi"
    BEKLEMEDE = "beklemede"


class ServiceOrderStatus(StrEnum):
    """Servis emri durumu (Miço Usta iş akışı: Yeni Atandı → ... → Tamamlandı)."""

    YENI_ATANDI = "yeni_atandi"
    KESIFTE = "kesifte"
    ONAYLANDI = "onaylandi"
    DEVAM_EDIYOR = "devam_ediyor"
    TAMAMLANDI = "tamamlandi"


class SwitchboardOutcome(StrEnum):
    """Santral/CRM'de çağrının kapanış sonucu (çağrı bilgisi; ses dosyasından çıkmaz)."""

    RANDEVU_OLUSTURULDU = "randevu_olusturuldu"
    USTA_YONLENDIRILDI = "usta_yonlendirildi"
    KAYIT_OLUSTURULDU = "kayit_olusturuldu"
    BILGI_VERILDI = "bilgi_verildi"
    GERI_ARANACAK = "geri_aranacak"
    IPTAL = "iptal"


class LossReason(StrEnum):
    """Satışın kaybedilme nedeni (yalnızca `kaybedildi` iken)."""

    FIYAT = "fiyat"
    GEC_DONUS = "gec_donus"
    RAKIP = "rakip"
    TAKVIM = "takvim"
    GUVEN = "guven"
    DIGER = "diger"


LABELS_TR: dict[StrEnum, str] = {
    CallType.YENI_MUSTERI: "Yeni müşteri",
    CallType.SERVIS: "Servis talebi",
    CallType.TEKLIF: "Teklif talebi",
    CallType.ACIL: "Acil servis",
    CallType.BILGI: "Bilgi",
    RequestCategory.MAKINE: "Makine",
    RequestCategory.MEKANIK_HIDROLIK: "Mekanik & Hidrolik",
    RequestCategory.ELEKTRIK_ELEKTRONIK: "Elektrik & Elektronik",
    RequestCategory.SU_SIHHI_TESISAT: "Su & Sıhhi Tesisat",
    RequestCategory.IKLIMLENDIRME: "İklimlendirme & Havalandırma",
    RequestCategory.TEKNE_GUVENLIGI: "Tekne Güvenlik Hizmetleri",
    RequestCategory.TEMIZLIK_BAKIM: "Temizlik & Tekne Bakımı",
    RequestCategory.DIGER: "Diğer",
    ServiceMode.YERINDE_SERVIS: "Yerinde servis",
    ServiceMode.ATOLYEDE: "Atölyede servis",
    ServiceMode.UZAKTAN_DESTEK: "Uzaktan destek",
    Urgency.DUSUK: "Düşük",
    Urgency.NORMAL: "Normal",
    Urgency.YUKSEK: "Yüksek",
    Urgency.ACIL: "Acil",
    NextAction.SERVIS_RANDEVUSU_OLUSTUR: "Servis randevusu oluştur",
    NextAction.TEKLIF_HAZIRLA: "Teklif hazırla",
    NextAction.GERI_ARA: "Müşteriyi geri ara",
    NextAction.BILGI_VER: "Bilgi ver",
    NextAction.USTA_ATA: "Usta ata",
    NextAction.AKSIYON_YOK: "Aksiyon gerekmiyor",
    SalesOutcomeType.SATISA_DONUSTU: "Satışa dönüştü",
    SalesOutcomeType.KAYBEDILDI: "Kaybedildi",
    SalesOutcomeType.BEKLEMEDE: "Beklemede",
    ServiceOrderStatus.YENI_ATANDI: "Yeni Atandı",
    ServiceOrderStatus.KESIFTE: "Keşifte",
    ServiceOrderStatus.ONAYLANDI: "Onaylandı",
    ServiceOrderStatus.DEVAM_EDIYOR: "Devam Ediyor",
    ServiceOrderStatus.TAMAMLANDI: "Tamamlandı",
    SwitchboardOutcome.RANDEVU_OLUSTURULDU: "Randevu oluşturuldu",
    SwitchboardOutcome.USTA_YONLENDIRILDI: "Usta yönlendirildi",
    SwitchboardOutcome.KAYIT_OLUSTURULDU: "Kayıt oluşturuldu",
    SwitchboardOutcome.BILGI_VERILDI: "Bilgi verildi",
    SwitchboardOutcome.GERI_ARANACAK: "Geri aranacak",
    SwitchboardOutcome.IPTAL: "İptal",
    LossReason.FIYAT: "Fiyat",
    LossReason.GEC_DONUS: "Geç dönüş",
    LossReason.RAKIP: "Rakip",
    LossReason.TAKVIM: "Takvim uygunsuzluğu",
    LossReason.GUVEN: "Güven",
    LossReason.DIGER: "Diğer",
}
