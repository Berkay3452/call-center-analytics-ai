"""Ses dosyası saklama (#49): biçim, boyut, içerik özetine göre ad. Veritabanı gerektirmez."""

import hashlib
import io
from pathlib import Path

import pytest

from app.services.audio_ingest import (
    AudioTooLargeError,
    UnsupportedAudioError,
    storage_dir,
    store_audio,
)
from tests.conftest import make_settings


def test_store_audio_names_file_by_content_hash(tmp_path: Path) -> None:
    data = b"RIFF" + b"\x01" * 3000

    stored = store_audio(io.BytesIO(data), "Kayıt 1.WAV", tmp_path, max_bytes=10_000)

    assert stored.sha256 == hashlib.sha256(data).hexdigest()
    assert stored.relative_path == f"{stored.sha256}.wav"
    assert stored.size_bytes == len(data)
    assert (tmp_path / stored.relative_path).read_bytes() == data
    assert list(tmp_path.iterdir()) == [tmp_path / stored.relative_path]  # geçici dosya kalmaz


def test_same_audio_twice_gives_same_file(tmp_path: Path) -> None:
    first = store_audio(io.BytesIO(b"abc"), "a.mp3", tmp_path, max_bytes=100)
    second = store_audio(io.BytesIO(b"abc"), "b.mp3", tmp_path, max_bytes=100)

    assert first == second
    assert len(list(tmp_path.iterdir())) == 1


@pytest.mark.parametrize("name", ["notlar.pdf", "ses", None, "video.mp4"])
def test_unsupported_extensions_are_rejected(tmp_path: Path, name: str | None) -> None:
    with pytest.raises(UnsupportedAudioError):
        store_audio(io.BytesIO(b"abc"), name, tmp_path, max_bytes=100)


def test_too_large_file_is_rejected_and_not_kept(tmp_path: Path) -> None:
    with pytest.raises(AudioTooLargeError):
        store_audio(io.BytesIO(b"0" * 101), "a.wav", tmp_path, max_bytes=100)

    assert list(tmp_path.iterdir()) == []


def test_empty_file_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(UnsupportedAudioError, match="boş"):
        store_audio(io.BytesIO(b""), "a.wav", tmp_path, max_bytes=100)
    assert list(tmp_path.iterdir()) == []


def test_storage_dir_is_relative_to_backend(tmp_path: Path) -> None:
    relative = storage_dir(make_settings(audio_storage_dir="storage/audio"))
    absolute = storage_dir(make_settings(audio_storage_dir=str(tmp_path)))

    assert relative.parts[-3:] == ("backend", "storage", "audio")
    assert absolute == tmp_path
