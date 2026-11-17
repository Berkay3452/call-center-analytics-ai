"""Kişisel veri sızıntısı (OWASP LLM02, LLM06; KVKK): LLM'e giden metinde ham veri kalmamalı.

Saldırgan (veya konuşan müşteri) kişisel veriyi alışılmadık biçimlerde yazar: bölünmüş, tireli,
parantezli, satır sonlu, bağlam içinde gömülü. Maskeleme hepsini yakalamalı.
"""

import re

import pytest

from app.security import untrusted
from app.services.masking import mask_text

# (ham değer, cümle şablonu): ham değer maskeli çıktıda hiçbir biçimde kalmamalı.
CASES: list[tuple[str, str]] = [
    ("05321234567", "Beni {} numarasından arayın"),
    ("0532 123 45 67", "Telefonum {} tamam mı"),
    ("0 (532) 123-45-67", "Numara: {}"),
    ("+90 532 123 45 67", "WhatsApp {} üzerinden yazın"),
    ("0532-123-45-67", "{} arayın"),
    ("10000000146", "TC kimlik numaram {}"),
    ("TR33 0006 1005 1978 6457 8413 26", "IBAN'ım {}"),
    ("TR330006100519786457841326", "Hesap {} olarak yazılsın"),
    ("4539 1488 0343 6467", "Kartım {} son kullanma 12/28"),
    ("4539-1488-0343-6467", "Kart {}"),
    ("ahmet.yilmaz+tekne@ornek.com.tr", "Mail adresim {}"),
    ("Ahmet_Y@ornek.org", "E-posta: {}"),
    ("34 ABC 123", "Aracımın plakası {}"),
    ("06ABC1234", "Plaka {} olacak"),
    ("U12345678", "Pasaport numaram {}"),
]


@pytest.mark.parametrize(("raw", "template"), CASES)
def test_personal_data_is_masked_in_every_format(raw: str, template: str) -> None:
    masked = mask_text(template.format(raw))

    assert raw not in masked, masked
    # Ham verinin rakam dizisi de (biçim bozulsa bile) kalmamalı.
    digits = re.sub(r"\D", "", raw)
    if len(digits) >= 9:
        assert digits not in re.sub(r"\D", "", masked), masked


@pytest.mark.parametrize("sep", [" ", "\n", " , ", "; ", "\t"])
def test_data_next_to_other_text_is_still_masked(sep: str) -> None:
    text = f"Adım Ahmet Yılmaz{sep}telefon 0532 123 45 67{sep}mail a.b@c.de{sep}TC 10000000146"

    masked = mask_text(text)

    for raw in ("Ahmet Yılmaz", "0532 123 45 67", "a.b@c.de", "10000000146"):
        assert raw not in masked, (sep, masked)


def test_known_names_are_masked_case_insensitively_and_by_part() -> None:
    masked = mask_text("fatma hanımın teknesi albatros; KAYA bey de geldi", names=["Fatma Kaya"])

    assert "fatma" not in masked.lower() and "kaya" not in masked.lower()


def test_masking_is_idempotent_and_never_reintroduces_data() -> None:
    text = "Ben Ahmet Yılmaz, 0532 123 45 67, TR330006100519786457841326"
    once = mask_text(text)

    assert mask_text(once) == once


def test_output_filter_is_the_second_line_of_defence() -> None:
    """Maskelemeden kaçan ham kimlik/IBAN/kart LLM çıktısında yakalanır (LLM02)."""
    for leaked in (
        "TC: 10000000146",
        "IBAN TR33 0006 1005 1978 6457 8413 26",
        "kart 4539 1488 0343 6467",
    ):
        assert untrusted.output_leaks(leaked), leaked


@pytest.mark.xfail(
    strict=True,
    reason="Bilinen sınırlama (docs/maskeleme_olcum.md): yazıyla söylenen numaralar ve kalıp "
    "dışı serbest adlar kural tabanlı maskelemede yakalanamaz.",
)
def test_known_gap_numbers_spoken_as_words_are_not_masked() -> None:
    masked = mask_text("Telefonum sıfır beş üç iki yüz yirmi üç kırk beş altmış yedi")

    assert "sıfır beş üç iki" not in masked
