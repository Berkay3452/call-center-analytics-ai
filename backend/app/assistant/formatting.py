"""Asistanın cevap ve kaynak kartlarında kullandığı Türkçe sayı ve tarih biçimleri (#83).

Cevap metni (`answer.py`) ve kaynak kartı alıntıları (`tools.py`) aynı biçimi kullansın diye
tek yerde tutulur.
"""

from datetime import date
from decimal import Decimal

MONTHS = [
    "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
]  # fmt: skip


def format_date(d: date) -> str:
    """2026-08-15 → '15 Ağustos 2026'."""
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def format_try(amount: Decimal) -> str:
    """14250.00 → '14.250,00 TL' (Türkçe sayı biçimi)."""
    text = f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{text} TL"
