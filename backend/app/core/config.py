"""Uygulama ayarları.

Tüm yapılandırma ortam değişkenlerinden (veya backend/.env dosyasından) okunur.
Koda hiçbir anahtar veya model adı gömülmez; örnek değerler .env.example'dadır.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

AppEnv = Literal["local", "test", "staging", "prod"]


PLACEHOLDER_SERVICE_KEY = "change-me-in-local-env"


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
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:15432/call_center"
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_echo: bool = False
    # Supabase pooler (transaction mode) arkasında asyncpg hazır ifade önbelleği kapatılmalı (0).
    db_statement_cache_size: int = 0

    # --- Redis / Celery ---
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str | None = None  # boşsa redis_url kullanılır
    celery_result_backend: str | None = None  # boşsa redis_url kullanılır
    # Takılı kalan çağrı zaman aşımı (dakika). Bu süreden uzun süredir
    # 'beklemede', 'yaziya_cevriliyor' veya 'isleniyor' olan çağrılar otomatik kurtarılır (#107).
    stuck_call_timeout_min: int = Field(default=10, ge=1)

    # --- Sağlık kontrolü ---
    health_check_timeout_s: float = 2.0

    # --- Servis Anahtarı / Supabase Storage ---
    # .NET API'nin Python servisini çağırırken `X-Service-Key` ile gönderdiği paylaşılan anahtar.
    service_api_key: SecretStr | None = None
    supabase_url: str | None = None
    supabase_service_role_key: SecretStr | None = None  # yalnızca backend; asla frontend'e verilmez
    storage_bucket: str = "call-audio"
    # Yüklenen çağrı sesleri: geliştirmede yerel klasör (backend/'e göre), canlıda bulut deposu.
    # --- Ses Depolama (#121) ---
    audio_storage_backend: Literal["local", "gcs"] = "local"
    audio_storage_dir: str = "storage/audio"
    audio_max_mb: int = Field(default=25, ge=1)
    gcs_bucket_name: str = "call-audio"
    gcs_project_id: str | None = None
    gcs_credentials_file: str | None = None
    # Yalnızca local/test: servis anahtarı kurulmadan uçları denemek için doğrulamayı atlar.
    auth_dev_bypass: bool = False

    # --- LLM (ücretsiz, OpenAI-uyumlu API sağlayıcıları) ---
    llm_provider: Literal[
        "groq", "openrouter", "gemini", "nvidia", "ollama", "openai_compatible"
    ] = "groq"
    llm_base_url: str | None = None  # boşsa sağlayıcının varsayılan adresi kullanılır
    llm_api_key: SecretStr | None = None
    llm_fast_model: str | None = None  # sınıflandırma gibi hafif işler
    llm_smart_model: str | None = None  # özet, şikayet, RAG yanıtı gibi zor işler
    # Ücretsiz katmanların istek sınırı düşük olduğu için eşzamanlılık bilinçli olarak küçük.
    # Agent bazında model: doluysa o agent, katman modeli (fast/smart) yerine bunu kullanır.
    # Alan adı `llm_<agent adı>_model` biçimindedir (adlar için bkz. app/agents/names.py).
    llm_call_classifier_model: str | None = None
    llm_crm_extraction_model: str | None = None
    llm_sales_analyzer_model: str | None = None
    llm_summarizer_model: str | None = None
    llm_max_concurrency: int = Field(default=2, ge=1)
    # Model başına dakikadaki en fazla istek (0 = sınırsız). Gemini ücretsiz katmanı: 5.
    # Sınır süreç içidir; birden fazla Celery işçisi varsa her biri ayrı sayar.
    llm_requests_per_minute: int = Field(default=0, ge=0)
    # Nemotron gibi akıl yürüten modellerde düşünme çıktısını kapatır (NVIDIA): çok daha hızlı.
    llm_disable_thinking: bool = False
    # İstek başına zaman aşımı ve istemci içi yeniden deneme: kısa tutulur, yavaş/ölü bir model
    # ajanı dakikalarca bekletmesin (17 Ekim denemesinde 120 sn zaman aşımı görüldü).
    llm_timeout_s: float = Field(default=30.0, gt=0)
    llm_max_retries: int = Field(default=1, ge=0)
    # Ajanın (yedek model denemesi dahil) toplam süre bütçesi; aşılırsa ajan `timeout` ile biter.
    llm_agent_timeout_s: float = Field(default=90.0, gt=0)
    # Geçici hatada (zaman aşımı, 429, 5xx, bağlantı) bir kez denenecek yedek model. Boşsa
    # öteki katmanın modeli (fast <-> smart) yedek sayılır; o da yoksa yedek yoktur.
    llm_fallback_model: str | None = None
    # Sınıflandırma agent'ı diğerlerinden önce ayrı aşamada mı çalışsın? Varsayılan hayır: dördü
    # paralel çalışır, uçtan uca süre kısalır (#162).
    analysis_classifier_first: bool = False

    # --- STT (ses → metin) --- (#15; sağlayıcılar `app/stt/`)
    # faster_whisper: yerel, CPU'da çalışır (`stt` ekstrası). openai_compatible: Whisper API'si
    # (ör. Groq). stub: ses yanındaki .txt dosyasını okur; STT kurulmadan zinciri denemek için.
    stt_provider: Literal["faster_whisper", "openai_compatible", "stub"] = "faster_whisper"
    stt_language: str = "tr"
    # Konuşmacı ayrımı: santral kaydı stereo ise her kanal bir konuşmacıdır (temsilci sol/sağ).
    # Mono kayıtta konuşmacı ayrılamaz ("unknown"); model tabanlı ayrım sonraki adımdır.
    # Santral kayıtları iki kanallıdır (temsilci sol); mono dosyalar otomatik mono işlenir.
    stt_channel_layout: Literal["mono", "stereo_rep_left", "stereo_rep_right"] = "stereo_rep_left"
    whisper_model: str = "small"  # CPU için small/medium; GPU varsa large-v3
    whisper_compute_type: str = "int8"  # CPU: int8; GPU varsa float16
    whisper_cpu_threads: int = Field(default=0, ge=0)  # 0: otomatik
    # 1: beam 5 ile aynı doğrulukta (WER farkı <0,5 puan) yaklaşık 1,3-2 kat hızlı (#163 ölçümü).
    whisper_beam_size: int = Field(default=1, ge=1)
    # Ses etkinliği (VAD) eşiği: 0,5 dar bant telefon sesinde konuşmayı sessizlik sanıp atıyor
    # (#124 ölçümü: 97 kelimeden 28'i kalıyordu); 0,2 hem temiz hem telefon sesinde güvenli.
    whisper_vad_threshold: float = Field(default=0.2, gt=0, lt=1)
    # Modelin indirileceği klasör; boşsa Hugging Face varsayılanı (~/.cache/huggingface).
    whisper_download_root: str | None = None

    @field_validator("whisper_download_root", mode="before")
    @classmethod
    def _empty_download_root_is_none(cls, value: object) -> object:
        """`.env`'de boş bırakılan satır ("WHISPER_DOWNLOAD_ROOT=") klasör verilmiş sayılmaz."""
        return None if isinstance(value, str) and not value.strip() else value

    stt_api_base_url: str = "https://api.groq.com/openai/v1"
    stt_api_key: SecretStr | None = None
    stt_api_model: str = "whisper-large-v3"
    stt_timeout_s: float = 300.0

    # --- RAG / Embedding --- (#26; sağlayıcılar `app/rag/embedders.py`)
    # tei: bge-m3, Docker'da TEI servisi (CPU; infra/docker-compose.yml, "rag" profili).
    # openai_compatible: embedding API'si. hash: modelsiz, kelime tabanlı (test ve geliştirme).
    embedding_provider: Literal["tei", "openai_compatible", "hash"] = "tei"
    embedding_model: str = "BAAI/bge-m3"
    embedding_dim: int = 1024  # rag_chunks.embedding sütunuyla aynı olmalı
    tei_url: str = "http://localhost:8080"
    embedding_base_url: str | None = None  # openai_compatible için
    embedding_api_key: SecretStr | None = None
    embedding_timeout_s: float = 60.0
    embedding_batch_size: int = Field(default=16, ge=1)

    # --- Türetilmiş değerler ---
    @field_validator("llm_fallback_model", mode="before")
    @classmethod
    def _empty_fallback_is_none(cls, value: object) -> object:
        """`.env`'de boş bırakılan satır ("LLM_FALLBACK_MODEL=") yedek model verilmiş sayılmaz."""
        return None if isinstance(value, str) and not value.strip() else value

    def llm_fallback_for(
        self, agent_name: str, tier: Literal["fast", "smart"], primary: str | None
    ) -> str | None:
        """Geçici hatada kullanılacak yedek model adı; birincilden farklı değilse None."""
        other_tier = self.llm_smart_model if tier == "fast" else self.llm_fast_model
        candidate = self.llm_fallback_model or other_tier
        return candidate if candidate and candidate != primary else None

    def llm_model_for(self, agent_name: str, tier: Literal["fast", "smart"]) -> str | None:
        """Agent'ın kullanacağı model adı: önce agent'a özel ayar, yoksa katman modeli."""
        override: str | None = getattr(self, f"llm_{agent_name}_model", None)
        if override:
            return override
        return self.llm_fast_model if tier == "fast" else self.llm_smart_model

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
    def is_production(self) -> bool:
        return self.app_env == "prod"

    @model_validator(mode="after")
    def _guard_dev_bypass(self) -> "Settings":
        # Güvenlik: kimlik doğrulama atlatma yalnızca yerel geliştirme ve testte açılabilir.
        if self.auth_dev_bypass and self.app_env not in ("local", "test"):
            raise ValueError("AUTH_DEV_BYPASS yalnızca APP_ENV=local veya test iken açılabilir.")
        return self

    @model_validator(mode="after")
    def _guard_service_key(self) -> "Settings":
        # Güvenlik: canlıda boş veya örnek dosyadaki varsayılan servis anahtarı kullanılamaz.
        if self.is_production and not self.auth_dev_bypass:
            key = self.service_api_key.get_secret_value() if self.service_api_key else ""
            if len(key) < 32 or key == PLACEHOLDER_SERVICE_KEY:
                raise ValueError("SERVICE_API_KEY canlıda en az 32 karakterli, özel olmalıdır.")
        return self


@lru_cache
def get_settings() -> Settings:
    """Ayarları bir kez okuyup önbellekte tutar (FastAPI bağımlılığı olarak da kullanılır)."""
    return Settings()
