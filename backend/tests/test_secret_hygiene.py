"""Gizli anahtar hijyeni (#272): LLM/STT/embedding/servis anahtarları yalnızca ortam değişkeninden
okunur, kodda varsayılan değer taşımaz ve metin/günlük çıktısına düşmez."""

import json
import logging
import re
from pathlib import Path

import pytest
import structlog

from app.core.config import Settings
from app.core.logging import configure_logging

SECRET_FIELDS = {
    "SERVICE_API_KEY": "service_api_key",
    "LLM_API_KEY": "llm_api_key",
    "STT_API_KEY": "stt_api_key",
    "EMBEDDING_API_KEY": "embedding_api_key",
    "SUPABASE_SERVICE_ROLE_KEY": "supabase_service_role_key",
}
SENTINEL = "SIZDIRMA-TESTI-0123456789-abcdef"


def _settings_from_env(monkeypatch: pytest.MonkeyPatch) -> Settings:
    for env_name in SECRET_FIELDS:
        monkeypatch.setenv(env_name, f"{SENTINEL}-{env_name}")
    monkeypatch.setenv("APP_ENV", "test")
    return Settings(_env_file=None)


def test_secrets_are_read_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _settings_from_env(monkeypatch)
    for env_name, field in SECRET_FIELDS.items():
        value = getattr(s, field)
        assert value is not None
        assert value.get_secret_value() == f"{SENTINEL}-{env_name}"


def test_secret_fields_have_no_hardcoded_default(monkeypatch: pytest.MonkeyPatch) -> None:
    for env_name in SECRET_FIELDS:
        monkeypatch.delenv(env_name, raising=False)
    s = Settings(_env_file=None, app_env="test")
    for field in SECRET_FIELDS.values():
        assert getattr(s, field) is None, f"{field} kodda varsayılan değer taşımamalı"


def test_secrets_never_appear_in_text_or_dump(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _settings_from_env(monkeypatch)
    rendered = [repr(s), str(s), s.model_dump_json(), json.dumps(s.model_dump(), default=str)]
    for text in rendered:
        assert SENTINEL not in text


def test_logging_settings_object_does_not_leak(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    s = _settings_from_env(monkeypatch)
    configure_logging("DEBUG", json_logs=True)
    try:
        structlog.get_logger("test").info("ayarlar", settings=s, llm_key=s.llm_api_key)
        logging.getLogger("stdlib").warning("ayarlar: %s", s)
        err = capsys.readouterr().err
        assert "ayarlar" in err
        assert SENTINEL not in err
    finally:
        structlog.reset_defaults()


def test_no_secret_like_literals_in_source() -> None:
    """Kaynak koda gömülmüş sağlayıcı anahtarı desenleri (gitleaks'e ek, hızlı yerel kontrol)."""
    pattern = re.compile(
        r"(nvapi-[A-Za-z0-9_-]{40,}|sk-[A-Za-z0-9]{32,}|AIza[0-9A-Za-z_-]{35}|AKIA[0-9A-Z]{16}"
        r"|ghp_[A-Za-z0-9]{36}|hf_[A-Za-z0-9]{30,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)"
    )
    root = Path(__file__).resolve().parents[1]
    offenders = [
        str(p.relative_to(root))
        for folder in ("app", "scripts", "tests")
        for p in (root / folder).rglob("*.py")
        if p.name != Path(__file__).name and pattern.search(p.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_env_example_has_empty_secret_values() -> None:
    example = Path(__file__).resolve().parents[1] / ".env.example"
    values: dict[str, str] = {}
    for line in example.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, _, val = line.partition("=")
            values[key.strip()] = val.strip()
    for env_name in ("LLM_API_KEY", "STT_API_KEY", "EMBEDDING_API_KEY"):
        if env_name in values:
            assert values[env_name] == "", f"{env_name} .env.example içinde boş olmalı"
