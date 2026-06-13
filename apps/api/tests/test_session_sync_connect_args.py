"""Sync engine connect_args: keepalives + server-side idle/statement timeouts (DSI hang backstop)."""

from __future__ import annotations

from types import SimpleNamespace

from app.db.session_sync import build_sync_connect_args


def _settings(*, idle: int = 0, stmt: int = 0) -> SimpleNamespace:
    return SimpleNamespace(
        cip_sync_idle_in_transaction_timeout_ms=idle,
        cip_sync_statement_timeout_ms=stmt,
    )


def test_keepalives_and_prepare_threshold_always_present() -> None:
    args = build_sync_connect_args(_settings())
    assert args["keepalives"] == 1
    assert args["keepalives_idle"] == 30
    assert args["keepalives_interval"] == 10
    assert args["keepalives_count"] == 3
    assert args["prepare_threshold"] is None


def test_no_options_when_both_timeouts_disabled() -> None:
    args = build_sync_connect_args(_settings(idle=0, stmt=0))
    assert "options" not in args


def test_idle_timeout_emitted_in_options() -> None:
    args = build_sync_connect_args(_settings(idle=300_000))
    assert "-c idle_in_transaction_session_timeout=300000" in args["options"]
    assert "statement_timeout" not in args["options"]


def test_statement_timeout_emitted_in_options() -> None:
    args = build_sync_connect_args(_settings(stmt=120_000))
    assert "-c statement_timeout=120000" in args["options"]
    assert "idle_in_transaction_session_timeout" not in args["options"]


def test_both_timeouts_emitted_in_options() -> None:
    args = build_sync_connect_args(_settings(idle=300_000, stmt=120_000))
    assert "idle_in_transaction_session_timeout=300000" in args["options"]
    assert "statement_timeout=120000" in args["options"]


def test_negative_or_falsey_timeout_is_disabled() -> None:
    # getattr(... or 0) and the > 0 guard mean None / 0 / negatives never emit an option.
    args = build_sync_connect_args(SimpleNamespace(
        cip_sync_idle_in_transaction_timeout_ms=None,
        cip_sync_statement_timeout_ms=-1,
    ))
    assert "options" not in args


def test_settings_defaults_idle_on_statement_off() -> None:
    """Default policy: idle-in-transaction backstop on (5 min), statement_timeout off."""
    from app.core.config import Settings

    assert Settings.model_fields["cip_sync_idle_in_transaction_timeout_ms"].default == 300_000
    assert Settings.model_fields["cip_sync_statement_timeout_ms"].default == 0
