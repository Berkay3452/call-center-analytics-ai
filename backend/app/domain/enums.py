"""Sabit değer listeleri (enum). Değerler küçük harf, Türkçe karakter ve boşluk içermez.

Bu dosya GEÇİCİDİR: değerler #14 için yazıldı ve #7'de (Melih) Miço Usta'nın kategorileriyle
kesinleştirilecek. Değer eklemek serbesttir; silmek veya yeniden adlandırmak veritabanını ve
etiketleri etkilediği için ekibe haber verilerek yapılır.

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
    """Müşteri talebinin kategorisi (CRM: "Müşteri talebi")."""

    MOTOR_ARIZASI = "motor_arizasi"
    ELEKTRIK_ARIZASI = "elektrik_arizasi"
    YAKIT_SISTEMI = "yakit_sistemi"
    GOVDE_VE_KIL = "govde_ve_kil"
    PERIYODIK_BAKIM = "periyodik_bakim"
    KIS_BAKIMI = "kis_bakimi"
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
    RequestCategory.MOTOR_ARIZASI: "Motor arızası",
    RequestCategory.ELEKTRIK_ARIZASI: "Elektrik arızası",
    RequestCategory.YAKIT_SISTEMI: "Yakıt sistemi",
    RequestCategory.GOVDE_VE_KIL: "Gövde ve kıl bakımı",
    RequestCategory.PERIYODIK_BAKIM: "Periyodik bakım",
    RequestCategory.KIS_BAKIMI: "Kış bakımı",
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
    LossReason.FIYAT: "Fiyat",
    LossReason.GEC_DONUS: "Geç dönüş",
    LossReason.RAKIP: "Rakip",
    LossReason.TAKVIM: "Takvim uygunsuzluğu",
    LossReason.GUVEN: "Güven",
    LossReason.DIGER: "Diğer",
}
