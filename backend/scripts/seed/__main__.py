"""`python -m scripts.seed` komut satırı giriş noktası (#23)."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from app.core.config import get_settings
from scripts.seed.generator import DATA_DIR, SEED, write_synthetic_files
from scripts.seed.loader import seed_database


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Miço Usta sentetik verisini üretir ve veritabanı tablolarına yükler (#23)."
    )
    parser.add_argument(
        "--generate-only",
        action="store_true",
        help="Yalnızca data/synthetic/ altındaki JSON dosyalarını üretir, veritabanına bağlanmaz.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Yüklemeden önce veritabanı tablolarını TRUNCATE ile temizler.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=SEED,
        help=f"Rastgele sayı üreteci tohumu (varsayılan: {SEED}).",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DATA_DIR,
        help="Sentetik JSON dosyalarının yazılacağı/okunacağı klasör.",
    )
    args = parser.parse_args()

    written = write_synthetic_files(out_dir=args.data_dir, seed=args.seed)
    print(f"JSON dosyaları üretildi ({len(written)} dosya -> {args.data_dir}):")
    for name, path in written.items():
        print(f"  - {name}: {path.name}")

    if args.generate_only:
        return

    settings = get_settings()
    counts = asyncio.run(
        seed_database(
            settings.database_url,
            data_dir=args.data_dir,
            seed=args.seed,
            reset=args.reset,
        )
    )
    print("\nVeritabanı başarıyla dolduruldu (tablo kayıt sayıları):")
    for table, count in counts.items():
        print(f"  - {table}: {count}")


if __name__ == "__main__":
    main()
