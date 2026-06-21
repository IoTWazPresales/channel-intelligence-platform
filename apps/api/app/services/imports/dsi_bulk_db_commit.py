"""Transient-retry wrapper for DSI bulk writer commits (defense-in-depth on remote DB)."""

from __future__ import annotations

import time
from typing import Callable, TypeVar

from sqlalchemy.orm import Session

from app.services.imports.db_transient_retry import (
    _DEFAULT_ATTEMPTS,
    _DEFAULT_BASE_DELAY_S,
    invalidate_sync_session,
    is_readonly_db_error,
    is_transient_db_error,
    retry_sync_on_transient_db,
    retry_sync_session_on_transient_db,
)

T = TypeVar("T")


def commit_session_with_transient_retry(session: Session) -> None:
    """Commit once; retry transient errors or one read-only reconnect at chunk boundaries."""
    readonly_retried = False
    transient_attempts = 0
    while True:
        try:
            session.commit()
            return
        except Exception as exc:
            if is_readonly_db_error(exc):
                if readonly_retried:
                    raise
                readonly_retried = True
                invalidate_sync_session(session)
                time.sleep(_DEFAULT_BASE_DELAY_S)
                continue
            if is_transient_db_error(exc):
                transient_attempts += 1
                if transient_attempts >= _DEFAULT_ATTEMPTS:
                    raise
                session.rollback()
                time.sleep(_DEFAULT_BASE_DELAY_S * transient_attempts)
                continue
            raise


def read_session_with_transient_retry(session: Session, operation: Callable[[], T]) -> T:
    """Read once; rollback and retry on transient connection/pooler errors."""
    return retry_sync_session_on_transient_db(session, operation)
