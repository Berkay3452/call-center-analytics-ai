"""STT ortak yardımcıları: kullanıcıya görünen hatalarda sunucu yolu sızmaz (#216)."""

import pytest

from app.stt.base import redact_paths

URL = "Bağlantı reddedildi: https://api.example.com/v1/audio"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (r"Invalid data: 'C:\Users\ali\audio\a.wav'", "Invalid data: '<dosya>'"),
        ("No such file: C:/data/audio/a.wav", "No such file: <dosya>"),
        ("Hata: '/var/app/storage/audio/a.wav' açılamadı", "Hata: '<dosya>' açılamadı"),
        (URL, URL),
        ("Ses çözümlenemedi: boş dosya", "Ses çözümlenemedi: boş dosya"),
    ],
)
def test_redact_paths(raw: str, expected: str) -> None:
    assert redact_paths(raw) == expected
