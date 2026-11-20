"""STT alan terimi doğruluğu ve hata hizalaması (#328)."""

import pytest

from app.stt.metrics import (
    digits_to_words,
    error_class,
    is_format_only,
    load_terms,
    number_to_words,
    term_accuracy,
    word_errors,
)


@pytest.fixture(scope="module")
def terms() -> dict[str, list[str]]:
    return load_terms()


def test_terms_file_has_expected_classes(terms: dict[str, list[str]]) -> None:
    assert set(terms) == {"marka", "parca", "yer", "tekne_adi", "gun_ay", "sayi"}
    assert all(roots for roots in terms.values())


def test_perfect_transcript_scores_full(terms: dict[str, list[str]]) -> None:
    ref = "Tuzla Marina'da Yanmar motoru için akü ve sintine pompası, Perşembe saat 14."
    acc = term_accuracy(ref, ref, terms)
    assert all(hit == total for hit, total in acc.values())
    assert {"yer", "marka", "parca", "gun_ay", "sayi"} <= set(acc)


def test_suffixed_forms_count_as_term(terms: dict[str, list[str]]) -> None:
    acc = term_accuracy("aküyü değiştirelim", "aküyü değiştirelim", terms)
    assert acc["parca"] == (1, 1)
    # Ek almış hâl, köke eşit sayılır: referans "akü", çıktı "aküsü".
    assert term_accuracy("akü", "aküsü", terms)["parca"] == (1, 1)


def test_misspelled_term_is_a_miss(terms: dict[str, list[str]]) -> None:
    acc = term_accuracy("Yanmar motor", "yan mar motor", terms)
    assert acc["marka"] == (0, 1)


def test_short_stems_need_exact_match(terms: dict[str, list[str]]) -> None:
    # "on" sayı sözcüğüdür; "onu" ya da "onay" sayı sayılmaz.
    assert "sayi" not in term_accuracy("onu onay", "onu onay", terms)
    assert term_accuracy("on tane", "on tane", terms)["sayi"] == (1, 1)


def test_extra_terms_in_output_do_not_raise_score(terms: dict[str, list[str]]) -> None:
    acc = term_accuracy("akü", "akü akü akü", terms)
    assert acc["parca"] == (1, 1)


def test_repeated_term_counts_each_occurrence(terms: dict[str, list[str]]) -> None:
    acc = term_accuracy("akü ve akü", "akü", terms)
    assert acc["parca"] == (1, 2)


def test_digits_and_words_are_equivalent_numbers(terms: dict[str, list[str]]) -> None:
    # Whisper "14.30" yazar, referans "on dört otuz": ikisi aynı sayıdır.
    assert term_accuracy("saat on dört otuz", "saat 14 30", terms)["sayi"] == (3, 3)
    assert term_accuracy("saat 14 30", "saat on dört", terms)["sayi"] == (2, 3)


@pytest.mark.parametrize(
    ("n", "words"),
    [
        (0, "sıfır"),
        (9, "dokuz"),
        (14, "on dört"),
        (100, "yüz"),
        (120, "yüz yirmi"),
        (1300, "bin üç yüz"),
        (2500, "iki bin beş yüz"),
        (10000, "on bin"),
        (123456, "yüz yirmi üç bin dört yüz elli altı"),
    ],
)
def test_number_to_words(n: int, words: str) -> None:
    assert number_to_words(n) == words


def test_digits_to_words_leaves_other_tokens() -> None:
    assert digits_to_words("Saat 14.30'da 2 motor") == "saat on dört otuz da iki motor"
    assert digits_to_words("0532 1234567") == "0532 1234567"  # telefon biçimi dokunulmaz


def test_format_only_differences() -> None:
    assert is_format_only("on beş", "15")
    assert is_format_only("marina da", "marinada")
    assert not is_format_only("akü", "aki")
    assert not is_format_only("", "ve")


def test_masks_are_ignored(terms: dict[str, list[str]]) -> None:
    acc = term_accuracy("[İSİM] Bodrum'da", "Ali Bodrum'da", terms)
    assert acc["yer"] == (1, 1)


def test_word_errors_alignment() -> None:
    errors = word_errors("motor akü pompa", "motor akı pompa ve")
    assert ("değişti", "akü", "akı") in errors
    assert ("eklendi", "", "ve") in errors
    assert word_errors("aynı metin", "aynı metin") == []


def test_word_errors_deletion() -> None:
    assert word_errors("bir iki üç", "bir üç") == [("silindi", "iki", "")]


def test_error_class(terms: dict[str, list[str]]) -> None:
    assert error_class("yanmar", terms) == "marka"
    assert error_class("perşembe", terms) == "gun_ay"
    assert error_class("merhaba", terms) == "genel"
