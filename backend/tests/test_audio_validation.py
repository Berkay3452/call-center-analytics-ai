"""Ses yükleme içerik doğrulaması ve harici STT politikası (#270)."""

import io
import stat
import sys
from pathlib import Path

import pytest

from app.core.config import Settings
from app.services.audio_ingest import AudioTooLongError, UnsupportedAudioError, store_audio
from app.storage.audio_validation import magic_matches, validate_audio_upload
from app.storage.local import LocalAudioStorage
from tests.audio_fixtures import make_wav
from tests.conftest import make_settings

MAX = 25 * 1024 * 1024


def _validate(data: bytes, name: str, *, max_duration_s: float = 600) -> None:
    validate_audio_upload(io.BytesIO(data), name, max_bytes=MAX, max_duration_s=max_duration_s)


def test_valid_wav_passes_and_stream_is_rewound() -> None:
    source = io.BytesIO(make_wav())
    validate_audio_upload(source, "a.wav", max_bytes=MAX, max_duration_s=600)
    assert source.tell() == 0


@pytest.mark.parametrize(
    ("data", "name"),
    [
        (b"MZ\x90\x00" + b"\x00" * 200, "kotu.wav"),  # Windows çalıştırılabilir dosyası, uzantı wav
        (b"%PDF-1.7\n" + b"0" * 200, "belge.mp3"),
        (b"<html><script>alert(1)</script></html>", "sayfa.ogg"),
        (b"PK\x03\x04" + b"0" * 200, "arsiv.flac"),
        (b"0" * 200, "duz.webm"),
    ],
)
def test_fake_extension_is_rejected(data: bytes, name: str) -> None:
    with pytest.raises(UnsupportedAudioError, match="uyuşmuyor"):
        _validate(data, name)


def test_wav_header_with_garbage_body_is_rejected() -> None:
    """Başlığı doğru ama gövdesi çöp olan dosya kod çözücü denetiminden geçemez."""
    pytest.importorskip("av")
    bad = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\xff" * 300
    with pytest.raises(UnsupportedAudioError):
        _validate(bad, "bozuk.wav")


def test_truncated_wav_header_only_is_rejected() -> None:
    pytest.importorskip("av")
    with pytest.raises(UnsupportedAudioError):
        _validate(make_wav()[:20], "kesik.wav")


def test_too_long_audio_is_rejected() -> None:
    pytest.importorskip("av")
    with pytest.raises(AudioTooLongError) as exc:
        _validate(make_wav(3.0), "uzun.wav", max_duration_s=1)
    assert exc.value.status_code == 413
    assert exc.value.code == "audio_too_long"


def test_oversize_is_left_to_storage_413() -> None:
    validate_audio_upload(io.BytesIO(b"0" * 100), "a.mp3", max_bytes=10, max_duration_s=60)


def test_unknown_extension_is_left_to_storage_415() -> None:
    _validate(b"anything", "a.pdf")


def test_magic_bytes_for_each_format() -> None:
    assert magic_matches(make_wav()[:16], ".wav")
    assert magic_matches(b"ID3\x04" + b"\x00" * 12, ".mp3")
    assert magic_matches(b"\xff\xfb\x90\x00" + b"\x00" * 12, ".mp3")
    assert magic_matches(b"\x00\x00\x00\x20ftypM4A " + b"\x00" * 4, ".m4a")
    assert magic_matches(b"OggS" + b"\x00" * 12, ".ogg")
    assert magic_matches(b"fLaC" + b"\x00" * 12, ".flac")
    assert magic_matches(b"\x1a\x45\xdf\xa3" + b"\x00" * 12, ".webm")
    assert not magic_matches(b"RIFF\x00\x00\x00\x00AVI " + b"\x00" * 4, ".wav")


def test_store_audio_rejects_fake_before_saving(tmp_path: Path) -> None:
    with pytest.raises(UnsupportedAudioError):
        store_audio(
            io.BytesIO(b"MZ" + b"\x00" * 100),
            "ses.wav",
            LocalAudioStorage(tmp_path),
            max_bytes=MAX,
            max_duration_s=600,
        )
    assert list(tmp_path.iterdir()) == []  # hiçbir şey diske yazılmadı


@pytest.mark.parametrize("evil", ["../../etc/passwd.wav", "..\\..\\kacis.wav", "/etc/x.wav"])
def test_upload_filename_cannot_escape_storage_dir(tmp_path: Path, evil: str) -> None:
    """Dosya adı yalnızca uzantı için kullanılır; kayıt adı içerik özetidir (yol gezintisi yok)."""
    root = tmp_path / "depo"
    stored = store_audio(
        io.BytesIO(make_wav()),
        evil,
        LocalAudioStorage(root),
        max_bytes=MAX,
        max_duration_s=600,
    )
    assert "/" not in stored.relative_path and "\\" not in stored.relative_path
    assert stored.relative_path == f"{stored.sha256}.wav"
    assert [p.name for p in root.iterdir()] == [stored.relative_path]
    assert not (tmp_path / "kacis.wav").exists()


def test_external_stt_is_off_by_default() -> None:
    assert Settings.model_fields["stt_allow_external"].default is False
    assert make_settings().stt_allow_external is False


def test_openai_compatible_stt_requires_explicit_opt_in() -> None:
    with pytest.raises(ValueError, match="STT_ALLOW_EXTERNAL"):
        make_settings(stt_provider="openai_compatible")
    ok = make_settings(stt_provider="openai_compatible", stt_allow_external=True)
    assert ok.stt_provider == "openai_compatible"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX dosya izinleri")
def test_local_storage_permissions_are_owner_only(tmp_path: Path) -> None:
    root = tmp_path / "izinli"
    stored = store_audio(
        io.BytesIO(make_wav()), "a.wav", LocalAudioStorage(root), max_bytes=MAX, max_duration_s=600
    )
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    assert stat.S_IMODE((root / stored.relative_path).stat().st_mode) == 0o600
