"""Transient DB error detection and retry."""

from __future__ import annotations

import asyncio
import socket
from unittest.mock import AsyncMock, patch

from app.services.imports.db_transient_retry import (
    is_transient_db_error,
    retry_async_on_transient_db,
    retry_sync_on_transient_db,
)


def test_is_transient_db_error_gaierror() -> None:
    assert is_transient_db_error(socket.gaierror("getaddrinfo failed"))


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
