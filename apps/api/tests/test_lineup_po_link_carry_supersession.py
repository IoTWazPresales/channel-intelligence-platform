"""PO-link carry on soft-supersession (BACKLOG-118). Requires disposable test DB — not cip."""

from __future__ import annotations

import os
import secrets
from urllib.parse import urlparse

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.models.commercial_lineup import CommercialLineupCase, CommercialLineupCasePo
from app.models.purchase_order import PurchaseOrder
from app.services.commercial_planner.lineup_case_supersession import (
    carry_case_po_links_on_supersession,
    soft_supersede_lineup_case,
)


def _db_name(url: str) -> str:
    path = urlparse(url.replace("+psycopg", "").replace("+asyncpg", "")).path
    return path.lstrip("/").split("?")[0]


@pytest.fixture(scope="module")
def carry_session():
    sync = os.environ.get("DATABASE_URL_SYNC", "")
    migrate = os.environ.get("DATABASE_URL_SYNC_MIGRATE", sync)
    print("DATABASE_URL_SYNC ->", sync)
    print("DATABASE_URL_SYNC_MIGRATE ->", migrate)
    if not sync:
        pytest.skip("DATABASE_URL_SYNC required")
    name = _db_name(sync)
    migrate_name = _db_name(migrate)
    print("resolved current targets:", name, migrate_name)
    if name == "cip" or migrate_name == "cip":
        pytest.skip("refusing cip — point BOTH URLs at a disposable DB")
    engine = create_engine(sync, pool_pre_ping=True)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with Session() as db:
        dbn = db.execute(text("SELECT current_database()")).scalar()
        print("current_database()", dbn)
        if dbn == "cip":
            pytest.skip("refusing cip")
        yield db


def test_soft_supersede_copies_links_idempotent(carry_session):
    db = carry_session
    tok = secrets.token_hex(3)
    loser = CommercialLineupCase(
        file_name=f"t_loser_{tok}.xlsx",
        period_label="2099 Q2",
        commercial_status="po_issued",
        import_intent="historical_lineup_backfill",
        source_context="test_po_carry",
    )
    winner = CommercialLineupCase(
        file_name=f"t_winner_{tok}.xlsx",
        period_label="2099 Q2",
        commercial_status="draft_imported",
        import_intent="historical_lineup_backfill",
        source_context="test_po_carry",
    )
    db.add_all([loser, winner])
    db.flush()
    pos = []
    for s in ("1", "2", "3"):
        po = PurchaseOrder(po_number_raw=f"T{tok}{s}", po_number_norm=f"T{tok}{s}")
        db.add(po)
        db.flush()
        pos.append(po)
        db.add(CommercialLineupCasePo(case_id=int(loser.id), purchase_order_id=int(po.id)))
    db.flush()

    r1 = soft_supersede_lineup_case(db, loser_case_id=int(loser.id), winner_case_id=int(winner.id))
    db.flush()
    assert r1["carry"]["carried"] == 3
    assert (
        db.execute(
            text("SELECT count(*) FROM commercial_lineup_case_po WHERE case_id=:c"),
            {"c": int(winner.id)},
        ).scalar()
        == 3
    )
    assert (
        db.execute(
            text("SELECT count(*) FROM commercial_lineup_case_po WHERE case_id=:c"),
            {"c": int(loser.id)},
        ).scalar()
        == 3
    )

    r2 = soft_supersede_lineup_case(db, loser_case_id=int(loser.id), winner_case_id=int(winner.id))
    db.flush()
    assert r2["already_superseded"] is True
    assert r2["carry"]["carried"] == 0
    assert r2["carry"]["skipped_existing"] == 3
    db.rollback()  # leave no residue on shared disposable DB


def test_carry_union_when_winner_has_overlap(carry_session):
    db = carry_session
    tok = secrets.token_hex(3)
    loser = CommercialLineupCase(
        file_name=f"u_loser_{tok}.xlsx",
        period_label="2099 Q3",
        commercial_status="po_issued",
        import_intent="historical_lineup_backfill",
        source_context="test_po_carry",
    )
    winner = CommercialLineupCase(
        file_name=f"u_winner_{tok}.xlsx",
        period_label="2099 Q3",
        commercial_status="draft_imported",
        import_intent="historical_lineup_backfill",
        source_context="test_po_carry",
    )
    db.add_all([loser, winner])
    db.flush()
    shared = PurchaseOrder(po_number_raw=f"U{tok}S", po_number_norm=f"U{tok}S")
    only_l = PurchaseOrder(po_number_raw=f"U{tok}L", po_number_norm=f"U{tok}L")
    only_w = PurchaseOrder(po_number_raw=f"U{tok}W", po_number_norm=f"U{tok}W")
    db.add_all([shared, only_l, only_w])
    db.flush()
    db.add(CommercialLineupCasePo(case_id=int(loser.id), purchase_order_id=int(shared.id)))
    db.add(CommercialLineupCasePo(case_id=int(loser.id), purchase_order_id=int(only_l.id)))
    db.add(CommercialLineupCasePo(case_id=int(winner.id), purchase_order_id=int(shared.id)))
    db.add(CommercialLineupCasePo(case_id=int(winner.id), purchase_order_id=int(only_w.id)))
    db.flush()

    carry_case_po_links_on_supersession(
        db, loser_case_id=int(loser.id), winner_case_id=int(winner.id)
    )
    db.flush()
    norms = set(
        db.execute(
            text(
                """
                SELECT po.po_number_norm FROM commercial_lineup_case_po cl
                JOIN purchase_order po ON po.id = cl.purchase_order_id
                WHERE cl.case_id = :c
                """
            ),
            {"c": int(winner.id)},
        ).scalars().all()
    )
    assert norms == {shared.po_number_norm, only_l.po_number_norm, only_w.po_number_norm}
    db.rollback()
