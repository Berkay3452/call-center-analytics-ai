"""Maskelemenin geri çağırma ve yanlış maskeleme ölçümü (#268).

Sentetik, elle etiketlenmiş cümleler `mask_text` ile maskelenir. Her cümlede:

- `gizli`: maskeden sonra metinde KALMAMASI gereken kişisel veri parçaları (geri çağırma);
- `korunan`: kişisel veri olmayan, ama kişisel veriye benzeyen ve metinde KALMASI gereken
  ifadeler (yanlış maskeleme / kesinlik).

`zor=True` işaretli cümleler kalıp dışı (yazıyla söylenen numara, küçük harfli adres, kalıpsız
ad) durumlardır; kuralların kapsamı dışında olduğunu dürüstçe göstermek için ayrı raporlanır.

Kullanım (backend/ klasöründe; LLM veya veritabanı gerekmez):

    python -m scripts.maskeleme_olcum
"""

import argparse
import io
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from app.services.masking import mask_text


@dataclass(frozen=True)
class Ornek:
    kategori: str
    metin: str
    gizli: tuple[str, ...] = ()
    korunan: tuple[str, ...] = ()
    zor: bool = False
    adlar: tuple[str, ...] = field(default=())


# Kart numaraları yayımlanmış test numaralarıdır; kimlik/telefon/IBAN değerleri uydurmadır.
OLCUM_SETI: tuple[Ornek, ...] = (
    # --- e-posta
    Ornek("e-posta", "E-postam ayse.demir@ornek.com, oraya yazın.", ("ayse.demir@ornek.com",)),
    Ornek(
        "e-posta",
        "Fatura için muhasebe_tekne@yatservis.com.tr adresini kullanın.",
        ("muhasebe_tekne@yatservis.com.tr",),
    ),
    Ornek("e-posta", "Mail adresim: kaptan.ali+tekne@ornek.org", ("kaptan.ali+tekne@ornek.org",)),
    Ornek(
        "e-posta",
        "Mailim ali.kaya at ornek nokta com.",
        ("ali.kaya at ornek nokta com",),
        zor=True,
    ),
    # --- IBAN
    Ornek(
        "iban", "IBAN'ım TR33 0006 1005 1978 6457 8413 26.", ("TR33 0006 1005 1978 6457 8413 26",)
    ),
    Ornek("iban", "TR330006100519786457841326 hesabına yatırın.", ("TR330006100519786457841326",)),
    Ornek("iban", "İban numarası tr33 0006 1005 1978 6457 8413 26 olacak.", ("1005 1978 6457",)),
    # --- T.C. kimlik no
    Ornek("tc-kimlik", "T.C. kimlik numaram 10000000146.", ("10000000146",)),
    Ornek("tc-kimlik", "Kimlik 10000000146 ile kayıt açın.", ("10000000146",)),
    Ornek("tc-kimlik", "Kimlik numarası 100 000 001 46.", ("100 000 001 46",)),
    # --- telefon
    Ornek("telefon", "0532 123 45 67 numarasından arayın.", ("0532 123 45 67",)),
    Ornek("telefon", "Beni +90 (532) 123-45-67 numarasından bulun.", ("+90 (532) 123-45-67",)),
    Ornek("telefon", "5321234567 olsun.", ("5321234567",)),
    Ornek("telefon", "Numaram 0 532 123 45 67.", ("0 532 123 45 67",)),
    Ornek(
        "telefon",
        "Telefonum sıfır beş yüz otuz iki yüz yirmi üç kırk beş altmış yedi.",
        ("sıfır beş yüz otuz iki",),
        zor=True,
    ),
    # --- banka/kredi kartı
    Ornek("kart", "Kart numaram 4539 1488 0343 6467.", ("4539 1488 0343 6467",)),
    Ornek("kart", "5555-5555-5555-4444 kartıyla ödeyeceğim.", ("5555-5555-5555-4444",)),
    Ornek("kart", "4111111111111111 numaralı karttan çekin.", ("4111111111111111",)),
    Ornek("kart", "Kartın son dört hanesi 6467.", korunan=("6467",)),
    # --- pasaport / ehliyet
    Ornek("belge-no", "Pasaport numaram U12345678.", ("U12345678",)),
    Ornek("belge-no", "Ehliyet no: 123456 olacak.", ("123456",)),
    Ornek("belge-no", "Ehliyet numaram A1234567.", ("A1234567",)),
    Ornek("belge-no", "Yurt dışı için P98765432 kayıtlı.", ("P98765432",)),
    # --- vergi no
    Ornek("vergi-no", "Vergi numaramız 1234567890.", ("1234567890",)),
    Ornek("vergi-no", "VKN: 9876543210 şirket adına fatura.", ("9876543210",)),
    Ornek(
        "vergi-no",
        "Vergi kimlik no 1122334455, vergi dairesi Kadıköy.",
        ("1122334455",),
        ("Kadıköy",),
    ),
    # --- adres
    Ornek(
        "adres",
        "Cumhuriyet Mahallesi 12. Sokak No 5 Daire 3'e gelin.",
        ("Cumhuriyet", "No 5", "Daire 3"),
    ),
    Ornek("adres", "Adresim Atatürk Caddesi No: 45, Bodrum.", ("Atatürk", "No: 45"), ("Bodrum",)),
    Ornek("adres", "Bağdat Cad. 123/4 Kadıköy.", ("Bağdat", "123/4"), ("Kadıköy",)),
    Ornek("adres", "Yelkovan Sitesi B Blok Kat 2'de oturuyorum.", ("Yelkovan", "Kat 2")),
    Ornek("adres", "Fevzi Çakmak Bulvarı 88 numarada evim var.", ("Fevzi", "88")),
    Ornek(
        "adres",
        "Adres atatürk mahallesi gül sokak numara 7.",
        ("atatürk mahallesi gül sokak",),
        zor=True,
    ),
    Ornek(
        "adres",
        "Tekne Yalıkavak Marina'da bağlı, 3 gün sonra çıkacak.",
        korunan=("Yalıkavak Marina", "3 gün"),
    ),
    # --- araç / tekne plakası
    Ornek("plaka", "Aracımın plakası 34 ABC 123.", ("34 ABC 123",)),
    Ornek("plaka", "35 DE 4567 plakalı kamyonet geliyor.", ("35 DE 4567",)),
    Ornek("plaka", "Tekne tescil numarası BDR-1234.", ("BDR-1234",)),
    Ornek("plaka", "Bağlama kütüğü no: TR-45678.", ("TR-45678",)),
    Ornek("plaka", "Plaka 06 AB 12 diye yazılı.", ("06 AB 12",)),
    Ornek("plaka", "Aracın plakası 34 abc 123.", ("34 abc 123",), zor=True),
    # --- listede olmayan ad
    Ornek("ad", "Ben Mehmet Yıldız, teknem Rüzgar.", ("Mehmet", "Yıldız"), ("Rüzgar",)),
    Ornek("ad", "Adım Selin Aksoy.", ("Selin", "Aksoy")),
    Ornek("ad", "İsmim Okan.", ("Okan",)),
    Ornek("ad", "Merhaba, Ayşe Hanım ile görüşüyorum.", ("Ayşe",)),
    Ornek("ad", "Hasan Bey teknede bekliyor.", ("Hasan",)),
    Ornek("ad", "Ben Burak Çelik'im, motor çalışmıyor.", ("Burak", "Çelik")),
    Ornek("ad", "Mehmet'e söyleyin, motoru kontrol etsin.", ("Mehmet",), zor=True),
    Ornek("ad", "Teknenin sahibi Cem Karaca, yarın arayacak.", ("Cem", "Karaca")),
    # Bilinen listeden (çağrı bilgisi) gelen ad: harf büyüklüğüne bakılmaz.
    Ornek(
        "ad (bilinen liste)",
        "Ben Burak Çelik. burak bey mi arıyor, ÇELİK?",
        ("Burak", "burak", "ÇELİK"),
        adlar=("Burak Çelik",),
    ),
    # --- yanlış maskeleme denetimi (kişisel veri yok, kişisel veriye benzeyen ifadeler)
    Ornek(
        "korunan",
        "Motor 2500 devirde, saat 14:30, 3 gün sonra gelin.",
        korunan=("2500 devirde", "14:30", "3 gün"),
    ),
    Ornek("korunan", "Yerinde arıza tespiti bin beş yüz lira.", korunan=("bin beş yüz lira",)),
    Ornek("korunan", "Randevu 15.10.2026 tarihinde 14:30'da.", korunan=("15.10.2026", "14:30")),
    Ornek(
        "korunan",
        "Jeanneau Sun Odyssey 440, 2018 model.",
        korunan=("Jeanneau Sun Odyssey 440", "2018 model"),
    ),
    Ornek("korunan", "Ben Miço Usta'dan arıyorum.", korunan=("Miço", "Usta")),
    Ornek("korunan", "Ben Tuzla Marina'dan arıyorum.", korunan=("Tuzla Marina",)),
    Ornek("korunan", "Volvo Penta D2-40, 40 HP 2500 devir.", korunan=("40 HP 2500",)),
    Ornek("korunan", "Fatura tutarı 12500 TL, KDV dahil.", korunan=("12500 TL",)),
    Ornek("korunan", "Sipariş numarası 45821 olarak kayda geçti.", korunan=("45821",)),
    Ornek("korunan", "Kaptan Bey yarın gelecek.", korunan=("Kaptan Bey",)),
    Ornek("korunan", "Marmaris'te duruyor, ben İstanbul'dayım.", korunan=("İstanbul'dayım",)),
    # Tekne adı kişisel veri değildir; analizde tekne adı gerekir.
    Ornek("korunan", "Bavaria C42, on iki yaşında, adı Mavi Rota.", korunan=("Mavi Rota",)),
)


@dataclass
class Sonuc:
    kategori: str
    gizli_toplam: int = 0
    gizli_yakalanan: int = 0
    korunan_toplam: int = 0
    korunan_bozulan: int = 0
    kacirilan: list[str] = field(default_factory=list)
    bozulan: list[str] = field(default_factory=list)


def olc(zor: bool | None = None) -> dict[str, Sonuc]:
    """Kategori bazında sonuç. `zor`: None → hepsi, False → kalıp kapsamı, True → kalıp dışı."""
    sonuclar: dict[str, Sonuc] = {}
    for o in OLCUM_SETI:
        if zor is not None and o.zor != zor:
            continue
        s = sonuclar.setdefault(o.kategori, Sonuc(o.kategori))
        masked = mask_text(o.metin, o.adlar)
        for g in o.gizli:
            s.gizli_toplam += 1
            if g in masked:
                s.kacirilan.append(f"{g!r} → {masked!r}")
            else:
                s.gizli_yakalanan += 1
        for k in o.korunan:
            s.korunan_toplam += 1
            if k not in masked:
                s.korunan_bozulan += 1
                s.bozulan.append(f"{k!r} → {masked!r}")
    return sonuclar


def _oran(a: int, b: int) -> str:
    return "-" if b == 0 else f"%{100 * a / b:.0f} ({a}/{b})"


def rapor(sonuclar: dict[str, Sonuc]) -> list[str]:
    satirlar = ["| Kategori | Geri çağırma | Yanlış maskeleme (korunan bozuldu) |", "|---|---|---|"]
    for s in sonuclar.values():
        satirlar.append(
            f"| {s.kategori} | {_oran(s.gizli_yakalanan, s.gizli_toplam)} "
            f"| {s.korunan_bozulan}/{s.korunan_toplam} |"
        )
    toplam = Sonuc("toplam")
    for s in sonuclar.values():
        toplam.gizli_toplam += s.gizli_toplam
        toplam.gizli_yakalanan += s.gizli_yakalanan
        toplam.korunan_toplam += s.korunan_toplam
        toplam.korunan_bozulan += s.korunan_bozulan
    satirlar.append(
        f"| **Toplam** | **{_oran(toplam.gizli_yakalanan, toplam.gizli_toplam)}** "
        f"| **{toplam.korunan_bozulan}/{toplam.korunan_toplam}** |"
    )
    return satirlar


SENTETIK_CAGRILAR = Path(__file__).parents[2] / "data" / "synthetic" / "calls"


def sentetik_degisenler() -> tuple[int, list[tuple[str, str, str]]]:
    """Sentetik çağrıların her konuşma turunu maskeler; metni DEĞİŞTİREN turları döner.

    Sentetik metinlerde gerçek kişisel veri yoktur (adlar zaten `[İSİM]`), yani değişen her tur
    olası bir yanlış maskelemedir. Dönen: (toplam tur, [(çağrı, özgün, maskeli)]).
    """
    toplam = 0
    degisen: list[tuple[str, str, str]] = []
    for yol in sorted(SENTETIK_CAGRILAR.glob("*.json")):
        for tur in json.loads(yol.read_text(encoding="utf-8"))["turns"]:
            toplam += 1
            maskeli = mask_text(tur["text"])
            if maskeli != tur["text"]:
                degisen.append((yol.stem, tur["text"], maskeli))
    return toplam, degisen


def main() -> None:
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args()
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    toplam, degisen = sentetik_degisenler()
    print(f"Sentetik çağrılar: {toplam} turdan {len(degisen)} tanesi maskeleme ile değişti.")
    for cagri, ozgun, maskeli in degisen:
        print(f"- {cagri}: {ozgun!r} → {maskeli!r}")
    for baslik, zor in [
        ("Kalıp kapsamındaki cümleler", False),
        ("Kalıp dışı (zor) cümleler", True),
    ]:
        sonuclar = olc(zor)
        print(f"\n### {baslik}\n")
        print("\n".join(rapor(sonuclar)))
        for s in sonuclar.values():
            for satir in [*s.kacirilan, *s.bozulan]:
                print(f"- [{s.kategori}] {satir}")
    print(f"\nToplam cümle: {len(OLCUM_SETI)}")


if __name__ == "__main__":
    main()
