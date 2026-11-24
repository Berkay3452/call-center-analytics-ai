"""Denetim günlüğü sabitleri (#267): olay türleri ve sonuçlar.

Yeni olay türü eklemek migration gerektirmez (`audit_log.action` serbest metindir, değerler
kodda bu listeyle sınırlanır). Değerler küçük harf, Türkçe karakter ve boşluk içermez.
"""

from enum import StrEnum


class AuditOutcome(StrEnum):
    """Olayın sonucu. `audit_log.outcome` CHECK kısıtı bu listedendir."""

    BASARILI = "basarili"
    REDDEDILDI = "reddedildi"  # yetki/kimlik/kural nedeniyle reddedildi
    HATA = "hata"


class AuditAction(StrEnum):
    """Kaydedilen olay türleri."""

    KIMLIK_DOGRULAMA_BASARISIZ = "kimlik_dogrulama_basarisiz"
    CAGRI_YUKLENDI = "cagri_yuklendi"  # metin veya ses (details.kaynak)
    CAGRI_YENIDEN_ANALIZ = "cagri_yeniden_analiz"
    CAGRI_ESLESTIRILDI = "cagri_eslestirildi"  # elle müşteri/tekne eşleştirme
    CAGRI_SILINDI = "cagri_silindi"  # #269
    SES_ERISIMI = "ses_erisimi"
    CANLI_TRANSKRIPT_IZLENDI = "canli_transkript_izlendi"  # #324 (ham transkript akışı)
    CRM_ONAYLANDI = "crm_onaylandi"
    CRM_REDDEDILDI = "crm_reddedildi"
    SERVIS_EMRI_OLUSTURULDU = "servis_emri_olusturuldu"
    SERVIS_EMRI_DURUM_DEGISTI = "servis_emri_durum_degisti"
    ASISTAN_KURAL_IHLALI = "asistan_kural_ihlali"  # küfür, tehdit, kendine zarar...
    ASISTAN_INJECTION = "asistan_injection"
    ASISTAN_BASKA_TARAF = "asistan_baska_taraf"  # başka müşteri/tekne verisi isteği
    DENETIM_GORUNTULENDI = "denetim_goruntulendi"
    GIRIS_BASARILI = "giris_basarili"  # #369 (kullanıcı girişi)
    GIRIS_BASARISIZ = "giris_basarisiz"
    HESAP_KILITLENDI = "hesap_kilitlendi"


class AuditActorRole(StrEnum):
    """Eylemi yapan taraf. Hesap sistemi (#278) gelene kadar iki bağlam vardır."""

    SERVIS = "servis"  # servis anahtarı, X-User-Id yok (yönetici/arka uç bağlamı)
    TEKNE_SAHIBI = "tekne_sahibi"  # servis anahtarı + X-User-Id
    SISTEM = "sistem"  # istek bağlamı olmayan işler (Celery, zamanlanmış)
    ANONIM = "anonim"  # kimlik doğrulanamadı
