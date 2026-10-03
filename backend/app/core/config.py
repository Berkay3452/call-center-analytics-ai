"""Uygulama ayarları.

Tüm yapılandırma ortam değişkenlerinden (veya backend/.env dosyasından) okunur.
Koda hiçbir anahtar veya model adı gömülmez; örnek değerler .env.example'dadır.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

AppEnv = Literal["local", "test", "staging", "prod"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Genel ---
    app_name: str = "Call Center Analytics API"
    app_env: AppEnv = "local"
    log_level: str = "INFO"
    # True: JSON log (sunucu/CI), False: renkli konsol logu (geliştirme)
    log_json: bool = False
    api_v1_prefix: str = "/api/v1"
    # Virgülle ayrılmış izinli origin listesi (ör. "http://localhost:3000,https://app.example.com")
    cors_origins: str = "http://localhost:3000"

    # --- Veritabanı (Supabase PostgreSQL + pgvector) ---
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5433/call_center"
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_echo: bool = False
    # Supabase pooler (transaction mode) arkasında asyncpg hazır ifade önbelleği kapatılmalı (0).
    db_statement_cache_size: int = 0

    # --- Redis / Celery ---
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str | None = None  # boşsa redis_url kullanılır
    celery_result_backend: str | None = None  # boşsa redis_url kullanılır

    # --- Sağlık kontrolü ---
    health_check_timeout_s: float = 2.0

    # --- Supabase Auth / Storage ---
    supabase_url: str | None = None
    supabase_jwks_url: str | None = None  # boşsa supabase_url'den türetilir
    supabase_jwt_audience: str = "authenticated"
    supabase_service_role_key: SecretStr | None = None  # yalnızca backend; asla frontend'e verilmez
    storage_bucket: str = "call-audio"
    # Yalnızca local/test: Supabase kurulmadan uçları denemek için JWT doğrulamasını atlar.
    auth_dev_bypass: bool = False

    # --- LLM (ücretsiz, OpenAI-uyumlu API sağlayıcıları) ---
    llm_provider: Literal["groq", "openrouter", "gemini", "ollama", "openai_compatible"] = "groq"
    llm_base_url: str | None = None  # boşsa sağlayıcının varsayılan adresi kullanılır
    llm_api_key: SecretStr | None = None
    llm_fast_model: str | None = None  # duygu, anahtar kelime, triage gibi hafif işler
    llm_smart_model: str | None = None  # özet, şikayet, RAG yanıtı gibi zor işler
    # Ücretsiz katmanların istek sınırı düşük olduğu için eşzamanlılık bilinçli olarak küçük.
    llm_max_concurrency: int = Field(default=2, ge=1)
    llm_timeout_s: float = 60.0
    llm_max_retries: int = 3

    # --- STT (ses → metin) ---
    stt_provider: Literal["faster_whisper", "openai_compatible"] = "faster_whisper"
    whisper_model: str = "small"  # GPU varsa: large-v3
    whisper_compute_type: str = "int8"  # GPU varsa: float16
    hf_token: SecretStr | None = None  # pyannote modeli için Hugging Face token

    # --- RAG / Embedding ---
    embedding_provider: Literal["tei", "openai_compatible"] = "tei"
    embedding_model: str = "BAAI/bge-m3"
    embedding_dim: int = 1024
    tei_url: str = "http://localhost:8080"

    # --- Türetilmiş değerler ---
    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def broker_url(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def result_backend_url(self) -> str:
        return self.celery_result_backend or self.redis_url

    @property
    def jwks_url(self) -> str | None:
        if self.supabase_jwks_url:
            return self.supabase_jwks_url
        if self.supabase_url:
            return f"{self.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
        return None

    @property
    def is_production(self) -> bool:
        return self.app_env == "prod"

    @model_validator(mode="after")
    def _guard_dev_bypass(self) -> "Settings":
        # Güvenlik: kimlik doğrulama atlatma yalnızca yerel geliştirme ve testte açılabilir.
        if self.auth_dev_bypass and self.app_env not in ("local", "test"):
            raise ValueError("AUTH_DEV_BYPASS yalnızca APP_ENV=local veya test iken açılabilir.")
        return self


@lru_cache
def get_settings() -> Settings:
    """Ayarları bir kez okuyup önbellekte tutar (FastAPI bağımlılığı olarak da kullanılır)."""
    return Settings()
