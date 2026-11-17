"""Kullanıcı hesabı sabitleri (#278): roller, parola politikası, kilitlenme eşikleri."""

from enum import StrEnum


class AccountRole(StrEnum):
    ADMIN = "admin"  # yönetici (çağrı merkezi/ofis)
    OWNER = "owner"  # tekne sahibi (customer_id zorunlu)


MIN_PASSWORD_LENGTH = 12
MAX_FAILED_ATTEMPTS = 5  # üst üste bu kadar yanlış parola hesabı geçici olarak kilitler
LOCK_MINUTES = 15
