"""Transient-retry wrapper for DSI bulk writer commits (defense-in-depth on remote DB)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.imports.db_transient_retry import retry_sync_on_transient_db


def commit_session_with_transient_retry(session: Session) -> None:
    """Commit once; retry only on transient connection/pooler errors."""
    retry_sync_on_transient_db(lambda: session.commit())
