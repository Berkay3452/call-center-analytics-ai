"""Sağlam girdi türleri (#320, #338): kara kutu testinin bulduğu 500'leri 422'ye çevirir.

PostgreSQL metin sütunları NUL karakterini (kod 0), `int4` sütunları 2^31 üstü sayıyı ve
`timestamptz` sütunları yıl 1/9999 sınırındaki tarihleri kabul etmez; doğrulanmadan sorguya
giderse istemci hatası sunucu hatası (500) olarak döner. Bu türler hatayı şema katmanında yakalar.
"""

from datetime import date, datetime
from typing import Annotated

from pydantic import AfterValidator, Field

MIN_YEAR = 2000
MAX_YEAR = 2100


def _no_nul(value: str) -> str:
    if "\x00" in value:
        raise ValueError("Metin NUL (\x00) karakteri içeremez.")
    return value


def _sane_year[T: (date, datetime)](value: T) -> T:
    if not MIN_YEAR <= value.year <= MAX_YEAR:
        raise ValueError(f"Tarih {MIN_YEAR}-{MAX_YEAR} yılları arasında olmalıdır.")
    return value


SafeStr = Annotated[str, AfterValidator(_no_nul)]
"""Veritabanına giden serbest metin (NUL içeremez)."""

NameStr = Annotated[str, AfterValidator(_no_nul), Field(max_length=200)]
"""Kısa ad alanı: müşteri, tekne, marina (NUL içeremez, en fazla 200 karakter)."""

SaneDate = Annotated[date, AfterValidator(_sane_year)]
SaneDateTime = Annotated[datetime, AfterValidator(_sane_year)]

Seconds = Annotated[int, Field(ge=0, le=86_400)]
"""Süre (saniye): en fazla bir gün; `int4` taşmasını ve anlamsız süreleri engeller."""

Millis = Annotated[int, Field(ge=0, le=86_400_000)]
"""Konuşma içi zaman (milisaniye): en fazla bir gün."""
