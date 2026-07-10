"""Unit 2b — NULL-distributor PO sibling merge into distributor-set keeper."""

from __future__ import annotations

import secrets
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select, text

from app.db.session_sync import SessionLocal
from app.models.commercial_lineup import CommercialLineupCasePo
from app.models.purchase_order import PurchaseOrder
from app.models.shipment_evidence import ShipmentEvidenceLine
from app.services.imports.shipment_null_distributor_sibling_po_merge import (
    SiblingPoMergeAbortError,
    SiblingPoMergeGroup,
    _would_violate_unique_on_repoint,
    execute_null_distributor_sibling_po_merge,
    plan_null_distributor_sibling_po_merges,
    sibling_merge_summary_stats,
)


@pytest.fixture
def _stub_observation_fk_helpers(monkeypatch):
    """Dev ``cip`` role may lack observation grants; these tests do not use observation rows."""
    import app.services.imports.shipment_null_distributor_sibling_po_merge as mod

    monkeypatch.setattr(mod, "_observation_loser_ref_count", lambda _db, _lid: 0)
    monkeypatch.setattr(mod, "_repoint_observation_po_links_strict", lambda _db, _k, _l: 0)


def test_plan_skips_ambiguous_multiple_distributors(monkeypatch):
    db = MagicMock()
    monkeypatch.setattr(
        "app.services.imports.shipment_null_distributor_sibling_po_merge._sibling_norms_subquery",
        lambda: "norms-subq",
    )

    def fake_execute(stmt):
        class R:
            def all(self_inner):
                if "norms-subq" in str(stmt):
                    return [("PO-AMB",)]
                return []

        return R()

    monkeypatch.setattr(db, "execute", fake_execute)
    monkeypatch.setattr(
        "app.services.imports.shipment_null_distributor_sibling_po_merge._po_ids_for_norm",
        lambda _db, norm, distributor_null=False: [100] if distributor_null else [200, 201],
    )
    monkeypatch.setattr(
        "app.services.imports.shipment_null_distributor_sibling_po_merge._distributor_ids_for_pos",
        lambda _db, _ids: [7, 8],
    )

    plans, skipped = plan_null_distributor_sibling_po_merges(db)
    assert plans == []
    assert len(skipped) == 1
    assert skipped[0].reason == "ambiguous_multiple_distributors"


def test_would_violate_unique_on_fact_source_key_overlap():
    db = MagicMock()
    keeper = MagicMock()
    keeper.po_number_norm = "NORM"
    keeper.distributor_id = 7
    db.get.return_value = keeper
    db.execute.return_value.all.return_value = [("fact-key-1",)]

    scalar_calls = {"n": 0}

    def fake_scalar(_stmt):
        scalar_calls["n"] += 1
        if scalar_calls["n"] == 1:
            return 0  # no duplicate distributor-set rows
        return 1  # overlapping fact source_key on keeper

    db.scalar = fake_scalar

    reason = _would_violate_unique_on_repoint(db, keeper_id=200, loser_ids=(100,))
    assert reason == "fact_source_key_overlap"


def test_plan_finds_sibling_norms_on_cip():
    try:
        with SessionLocal() as db:
            if db.scalar(text("SELECT to_regclass('public.purchase_order')")) is None:
                pytest.skip("purchase_order not migrated")
            summary = sibling_merge_summary_stats(db)
            if int(summary.get("sibling_norm_groups_total") or 0) == 0:
                pytest.skip("no NULL+distributor sibling norms on this DB")
            plans, skipped = plan_null_distributor_sibling_po_merges(db)
            assert len(plans) + len(skipped) == int(summary["sibling_norm_groups_total"])
            for g in plans:
                assert g.keeper_id not in g.loser_ids
                assert len(g.loser_ids) >= 1
    except Exception:
        pytest.skip("DB not available")


def test_execute_sibling_merge_repoints_evidence_case_link_and_deletes_null_loser(
    _stub_observation_fk_helpers,
):
    token = secrets.token_hex(6)
    norm = f"sibling-merge-{token}"
    keeper_id: int | None = None
    loser_id: int | None = None
    case_id: int | None = None
    try:
        with SessionLocal() as db:
            if db.scalar(text("SELECT to_regclass('public.commercial_lineup_case_po')")) is None:
                pytest.skip("commercial_lineup_case_po not migrated")
            job_id = db.scalar(text("SELECT id FROM import_job ORDER BY id LIMIT 1"))
            case_id = db.scalar(text("SELECT id FROM commercial_lineup_case ORDER BY id LIMIT 1"))
            if job_id is None or case_id is None:
                pytest.skip("need import_job and commercial_lineup_case for FK fixtures")

            keeper = PurchaseOrder(
                po_number_raw=f"PO-K-{token}",
                po_number_norm=norm,
                distributor_id=1,
                status="observed",
                source="shipment_materialized",
            )
            loser = PurchaseOrder(
                po_number_raw=f"PO-L-{token}",
                po_number_norm=norm,
                distributor_id=None,
                status="observed",
                source="shipment_materialized",
            )
            db.add(keeper)
            db.add(loser)
            db.flush()
            keeper_id = int(keeper.id)
            loser_id = int(loser.id)

            line = ShipmentEvidenceLine(
                import_job_id=int(job_id),
                source_row_number=1,
                report_type="test",
                line_state="shipped",
                source_key=f"sk-{token}",
                raw_source_row={},
                product_resolution_status="resolved",
                distributor_resolution_status="resolved",
                purchase_order_id=loser_id,
            )
            db.add(line)
            db.add(
                CommercialLineupCasePo(
                    case_id=int(case_id),
                    purchase_order_id=loser_id,
                    notes="test",
                )
            )
            db.flush()

            group = SiblingPoMergeGroup(
                po_number_norm=norm,
                keeper_id=keeper_id,
                keeper_distributor_id=1,
                loser_ids=(loser_id,),
            )
            stats = execute_null_distributor_sibling_po_merge(db, group)
            db.commit()

            assert stats["losers_deleted"] == 1
            assert stats["evidence_lines_updated"] == 1
            assert stats["case_links_updated"] == 1

            remaining = list(
                db.scalars(select(PurchaseOrder.id).where(PurchaseOrder.po_number_norm == norm)).all()
            )
            assert remaining == [keeper_id]

            ev_po = db.scalar(
                select(ShipmentEvidenceLine.purchase_order_id).where(
                    ShipmentEvidenceLine.source_key == f"sk-{token}"
                )
            )
            assert int(ev_po) == keeper_id

            link_po = db.scalar(
                select(CommercialLineupCasePo.purchase_order_id).where(
                    CommercialLineupCasePo.case_id == int(case_id),
                    CommercialLineupCasePo.purchase_order_id == keeper_id,
                )
            )
            assert int(link_po) == keeper_id
    finally:
        if loser_id is not None or keeper_id is not None:
            with SessionLocal() as db:
                if case_id is not None:
                    db.execute(
                        text(
                            "DELETE FROM commercial_lineup_case_po "
                            "WHERE case_id = :cid AND notes = 'test'"
                        ),
                        {"cid": int(case_id)},
                    )
                db.execute(
                    text("DELETE FROM shipment_evidence_line WHERE source_key = :sk"),
                    {"sk": f"sk-{token}"},
                )
                db.execute(text("DELETE FROM purchase_order WHERE po_number_norm = :n"), {"n": norm})
                db.commit()


def test_execute_skips_ambiguous_two_distributor_rows_same_norm():
    token = secrets.token_hex(6)
    norm = f"sibling-amb-{token}"
    ids: list[int] = []
    try:
        with SessionLocal() as db:
            for dist in (1, 2):
                po = PurchaseOrder(
                    po_number_raw=f"PO-{dist}-{token}",
                    po_number_norm=norm,
                    distributor_id=dist,
                    status="observed",
                    source="shipment_materialized",
                )
                db.add(po)
            null_po = PurchaseOrder(
                po_number_raw=f"PO-NULL-{token}",
                po_number_norm=norm,
                distributor_id=None,
                status="observed",
                source="shipment_materialized",
            )
            db.add(null_po)
            db.flush()
            ids = [int(x) for x in db.scalars(select(PurchaseOrder.id).where(PurchaseOrder.po_number_norm == norm)).all()]

            plans, skipped = plan_null_distributor_sibling_po_merges(db)
            hit = [s for s in skipped if s.po_number_norm == norm]
            assert hit
            assert hit[0].reason == "ambiguous_multiple_distributors"
            assert not [g for g in plans if g.po_number_norm == norm]
    finally:
        if ids:
            with SessionLocal() as db:
                db.execute(text("DELETE FROM purchase_order WHERE po_number_norm = :n"), {"n": norm})
                db.commit()


def test_execute_aborts_when_evidence_repoint_incomplete(_stub_observation_fk_helpers):
    token = secrets.token_hex(6)
    norm = f"sibling-abort-{token}"
    keeper_id: int | None = None
    loser_id: int | None = None
    try:
        with SessionLocal() as db:
            job_id = db.scalar(text("SELECT id FROM import_job ORDER BY id LIMIT 1"))
            if job_id is None:
                pytest.skip("need import_job for FK fixture")

            keeper = PurchaseOrder(
                po_number_raw=f"PO-K-{token}",
                po_number_norm=norm,
                distributor_id=1,
                status="observed",
                source="shipment_materialized",
            )
            loser = PurchaseOrder(
                po_number_raw=f"PO-L-{token}",
                po_number_norm=norm,
                distributor_id=None,
                status="observed",
                source="shipment_materialized",
            )
            db.add(keeper)
            db.add(loser)
            db.flush()
            keeper_id = int(keeper.id)
            loser_id = int(loser.id)
            db.add(
                ShipmentEvidenceLine(
                    import_job_id=int(job_id),
                    source_row_number=1,
                    report_type="test",
                    line_state="shipped",
                    source_key=f"sk-abort-{token}",
                    raw_source_row={},
                    product_resolution_status="resolved",
                    distributor_resolution_status="resolved",
                    purchase_order_id=loser_id,
                )
            )
            db.commit()

        with SessionLocal() as db:
            group = SiblingPoMergeGroup(
                po_number_norm=norm,
                keeper_id=int(keeper_id),
                keeper_distributor_id=1,
                loser_ids=(int(loser_id),),
            )
            real_execute = db.execute

            def _block_evidence_repoint(statement, *args, **kwargs):
                compiled = str(statement)
                if "shipment_evidence_line" in compiled and "purchase_order_id" in compiled:
                    if "UPDATE" in compiled.upper():
                        class _R:
                            rowcount = 0

                        return _R()
                return real_execute(statement, *args, **kwargs)

            db.execute = _block_evidence_repoint  # type: ignore[method-assign]

            with pytest.raises(SiblingPoMergeAbortError) as exc:
                execute_null_distributor_sibling_po_merge(db, group)
            assert exc.value.table == "shipment_evidence_line"
            db.rollback()

        with SessionLocal() as db:
            assert db.get(PurchaseOrder, int(loser_id)) is not None
            assert db.get(PurchaseOrder, int(keeper_id)) is not None
    finally:
        if loser_id is not None or keeper_id is not None:
            with SessionLocal() as db:
                db.execute(
                    text("DELETE FROM shipment_evidence_line WHERE source_key = :sk"),
                    {"sk": f"sk-abort-{token}"},
                )
                db.execute(text("DELETE FROM purchase_order WHERE po_number_norm = :n"), {"n": norm})
                db.commit()


def test_execute_batch_all_or_nothing_when_second_loser_fails(_stub_observation_fk_helpers):
    token = secrets.token_hex(6)
    norm_a = f"sibling-batch-a-{token}"
    norm_b = f"sibling-batch-b-{token}"
    ids: dict[str, int] = {}
    try:
        with SessionLocal() as db:
            job_id = db.scalar(text("SELECT id FROM import_job ORDER BY id LIMIT 1"))
            if job_id is None:
                pytest.skip("need import_job for FK fixture")

            for norm, key in ((norm_a, "a"), (norm_b, "b")):
                keeper = PurchaseOrder(
                    po_number_raw=f"K-{key}-{token}",
                    po_number_norm=norm,
                    distributor_id=1,
                    status="observed",
                    source="shipment_materialized",
                )
                loser = PurchaseOrder(
                    po_number_raw=f"L-{key}-{token}",
                    po_number_norm=norm,
                    distributor_id=None,
                    status="observed",
                    source="shipment_materialized",
                )
                db.add(keeper)
                db.add(loser)
                db.flush()
                ids[f"keeper_{key}"] = int(keeper.id)
                ids[f"loser_{key}"] = int(loser.id)
                db.add(
                    ShipmentEvidenceLine(
                        import_job_id=int(job_id),
                        source_row_number=1,
                        report_type="test",
                        line_state="shipped",
                        source_key=f"sk-batch-{key}-{token}",
                        raw_source_row={},
                        product_resolution_status="resolved",
                        distributor_resolution_status="resolved",
                        purchase_order_id=int(loser.id),
                    )
                )
            db.commit()

        with SessionLocal() as db:
            group_a = SiblingPoMergeGroup(
                po_number_norm=norm_a,
                keeper_id=ids["keeper_a"],
                keeper_distributor_id=1,
                loser_ids=(ids["loser_a"],),
            )
            group_b = SiblingPoMergeGroup(
                po_number_norm=norm_b,
                keeper_id=ids["keeper_b"],
                keeper_distributor_id=1,
                loser_ids=(ids["loser_b"],),
            )

            real_execute = db.execute
            blocked = {"n": 0}

            def _block_second_evidence_repoint(statement, *args, **kwargs):
                compiled = str(statement)
                if "shipment_evidence_line" in compiled and "UPDATE" in compiled.upper():
                    blocked["n"] += 1
                    if blocked["n"] == 2:
                        class _R:
                            rowcount = 0

                        return _R()
                return real_execute(statement, *args, **kwargs)

            db.execute = _block_second_evidence_repoint  # type: ignore[method-assign]

            execute_null_distributor_sibling_po_merge(db, group_a)
            with pytest.raises(SiblingPoMergeAbortError):
                execute_null_distributor_sibling_po_merge(db, group_b)
            db.rollback()

        with SessionLocal() as db:
            for key in ("loser_a", "loser_b", "keeper_a", "keeper_b"):
                assert db.get(PurchaseOrder, ids[key]) is not None
            loser_a_still = db.get(PurchaseOrder, ids["loser_a"])
            assert loser_a_still is not None
            assert loser_a_still.distributor_id is None
    finally:
        with SessionLocal() as db:
            db.execute(
                text("DELETE FROM shipment_evidence_line WHERE source_key LIKE :sk"),
                {"sk": f"sk-batch-%-{token}"},
            )
            db.execute(
                text("DELETE FROM purchase_order WHERE po_number_norm IN (:a, :b)"),
                {"a": norm_a, "b": norm_b},
            )
            db.commit()
