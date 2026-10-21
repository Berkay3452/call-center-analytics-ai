"""Ses depolama sağlayıcısı kayıt defteri ve fabrika fonksiyonları (#121)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.config import Settings
    from app.storage.base import AudioStorage


def build_audio_storage(settings: Settings | None = None) -> AudioStorage:
    """Yapılandırmaya göre uygun ses depolama sağlayıcısını üretir."""
    if settings is None:
        from app.core.config import get_settings

        settings = get_settings()

    backend = settings.audio_storage_backend

    if backend == "gcs":
        from app.storage.gcs import GcsAudioStorage

        return GcsAudioStorage(
            bucket_name=settings.gcs_bucket_name,
            project_id=settings.gcs_project_id,
            credentials_file=settings.gcs_credentials_file,
        )

    # Varsayılan: "local"
    from app.services.audio_ingest import storage_dir
    from app.storage.local import LocalAudioStorage

    return LocalAudioStorage(base_dir=storage_dir(settings))
