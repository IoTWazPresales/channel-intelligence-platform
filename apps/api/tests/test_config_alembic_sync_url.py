"""Settings must expose optional sync migrate URL used by alembic/env.py."""

import os

from app.core.config import Settings, get_settings


def test_settings_database_url_sync_migrate_optional():
    get_settings.cache_clear()
    s = Settings()
    assert hasattr(s, "database_url_sync_migrate")
    assert "postgresql" in s.database_url_sync
    migrate_from_env = os.environ.get("DATABASE_URL_SYNC_MIGRATE")
    if migrate_from_env is not None:
        assert s.database_url_sync_migrate == migrate_from_env
        assert "postgresql" in s.database_url_sync_migrate
    elif s.database_url_sync_migrate is not None:
        assert "postgresql" in s.database_url_sync_migrate


def test_settings_database_url_sync_migrate_defaults_none(monkeypatch):
    """When unset, optional migrate URL is None (alembic falls back to database_url_sync)."""
    get_settings.cache_clear()
    monkeypatch.delenv("DATABASE_URL_SYNC_MIGRATE", raising=False)
    s = Settings(_env_file=())
    assert s.database_url_sync_migrate is None
    assert "postgresql" in s.database_url_sync
