"""Kayıt parola kuralı (#382): en az 12 karakter, büyük harf, küçük harf, özel sembol."""

import pytest

from app.domain.accounts import password_policy_message, password_problems
from app.services.accounts import generate_password


@pytest.mark.parametrize(
    "password",
    ["Abcdefghij!k", "Güçlü-Parola_2026", "ÇiçekBahçesi.12", "Aa!aaaaaaaaa"],
)
def test_strong_passwords_pass(password: str) -> None:
    assert password_problems(password) == []


@pytest.mark.parametrize(
    ("password", "expected"),
    [
        ("Ab!kisa", "12 karakter"),
        ("kucukharfsadece!!", "büyük harf"),
        ("BUYUKHARFSADECE!!", "küçük harf"),
        ("SembolsuzParola123", "özel sembol"),
        ("Boşluk Boşluk Boşluk", "özel sembol"),  # boşluk sembol sayılmaz
    ],
)
def test_each_missing_rule_is_reported(password: str, expected: str) -> None:
    problems = password_problems(password)
    assert any(expected in p for p in problems)
    assert expected in password_policy_message(problems)


def test_generated_passwords_always_satisfy_the_rule() -> None:
    assert all(password_problems(generate_password()) == [] for _ in range(300))
