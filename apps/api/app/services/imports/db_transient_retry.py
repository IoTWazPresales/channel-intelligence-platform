"""Detect and retry transient remote-DB connection failures (Supabase pooler / DNS blips)."""

from __future__ import annotations

import asyncio
import socket
import time
from typing import Awaitable, Callable, TypeVar

from sqlalchemy.exc import DBAPIError, OperationalError

T = TypeVar("T")

_DEFAULT_ATTEMPTS = 3
_DEFAULT_BASE_DELAY_S = 1.5


def is_transient_db_error(exc: BaseException) -> bool:
    """True for errors that often succeed on immediate retry (not logic/constraint failures)."""
    if isinstance(exc, (socket.gaierror, ConnectionError, TimeoutError, OSError)):
        return True
    if isinstance(exc, (OperationalError, DBAPIError)):
        orig = getattr(exc, "orig", None)
        if orig is not None and is_transient_db_error(orig):
            return True
        msg = str(exc).lower()
        if any(
            token in msg
            for token in (
                "getaddrinfo",
                "connection refused",
                "connection reset",
                "server closed the connection",
                "ssl connection has been closed",
                "could not connect",
                "timeout",
                "broken pipe",
            )
        ):
            return True
    msg = str(exc).lower()
    return "getaddrinfo" in msg or "11002" in msg


async def retry_async_on_transient_db(
    operation: Callable[[], Awaitable[T]],
    *,
    attempts: int = _DEFAULT_ATTEMPTS,
    base_delay_s: float = _DEFAULT_BASE_DELAY_S,
) -> T:
    last_exc: BaseException | None = None
    for attempt in range(max(1, attempts)):
        try:
            return await operation()
        except Exception as exc:
            last_exc = exc
            if attempt >= attempts - 1 or not is_transient_db_error(exc):
                raise
            await asyncio.sleep(base_delay_s * (attempt + 1))
    assert last_exc is not None
    raise last_exc


def retry_sync_on_transient_db(
    operation: Callable[[], T],
    *,
    attempts: int = _DEFAULT_ATTEMPTS,
    base_delay_s: float = _DEFAULT_BASE_DELAY_S,
) -> T:
    """Sync variant for Celery bulk writers and checkpoint commits."""
    last_exc: BaseException | None = None
    for attempt in range(max(1, attempts)):
        try:
            return operation()
        except Exception as exc:
            last_exc = exc
            if attempt >= attempts - 1 or not is_transient_db_error(exc):
                raise
            time.sleep(base_delay_s * (attempt + 1))
    assert last_exc is not None
    raise last_exc
