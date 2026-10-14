"""Transkript ayrıştırma ve kişisel veri maskeleme (#48). Veritabanı gerektirmez."""

import pytest

from app.agents.summarizer import find_personal_data
from app.schemas.api import SegmentIn
from app.services.masking import mask_text
from app.services.transcript_text import parse_transcript, with_timings

# --- Ayrıştırma ---------------------------------------------------------------------------


def test_parse_transcript_splits_speaker_lines() -> None:
    segs = parse_transcript("Temsilci: Miço Usta, buyurun.\nMüşteri: Motor tekliyor.")

    assert [(s.speaker, s.text) for s in segs] == [
        ("rep", "Miço Usta, buyurun."),
        ("customer", "Motor tekliyor."),
    ]


def test_parse_transcript_joins_unlabelled_lines_to_previous_turn() -> None:
    segs = parse_transcript("Müşteri: Motor tekliyor,\nyakıt filtresi olabilir.\nTemsilci: Tamam.")

    assert len(segs) == 2
    assert segs[0].text == "Motor tekliyor, yakıt filtresi olabilir."


def test_parse_transcript_without_labels_is_one_customer_turn() -> None:
    segs = parse_transcript("Merhaba, teknem Tuzla'da.\nMotor çalışmıyor.")

    assert len(segs) == 1
    assert segs[0].speaker == "customer"
    assert segs[0].text == "Merhaba, teknem Tuzla'da. Motor çalışmıyor."


def test_parse_transcript_ignores_blank_and_empty_turns() -> None:
    assert parse_transcript("\n  \nMüşteri:   \n") == []
    assert parse_transcript("") == []


def test_parse_transcript_does_not_treat_other_colons_as_speakers() -> None:
    segs = parse_transcript("Müşteri: Saat 14:30 gibi gelin.")

    assert segs[0].text == "Saat 14:30 gibi gelin."


def test_timings_are_sequential_and_respect_given_values() -> None:
    timed = with_timings(
        [
            SegmentIn(speaker="rep", text="Buyurun."),
            SegmentIn(speaker="customer", text="Merhaba " * 20),
            SegmentIn(speaker="rep", text="Tamam.", start_ms=50_000, end_ms=52_000),
        ]
    )

    (_, s0, e0), (_, s1, e1), (_, s2, e2) = timed
    assert s0 == 0
    assert e0 >= 1000
    assert s1 == e0
    assert e1 > s1
    assert (s2, e2) == (50_000, 52_000)


# --- Maskeleme ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "token"),
    [
        ("Numaram 0532 123 45 67, arayın.", "[TELEFON]"),
        ("+90 (532) 123-45-67 numarasından", "[TELEFON]"),
        ("Kimlik 12345678901 olacak", "[KİMLİK]"),
        ("Mail: burak.celik@ornek.com adresine", "[EPOSTA]"),
        ("IBAN TR33 0006 1005 1978 6457 8413 26 hesabına", "[IBAN]"),
    ],
)
def test_mask_text_replaces_personal_data(raw: str, token: str) -> None:
    masked = mask_text(raw)

    assert token in masked
    assert find_personal_data(masked.replace(token, "")) == []


def test_mask_text_masks_known_names_case_insensitively() -> None:
    masked = mask_text("Ben Burak Çelik. burak bey mi arıyor, ÇELİK?", ["Burak Çelik"])

    assert "Burak" not in masked
    assert "burak" not in masked
    assert masked.count("[İSİM]") >= 3


def test_mask_text_keeps_ordinary_numbers_and_words() -> None:
    text = "Motor 2500 devirde, saat 14:30, 3 gün sonra gelin. Rüzgar teknesi."

    assert mask_text(text, ["Burak Çelik"]) == text


def test_mask_text_ignores_empty_names() -> None:
    assert mask_text("Merhaba", [None, "", "  "]) == "Merhaba"
