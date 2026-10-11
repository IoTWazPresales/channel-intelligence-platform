"""AI assist that is enabled but cannot build a client must raise."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.core.config import get_settings
from app.services.imports.ai_import_resolver import (
    AiResolverUnavailable,
    _anthropic_client,
    _call_claude,
    suggest_token_resolution,
)


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_resolver_silent_when_ai_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_ASSIST_ENABLED", "false")
    get_settings.cache_clear()
    assert _anthropic_client() is None
    assert suggest_token_resolution("raw", "product", [], None) is None


def test_resolver_raises_when_enabled_and_key_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_ASSIST_ENABLED", "true")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    get_settings.cache_clear()
    with pytest.raises(AiResolverUnavailable, match="client key is missing"):
        suggest_token_resolution("raw", "product", [{"id": 1}], None)


def test_resolver_raises_when_enabled_and_package_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_ASSIST_ENABLED", "true")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-used")
    get_settings.cache_clear()
    real_import = __import__

    def _blocked(name, globals=None, locals=None, fromlist=(), level=0):  # noqa: ANN001
        if name == "anthropic":
            raise ImportError("anthropic is not installed")
        return real_import(name, globals, locals, fromlist, level)

    with patch("builtins.__import__", side_effect=_blocked):
        with pytest.raises(AiResolverUnavailable, match="package is not installed"):
            _anthropic_client()


def test_api_call_failure_still_returns_none() -> None:
    client = MagicMock()
    client.messages.create.side_effect = RuntimeError("upstream down")
    with patch("app.services.imports.ai_import_resolver._anthropic_client", return_value=client):
        assert _call_claude(system="s", user="u") is None


def test_unavailable_from_api_call_is_not_swallowed() -> None:
    client = MagicMock()
    client.messages.create.side_effect = AiResolverUnavailable("client disappeared")
    with patch("app.services.imports.ai_import_resolver._anthropic_client", return_value=client):
        with pytest.raises(AiResolverUnavailable, match="client disappeared"):
            _call_claude(system="s", user="u")
