"""Kullanıcı hesabı sabitleri (#278): roller, parola politikası, kilitlenme eşikleri."""

from enum import StrEnum


class AccountRole(StrEnum):
    ADMIN = "admin"  # yönetici (çağrı merkezi/ofis)
    OWNER = "owner"  # tekne sahibi (customer_id zorunlu)


MIN_PASSWORD_LENGTH = 12
MAX_FAILED_ATTEMPTS = 5  # üst üste bu kadar yanlış parola hesabı geçici olarak kilitler
LOCK_MINUTES = 15


def password_problems(password: str) -> list[str]:
    """Kayıt parola kuralı (#382): en az 12 karakter, büyük harf, küçük harf ve özel sembol.

    Eksik her kural için bir ileti döner; boş liste = parola geçerli. Özel sembol: harf, rakam
    ve boşluk dışındaki herhangi bir karakter.
    """
    problems: list[str] = []
    if len(password) < MIN_PASSWORD_LENGTH:
        problems.append(f"en az {MIN_PASSWORD_LENGTH} karakter")
    if not any(c.isupper() for c in password):
        problems.append("en az bir büyük harf")
    if not any(c.islower() for c in password):
        problems.append("en az bir küçük harf")
    if not any(not c.isalnum() and not c.isspace() for c in password):
        problems.append("en az bir özel sembol (ör. ! ? # % + = - _ .)")
    return problems


def password_policy_message(problems: list[str]) -> str:
    return "Parola şunları içermeli: " + ", ".join(problems) + "."
