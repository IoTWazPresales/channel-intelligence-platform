"""Delete winner restores superseded children."""

from __future__ import annotations

import secrets

import pytest
from sqlalchemy import select

from app.db.session_sync import SessionLocal
from app.models.commercial_lineup import CommercialLineupCase
from app.services.commercial_planner.lineup_case_supersession import (
    delete_lineup_case_restoring_children,
    find_orphan_superseded_cases,
    restore_superseded_cases,
)


def _require_cip(db) -> None:
    from sqlalchemy import text

    name = db.scalar(text("SELECT current_database()"))
    if name != "cip":
        pytest.skip(f"integration test requires cip, got {name!r}")


@pytest.mark.integration
def test_delete_winner_restores_superseded_children():
    tok = secrets.token_hex(4)
    with SessionLocal() as db:
        _require_cip(db)
        winner = CommercialLineupCase(
            file_name=f"winner_{tok}.xlsx",
            period_label="26Q1",
            commercial_status="draft_imported",
            import_intent="historical_lineup_backfill",
            source_context="test",
        )
        loser = CommercialLineupCase(
            file_name=f"loser_{tok}.xlsx",
            period_label="26Q1",
            commercial_status="superseded",
            import_intent="historical_lineup_backfill",
            source_context="test",
        )
        db.add(winner)
        db.flush()
        loser.superseded_by_case_id = int(winner.id)
        db.add(loser)
        db.commit()
        winner_id = int(winner.id)
        loser_id = int(loser.id)

    try:
        with SessionLocal() as db:
            _require_cip(db)
            winner = db.get(CommercialLineupCase, winner_id)
            assert winner is not None
            report = delete_lineup_case_restoring_children(db, winner)
            db.commit()
            assert report["restored_child_count"] == 1
            assert report["restored_children"][0]["id"] == loser_id

            assert db.get(CommercialLineupCase, winner_id) is None
            restored = db.get(CommercialLineupCase, loser_id)
            assert restored is not None
            assert restored.commercial_status == "draft_imported"
            assert restored.superseded_by_case_id is None
    finally:
        with SessionLocal() as db:
            for cid in (winner_id, loser_id):
                row = db.get(CommercialLineupCase, cid)
                if row:
                    db.delete(row)
            db.commit()


@pytest.mark.integration
def test_restore_orphan_superseded_cases():
    tok = secrets.token_hex(4)
    with SessionLocal() as db:
        _require_cip(db)
        orphan = CommercialLineupCase(
            file_name=f"orphan_{tok}.xlsx",
            period_label="26Q1",
            commercial_status="superseded",
            import_intent="historical_lineup_backfill",
            source_context="test",
            superseded_by_case_id=None,
        )
        db.add(orphan)
        db.commit()
        orphan_id = int(orphan.id)

    try:
        with SessionLocal() as db:
            _require_cip(db)
            orphans = [c for c in find_orphan_superseded_cases(db) if int(c.id) == orphan_id]
            assert orphans
            restored = restore_superseded_cases(db, orphans)
            db.commit()
            assert restored[0]["after_commercial_status"] == "draft_imported"
            row = db.get(CommercialLineupCase, orphan_id)
            assert row is not None
            assert row.commercial_status == "draft_imported"
    finally:
        with SessionLocal() as db:
            row = db.get(CommercialLineupCase, orphan_id)
            if row:
                db.delete(row)
            db.commit()
