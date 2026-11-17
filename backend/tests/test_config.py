from collections.abc import Callable

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_dev_bypass_forbidden_outside_local(settings_factory: Callable[..., Settings]) -> None:
    with pytest.raises(ValidationError):
        settings_factory(app_env="prod", auth_dev_bypass=True)


def test_cors_origins_are_split(settings_factory: Callable[..., Settings]) -> None:
    s = settings_factory(cors_origins="http://a.com, http://b.com ,")
    assert s.cors_origin_list == ["http://a.com", "http://b.com"]


def test_service_api_key_stored_as_secret(settings_factory: Callable[..., Settings]) -> None:
    s = settings_factory(service_api_key="my-secret-key")
    assert s.service_api_key is not None
    assert s.service_api_key.get_secret_value() == "my-secret-key"


def test_broker_defaults_to_redis(settings_factory: Callable[..., Settings]) -> None:
    s = settings_factory(redis_url="redis://r:6379/0")
    assert s.broker_url == "redis://r:6379/0"
    assert s.result_backend_url == "redis://r:6379/0"


def test_prod_rejects_weak_service_key(settings_factory: Callable[..., Settings]) -> None:
    for weak in (None, "change-me-in-local-env", "kisa"):
        with pytest.raises(ValueError):
            settings_factory(
                app_env="prod",
                service_api_key=weak,
                audit_auth_failures=True,
                rate_limit_backend="redis",
            )
    ok = settings_factory(
        app_env="prod",
        service_api_key="x" * 40,
        audit_auth_failures=True,
        rate_limit_backend="redis",
    )
    assert ok.is_production


def test_prod_cannot_disable_auth_failure_audit(settings_factory: Callable[..., Settings]) -> None:
    with pytest.raises(ValueError, match="AUDIT_AUTH_FAILURES"):
        settings_factory(
            app_env="prod",
            service_api_key="x" * 40,
            audit_auth_failures=False,
            rate_limit_backend="redis",
        )


def test_empty_whisper_download_root_means_default_cache(
    settings_factory: Callable[..., Settings],
) -> None:
    """Boş `WHISPER_DOWNLOAD_ROOT=` satırı modeli çalışma klasörüne indirmemeli."""
    assert settings_factory(whisper_download_root="").whisper_download_root is None
    assert settings_factory(whisper_download_root="  ").whisper_download_root is None
    assert settings_factory(whisper_download_root="D:/m").whisper_download_root == "D:/m"


def test_prod_cannot_turn_rate_limit_off(settings_factory: Callable[..., Settings]) -> None:
    with pytest.raises(ValueError, match="RATE_LIMIT_BACKEND"):
        settings_factory(
            app_env="prod",
            service_api_key="x" * 40,
            audit_auth_failures=True,
            rate_limit_backend="off",
        )
