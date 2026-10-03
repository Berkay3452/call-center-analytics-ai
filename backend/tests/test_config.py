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


def test_jwks_url_derived_from_supabase_url(settings_factory: Callable[..., Settings]) -> None:
    s = settings_factory(supabase_url="https://xyz.supabase.co/")
    assert s.jwks_url == "https://xyz.supabase.co/auth/v1/.well-known/jwks.json"


def test_broker_defaults_to_redis(settings_factory: Callable[..., Settings]) -> None:
    s = settings_factory(redis_url="redis://r:6379/0")
    assert s.broker_url == "redis://r:6379/0"
    assert s.result_backend_url == "redis://r:6379/0"
