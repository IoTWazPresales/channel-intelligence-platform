"""Transient DB error detection and retry."""

from __future__ import annotations

import asyncio
import socket
from unittest.mock import AsyncMock, patch

from app.services.imports.db_transient_retry import (
    is_readonly_db_error,
    is_transient_db_error,
    retry_async_on_transient_db,
    retry_sync_on_transient_db,
    retry_sync_session_on_transient_db,
)


def test_is_transient_db_error_gaierror() -> None:
    assert is_transient_db_error(socket.gaierror("getaddrinfo failed"))


def test_is_readonly_db_error_detects_postgres_message() -> None:
    assert is_readonly_db_error(Exception("cannot execute DELETE in a read-only transaction"))
    assert is_readonly_db_error(Exception("ReadOnlySqlTransaction"))
    assert not is_readonly_db_error(ValueError("constraint violation"))


def test_commit_session_with_transient_retry_reconnects_once_on_readonly() -> None:
    from unittest.mock import MagicMock, patch

    from app.services.imports.dsi_bulk_db_commit import commit_session_with_transient_retry

    session = MagicMock()
    calls = {"n": 0}

    def flaky_commit() -> None:
        calls["n"] += 1
        if calls["n"] < 2:
            raise Exception("cannot execute DELETE in a read-only transaction")

    session.commit.side_effect = flaky_commit
    with patch("app.services.imports.dsi_bulk_db_commit.time.sleep"):
        commit_session_with_transient_retry(session)
    assert calls["n"] == 2
    session.rollback.assert_called()
    session.connection().invalidate.assert_called()


def test_commit_session_with_transient_retry_readonly_raises_after_one_retry() -> None:
    from unittest.mock import MagicMock, patch

    from app.services.imports.dsi_bulk_db_commit import commit_session_with_transient_retry

    session = MagicMock()
    session.commit.side_effect = Exception("ReadOnlySqlTransaction")
    with patch("app.services.imports.dsi_bulk_db_commit.time.sleep"):
        try:
            commit_session_with_transient_retry(session)
            raise AssertionError("expected ReadOnlySqlTransaction to propagate")
        except Exception as exc:
            assert "ReadOnlySqlTransaction" in str(exc)
    assert session.commit.call_count == 2


def test_retry_sync_on_transient_db_retries_gaierror() -> None:
    calls = {"n": 0}

    def op() -> str:
        calls["n"] += 1
        if calls["n"] < 2:
            raise socket.gaierror("getaddrinfo failed")
        return "ok"

    with patch("app.services.imports.db_transient_retry.time.sleep"):
        result = retry_sync_on_transient_db(op, attempts=3, base_delay_s=0.01)
    assert result == "ok"
    assert calls["n"] == 2


def test_retry_async_succeeds_on_second_attempt() -> None:
    calls = {"n": 0}

    async def op() -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("getaddrinfo failed")
        return "ok"

    async def run() -> None:
        with patch("app.services.imports.db_transient_retry.asyncio.sleep", new=AsyncMock()):
            result = await retry_async_on_transient_db(op, attempts=3, base_delay_s=0.01)
        assert result == "ok"
        assert calls["n"] == 2

    asyncio.run(run())


def test_retry_sync_session_on_transient_db_rolls_back_and_retries() -> None:
    from unittest.mock import MagicMock

    from sqlalchemy.exc import OperationalError

    session = MagicMock()
    calls = {"n": 0}

    def op() -> str:
        calls["n"] += 1
        if calls["n"] < 2:
            raise OperationalError("SELECT", {}, Exception("server closed the connection unexpectedly"))
        return "ok"

    with patch("app.services.imports.db_transient_retry.time.sleep"):
        result = retry_sync_session_on_transient_db(session, op, attempts=3, base_delay_s=0.01)
    assert result == "ok"
    assert calls["n"] == 2
    session.rollback.assert_called_once()


def test_dsi_resolution_cache_read_retries_operational_error_mid_load() -> None:
    """Simulated dead-socket OperationalError during cache read recovers on retry."""
    from unittest.mock import MagicMock

    from sqlalchemy.exc import OperationalError

    from app.services.imports.distributor_sales_inventory import _dsi_session_read_with_transient_retry

    session = MagicMock()
    calls = {"n": 0}

    def load_customer_aliases() -> list[str]:
        calls["n"] += 1
        if calls["n"] < 2:
            raise OperationalError("SELECT", {}, Exception("server closed the connection unexpectedly"))
        return ["alias-row"]

    with patch("app.services.imports.db_transient_retry.time.sleep"):
        result = _dsi_session_read_with_transient_retry(session, load_customer_aliases)
    assert result == ["alias-row"]
    assert calls["n"] == 2
    session.rollback.assert_called_once()
