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
