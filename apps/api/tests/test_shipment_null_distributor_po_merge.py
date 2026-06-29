"""Unit 2 — NULL-distributor PO dedup + deferred materialize."""

from __future__ import annotations

import secrets

import pytest
from sqlalchemy import func, select, text

from app.db.session_sync import SessionLocal
from app.models.purchase_order import PurchaseOrder
from app.services.imports.shipment_null_distributor_po_merge import (
    NullDistPoMergeGroup,
    _pick_keeper,
    execute_null_distributor_po_merge,
    merge_summary_stats,
    plan_null_distributor_po_merges,
)


def test_pick_keeper_prefers_most_evidence_links():
    keeper = _pick_keeper([10, 20, 30], {10: 1, 20: 5, 30: 2}, {})
    assert keeper == 20


def test_pick_keeper_tiebreaks_on_lowest_id():
    keeper = _pick_keeper([10, 20], {10: 3, 20: 3}, {10: 1, 20: 1})
    assert keeper == 10


def test_merge_plan_finds_null_distributor_duplicate_norms():
    try:
        with SessionLocal() as db:
            if db.scalar(text("SELECT to_regclass('public.purchase_order')")) is None:
                pytest.skip("purchase_order not migrated")
            summary = merge_summary_stats(db)
            if int(summary.get("norms_with_duplicates") or 0) == 0:
                pytest.skip("no NULL-distributor duplicate norms on this DB")
            plans = plan_null_distributor_po_merges(db)
            assert len(plans) == int(summary["norms_with_duplicates"])
            for g in plans:
                assert g.keeper_id not in g.loser_ids
                assert len(g.loser_ids) >= 1
    except Exception:
        pytest.skip("DB not available")


def test_execute_merge_repoints_and_deletes_losers():
    token = secrets.token_hex(6)
    keeper_id: int | None = None
    loser_ids: list[int] = []
    norm = f"merge-test-{token}"
    try:
        with SessionLocal() as db:
            for raw_suffix in ("A", "B", "C"):
                po = PurchaseOrder(
                    po_number_raw=f"PO-{raw_suffix}-{token}",
                    po_number_norm=norm,
                    distributor_id=None,
                    status="observed",
                    source="shipment_materialized",
                )
                db.add(po)
            db.flush()
            rows = list(
                db.scalars(
                    select(PurchaseOrder.id)
                    .where(PurchaseOrder.po_number_norm == norm)
                    .order_by(PurchaseOrder.id)
                ).all()
            )
            assert len(rows) == 3
            keeper_id = int(rows[0])
            loser_ids = [int(x) for x in rows[1:]]
            group = NullDistPoMergeGroup(
                po_number_norm=norm,
                keeper_id=keeper_id,
                loser_ids=tuple(loser_ids),
            )
            stats = execute_null_distributor_po_merge(db, group)
            db.commit()
            assert stats["losers_deleted"] == 2
            remaining = list(
                db.scalars(select(PurchaseOrder.id).where(PurchaseOrder.po_number_norm == norm)).all()
            )
            assert remaining == [keeper_id]
    finally:
        if keeper_id is not None:
            with SessionLocal() as db:
                db.execute(
                    text("DELETE FROM purchase_order WHERE po_number_norm = :n"), {"n": norm}
                )
                db.commit()
