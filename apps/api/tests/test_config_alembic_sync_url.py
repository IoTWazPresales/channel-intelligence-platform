"""Settings must expose optional sync migrate URL used by alembic/env.py."""

from app.core.config import Settings, get_settings


def test_settings_database_url_sync_migrate_optional():
    get_settings.cache_clear()
    s = Settings()
    assert hasattr(s, "database_url_sync_migrate")
    assert s.database_url_sync_migrate is None
    assert "postgresql" in s.database_url_sync
