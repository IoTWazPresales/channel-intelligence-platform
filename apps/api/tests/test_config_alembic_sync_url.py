"""Settings must expose optional sync migrate URL used by alembic/env.py."""

import os

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, text

from app.core.config import Settings, get_settings
from app.db.sync_url import sqlalchemy_sync_engine_url

_CIP_TEST_ASYNC = "postgresql+asyncpg://cip:cip@localhost:5432/cip_test"
_CIP_TEST_SYNC = "postgresql://cip:cip@localhost:5432/cip_test"


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
    s = Settings(
        _env_file=(),
        database_url=_CIP_TEST_ASYNC,
        database_url_sync=_CIP_TEST_SYNC,
    )
    assert s.database_url_sync_migrate is None
    assert "postgresql" in s.database_url_sync


def test_settings_database_urls_required_when_unset(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL_SYNC", raising=False)
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=())
    message = str(exc.value)
    assert "database_url" in message
    assert "database_url_sync" in message


def test_current_database_is_cip_test():
    get_settings.cache_clear()
    engine = create_engine(sqlalchemy_sync_engine_url(get_settings().database_url_sync))
    try:
        with engine.connect() as conn:
            name = conn.execute(text("SELECT current_database()")).scalar()
    finally:
        engine.dispose()
    print(f"current_database()={name}")
    assert name == "cip_test"
