"""``listing_live_fetch_enabled``: worker env and API Settings (D-0061, 2026-11-24)."""

from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.services.listing_capture.observation import listing_live_fetch_enabled


@pytest.fixture(autouse=True)
def _settings_env(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.delenv("CIP_LISTING_LIVE_FETCH", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/cip")
    monkeypatch.setenv("DATABASE_URL_SYNC", "postgresql://u:p@localhost/cip")
    yield
    get_settings.cache_clear()


@pytest.mark.parametrize("raw", ["1", "true", "on", "TRUE"])
def test_process_env_enables_live_fetch(monkeypatch, raw: str) -> None:
    monkeypatch.setenv("CIP_LISTING_LIVE_FETCH", raw)
    assert listing_live_fetch_enabled() is True


@pytest.mark.parametrize("raw", ["0", "false", ""])
def test_process_env_off_when_unset_or_false(monkeypatch, raw: str) -> None:
    if raw:
        monkeypatch.setenv("CIP_LISTING_LIVE_FETCH", raw)
    else:
        monkeypatch.delenv("CIP_LISTING_LIVE_FETCH", raising=False)
    base = get_settings()
    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: base.model_copy(update={"cip_listing_live_fetch": False}),
    )
    assert listing_live_fetch_enabled() is False


def test_api_settings_enable_when_process_env_unset(monkeypatch) -> None:
    base = get_settings()
    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: base.model_copy(update={"cip_listing_live_fetch": True}),
    )
    assert listing_live_fetch_enabled() is True


def test_process_env_wins_when_settings_are_off(monkeypatch) -> None:
    monkeypatch.setenv("CIP_LISTING_LIVE_FETCH", "1")
    base = get_settings()
    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: base.model_copy(update={"cip_listing_live_fetch": False}),
    )
    assert listing_live_fetch_enabled() is True