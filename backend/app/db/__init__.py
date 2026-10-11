"""Veritabanı erişimi: SQLAlchemy (async) motoru, oturumlar ve modeller.

Şemanın tek kaynağı Alembic migration'larıdır (`backend/alembic/versions/`). Modeller
(`app/db/models/`) migration'larla birebir aynı tutulur; CI `alembic check` ile farkı yakalar.
`create_all` kullanılmaz. Tasarım belgesi: docs/db_schema.md.
"""
