"""Sentetik veri üretimi ve veritabanı tohumlama (seed) paketi (#23).

Kullanım (backend/ klasöründe):
    python -m scripts.seed                  # JSON dosyalarını üretir + veritabanını doldurur
    python -m scripts.seed --generate-only  # Yalnızca data/synthetic/*.json dosyalarını üretir
    python -m scripts.seed --reset          # Tabloları temizleyip sıfırdan doldurur
"""

from scripts.seed.generator import (
    DATA_DIR,
    MARINAS,
    SEED,
    deterministic_uuid,
    generate_dataset,
    load_calls_bundle,
    write_synthetic_files,
)
from scripts.seed.loader import seed_database

__all__ = [
    "DATA_DIR",
    "MARINAS",
    "SEED",
    "deterministic_uuid",
    "generate_dataset",
    "load_calls_bundle",
    "seed_database",
    "write_synthetic_files",
]
