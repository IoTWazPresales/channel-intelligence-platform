"""CST bulk ignore must load: its module imported a SessionLocal that app.db.session never had, so
every bulk ignore answered 500 (Internal Server Error) before reaching the database."""

from __future__ import annotations

from sqlalchemy.orm import Session


def test_the_bulk_ignore_module_loads_and_uses_a_sync_session() -> None:
    from app.services.imports import cst_steward_bulk_enqueue as mod

    with mod.SessionLocal() as db:
        assert isinstance(db, Session)
