"""Tests for full distributor merge (name-similarity groups + PO consolidation)."""

from __future__ import annotations

import os
import secrets
from datetime import date
from unittest.mock import patch

import pytest
from sqlalchemy import select, text

from app.core.config import get_settings
from app.db.session_sync import SessionLocal
from app.models.dimensions import DimDistributor
from app.models.facts import FactInboundShipment
from app.models.purchase_order import PurchaseOrder
from app.models.shipment_evidence import ShipmentEvidenceLine
from app.services.commercial_planner.reference_bootstrap import ensure_commercial_planner_system_reference_data_sync
from app.services.distributor_duplicate_groups import build_duplicate_groups, list_distributor_duplicate_groups
from app.services.distributor_fk_discovery import discover_distributor_fk_columns, extra_distributor_ref_specs
from app.services.distributor_full_merge import (
    DistributorFullMergeError,
    confirm_distributor_full_merge_sync,
    preview_distributor_full_merge,
)
from app.services.distributor_full_repoint import DistributorFullRepointAbortError
from app.services.imports.dsi_customer_name_normalization import normalize_customer_name_for_similarity
from app.services.seed_demo import _seed_import_core


def _sqlalchemy_db_name(url: str) -> str:
    if not url or "://" not in url:
        return ""
    rest = url.split("://", 1)[1]
    if "/" not in rest:
        return ""
    db = rest.rsplit("/", 1)[-1]
    return db.split("?", 1)[0].strip()


def _require_disposable_or_opt_in_db() -> None:
    if os.environ.get("ALLOW_TESTS_ON_DEV_DB", "").strip() == "1":
        return
    settings = get_settings()
    if _sqlalchemy_db_name(settings.database_url) == "cip" or _sqlalchemy_db_name(settings.database_url_sync) == "cip":
        pytest.skip(
            "Refusing DB writes: set ALLOW_TESTS_ON_DEV_DB=1 or point DATABASE_URL_SYNC at a disposable database."
        )


def _migration_0063_applied(session) -> bool:
    row = session.execute(
        text(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'dim_distributor' AND column_name = 'merged_into_distributor_id'
            """
        )
    ).first()
    return row is not None


def _seed_dims(session) -> int:
    _seed_import_core(session)
    ensure_commercial_planner_system_reference_data_sync(session.connection())
    prod = session.scalar(select(DimDistributor).limit(1))
    assert prod is not None
    return int(prod.id)


def _seed_similar_pair(session, *, name_a: str, name_b: str) -> tuple[int, int, str]:
    key_a = normalize_customer_name_for_similarity(name_a)
    key_b = normalize_customer_name_for_similarity(name_b)
    assert key_a and key_a == key_b
    suffix = secrets.token_hex(4)
    d1 = DimDistributor(code=f"DIST-FULL-A-{suffix}", name=name_a, distributor_status="active")
    d2 = DimDistributor(code=f"DIST-FULL-B-{suffix}", name=name_b, distributor_status="unverified")
    session.add_all([d1, d2])
    session.commit()
    return int(d1.id), int(d2.id), key_a


def test_discover_distributor_fk_columns_matches_live_schema() -> None:
    """Read-only: discovered FK columns include priority surfaces (no writes)."""
    with SessionLocal() as session:
        db_name = session.scalar(text("SELECT current_database()"))
        if db_name == "cip":
            pytest.skip("discovery schema check runs on disposable DBs (cip_test), not live cip")

        discovered = discover_distributor_fk_columns(session)
        labels = {f"{t}.{c}" for t, c in discovered}

        pg_rows = session.execute(
            text(
                """
                SELECT c.relname AS table_name, a.attname AS column_name
                FROM pg_constraint con
                JOIN pg_class c ON c.oid = con.conrelid
                JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = ANY(con.conkey)
                JOIN pg_class ref ON ref.oid = con.confrelid
                WHERE con.contype = 'f'
                  AND ref.relname = 'dim_distributor'
                  AND array_length(con.confkey, 1) = 1
                  AND (
                    SELECT attname FROM pg_attribute
                    WHERE attrelid = con.confrelid AND attnum = con.confkey[1]
                  ) = 'id'
                ORDER BY 1, 2
                """
            )
        ).all()
        pg_labels = {f"{r[0]}.{r[1]}" for r in pg_rows if not (r[0] == "dim_distributor" and r[1] == "id")}

        assert pg_labels.issubset(labels)
        assert "purchase_order.distributor_id" in labels
        assert "fact_inbound_shipment.resolved_distributor_id" in labels
        assert "shipment_evidence_line.resolved_distributor_id" in labels
        assert "commercial_lineup_line.distributor_id" in labels

        extras = extra_distributor_ref_specs()
        assert any("import_entity_mapping_candidate" in f"{t}.{c}" for t, c, _w in extras)

        if _migration_0063_applied(session):
            assert "dim_distributor.merged_into_distributor_id" in labels


def test_fk_discovery_in_preview() -> None:
    _require_disposable_or_opt_in_db()
    with SessionLocal() as session:
        if not _migration_0063_applied(session):
            pytest.skip("migration 20260630_0063 not applied on test DB")
        _seed_dims(session)
        token = secrets.token_hex(4)
        d1, d2, key = _seed_similar_pair(
            session, name_a=f"Dist Alpha {token}", name_b=f"Dist Alpha {token} (Pty) Ltd"
        )
        preview = preview_distributor_full_merge(
            session,
            similarity_key=key,
            survivor_id=d1,
            audit_note="preview enumeration",
        )
    enum = preview["fk_enumeration"]
    cols = enum["pg_constraint_fk_columns"]
    assert any("fact_inbound_shipment.resolved_distributor_id" in c for c in cols)
    assert any("shipment_evidence_line.resolved_distributor_id" in c for c in cols)
    assert d2 in preview["loser_ids"]
    assert preview["loser_plans"][0].get("po_plans") is not None


def test_full_merge_repoints_resolved_distributor_on_facts_and_evidence() -> None:
    _require_disposable_or_opt_in_db()
    with SessionLocal() as session:
        if not _migration_0063_applied(session):
            pytest.skip("migration 20260630_0063 not applied on test DB")
        _seed_dims(session)
        token = secrets.token_hex(4)
        d1, d2, key = _seed_similar_pair(
            session, name_a=f"Merge Dist Alpha {token}", name_b=f"Merge Dist Alpha {token} Ltd"
        )
        job_id = session.scalar(text("SELECT id FROM import_job ORDER BY id LIMIT 1"))
        if job_id is None:
            pytest.skip("need import_job for shipment_evidence_line FK")

        sk_fact = f"test-dist-merge-fact-{secrets.token_hex(4)}"
        sk_ev = f"test-dist-merge-ev-{secrets.token_hex(4)}"
        fact = FactInboundShipment(
            source_key=sk_fact,
            fact_upsert_key=sk_fact,
            source_row_number=1,
            report_type="test",
            line_state="shipped",
            raw_source_row={},
            distributor_id=d1,
            resolved_distributor_id=d2,
            distributor_resolution_status="resolved",
            product_resolution_status="unresolved",
            status="scheduled",
        )
        ev = ShipmentEvidenceLine(
            import_job_id=int(job_id),
            source_row_number=99,
            report_type="test",
            line_state="shipped",
            source_key=sk_ev,
            raw_source_row={},
            product_resolution_status="resolved",
            distributor_resolution_status="resolved",
            resolved_distributor_id=d2,
        )
        session.add_all([fact, ev])
        session.commit()

        out = confirm_distributor_full_merge_sync(
            session,
            similarity_key=key,
            survivor_id=d1,
            audit_note="resolved_distributor repoint integration",
        )
        assert out["dry_run"] is False

        loser = session.get(DimDistributor, d2)
        assert loser is not None
        assert loser.merged_into_distributor_id == d1
        assert loser.distributor_status == "merged"

        refreshed_fact = session.scalar(select(FactInboundShipment).where(FactInboundShipment.source_key == sk_fact))
        assert refreshed_fact is not None
        assert refreshed_fact.resolved_distributor_id == d1

        refreshed_ev = session.scalar(select(ShipmentEvidenceLine).where(ShipmentEvidenceLine.source_key == sk_ev))
        assert refreshed_ev is not None
        assert refreshed_ev.resolved_distributor_id == d1


def test_po_consolidation_when_survivor_owns_same_norm() -> None:
    _require_disposable_or_opt_in_db()
    token = secrets.token_hex(6)
    norm = f"po-consolidate-{token}"
    keeper_dist_id: int | None = None
    loser_dist_id: int | None = None
    keeper_po_id: int | None = None
    try:
        with SessionLocal() as session:
            if not _migration_0063_applied(session):
                pytest.skip("migration 20260630_0063 not applied on test DB")
            if session.scalar(text("SELECT to_regclass('public.purchase_order')")) is None:
                pytest.skip("purchase_order not migrated")
            job_id = session.scalar(text("SELECT id FROM import_job ORDER BY id LIMIT 1"))
            if job_id is None:
                pytest.skip("need import_job")

            suffix = secrets.token_hex(4)
            name = f"PO Consolidate Dist {suffix}"
            d1 = DimDistributor(code=f"DIST-PO-K-{suffix}", name=name, distributor_status="active")
            d2 = DimDistributor(code=f"DIST-PO-L-{suffix}", name=f"{name} Ltd", distributor_status="unverified")
            session.add_all([d1, d2])
            session.flush()
            keeper_dist_id = int(d1.id)
            loser_dist_id = int(d2.id)
            key = normalize_customer_name_for_similarity(name)

            keeper_po = PurchaseOrder(
                po_number_raw=f"PO-K-{token}",
                po_number_norm=norm,
                distributor_id=keeper_dist_id,
                status="observed",
                source="shipment_materialized",
            )
            loser_po = PurchaseOrder(
                po_number_raw=f"PO-L-{token}",
                po_number_norm=norm,
                distributor_id=loser_dist_id,
                status="observed",
                source="shipment_materialized",
            )
            session.add_all([keeper_po, loser_po])
            session.flush()
            keeper_po_id = int(keeper_po.id)
            loser_po_id = int(loser_po.id)

            line = ShipmentEvidenceLine(
                import_job_id=int(job_id),
                source_row_number=1,
                report_type="test",
                line_state="shipped",
                source_key=f"sk-po-{token}",
                raw_source_row={},
                product_resolution_status="resolved",
                distributor_resolution_status="resolved",
                purchase_order_id=loser_po_id,
                resolved_distributor_id=loser_dist_id,
            )
            session.add(line)
            session.commit()

            preview = preview_distributor_full_merge(
                session,
                similarity_key=key,
                survivor_id=keeper_dist_id,
                audit_note="po consolidate preview",
            )
            po_plans = preview["loser_plans"][0]["po_plans"]
            assert any(p.get("action") == "consolidate_into_po" for p in po_plans)

            confirm_distributor_full_merge_sync(
                session,
                similarity_key=key,
                survivor_id=keeper_dist_id,
                audit_note="po consolidate confirm",
            )

            remaining_pos = list(
                session.scalars(select(PurchaseOrder).where(PurchaseOrder.po_number_norm == norm)).all()
            )
            assert len(remaining_pos) == 1
            assert int(remaining_pos[0].id) == keeper_po_id
            assert remaining_pos[0].distributor_id == keeper_dist_id

            refreshed_line = session.scalar(
                select(ShipmentEvidenceLine).where(ShipmentEvidenceLine.source_key == f"sk-po-{token}")
            )
            assert refreshed_line is not None
            assert refreshed_line.purchase_order_id == keeper_po_id
    finally:
        pass


def test_po_non_colliding_repoints_distributor_id_only() -> None:
    _require_disposable_or_opt_in_db()
    token = secrets.token_hex(6)
    norm_loser = f"po-unique-loser-{token}"
    try:
        with SessionLocal() as session:
            if not _migration_0063_applied(session):
                pytest.skip("migration 20260630_0063 not applied on test DB")
            suffix = secrets.token_hex(4)
            name = f"PO Repoint Dist {suffix}"
            d1 = DimDistributor(code=f"DIST-PO-RK-{suffix}", name=name, distributor_status="active")
            d2 = DimDistributor(code=f"DIST-PO-RL-{suffix}", name=f"{name} Ltd", distributor_status="unverified")
            session.add_all([d1, d2])
            session.flush()
            key = normalize_customer_name_for_similarity(name)

            loser_po = PurchaseOrder(
                po_number_raw=f"PO-UNIQ-{token}",
                po_number_norm=norm_loser,
                distributor_id=int(d2.id),
                status="observed",
                source="shipment_materialized",
            )
            session.add(loser_po)
            session.commit()
            loser_po_id = int(loser_po.id)

            preview = preview_distributor_full_merge(
                session,
                similarity_key=key,
                survivor_id=int(d1.id),
                audit_note="po repoint preview",
            )
            po_plans = preview["loser_plans"][0]["po_plans"]
            assert len(po_plans) == 1
            assert po_plans[0]["action"] == "repoint_distributor_id"

            confirm_distributor_full_merge_sync(
                session,
                similarity_key=key,
                survivor_id=int(d1.id),
                audit_note="po repoint confirm",
            )

            refreshed = session.get(PurchaseOrder, loser_po_id)
            assert refreshed is not None
            assert refreshed.distributor_id == int(d1.id)
    finally:
        pass


def test_incomplete_repoint_aborts_whole_merge() -> None:
    _require_disposable_or_opt_in_db()
    with SessionLocal() as session:
        if not _migration_0063_applied(session):
            pytest.skip("migration 20260630_0063 not applied on test DB")
        _seed_dims(session)
        token = secrets.token_hex(4)
        d1, d2, key = _seed_similar_pair(
            session, name_a=f"Abort Dist {token}", name_b=f"Abort Dist {token} Ltd"
        )

        with patch(
            "app.services.distributor_full_merge.repoint_distributor_footprint_full",
            side_effect=DistributorFullRepointAbortError("simulated incomplete repoint", loser_id=d2, table="fact_x"),
        ):
            with pytest.raises(DistributorFullMergeError, match="simulated"):
                confirm_distributor_full_merge_sync(
                    session,
                    similarity_key=key,
                    survivor_id=d1,
                    audit_note="should abort",
                )

        loser = session.get(DimDistributor, d2)
        assert loser is not None
        assert loser.merged_into_distributor_id is None
        assert loser.distributor_status != "merged"


def test_tombstoned_distributors_excluded_from_duplicate_listing() -> None:
    _require_disposable_or_opt_in_db()
    import asyncio

    with SessionLocal() as session:
        if not _migration_0063_applied(session):
            pytest.skip("migration 20260630_0063 not applied on test DB")
        suffix = secrets.token_hex(4)
        name = f"Tombstone Exclude {suffix}"
        survivor = DimDistributor(code=f"DIST-T-S-{suffix}", name=name, distributor_status="active")
        loser = DimDistributor(
            code=f"DIST-T-L-{suffix}",
            name=f"{name} Ltd",
            distributor_status="merged",
            merged_into_distributor_id=None,
        )
        session.add_all([survivor, loser])
        session.flush()
        loser.merged_into_distributor_id = int(survivor.id)
        session.commit()
        loser_id = int(loser.id)
        survivor_id = int(survivor.id)

        rows = session.execute(
            select(
                DimDistributor.id,
                DimDistributor.code,
                DimDistributor.name,
                DimDistributor.distributor_status,
                DimDistributor.created_at,
            ).where(DimDistributor.merged_into_distributor_id.is_(None))
        ).all()
        from app.services.distributor_duplicate_groups import _DistributorRow

        distributors = [
            _DistributorRow(
                id=int(r.id),
                code=str(r.code),
                name=str(r.name),
                distributor_status=str(r.distributor_status or "active"),
                created_at=r.created_at,
            )
            for r in rows
        ]
        groups = build_duplicate_groups(distributors)
        key = normalize_customer_name_for_similarity(name)
        matching = [g for g in groups if g["similarity_key"] == key]
        if matching:
            member_ids = {m.id for m in matching[0]["members"]}
            assert int(loser_id) not in member_ids

    async def _list():
        from app.db.session import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            return await list_distributor_duplicate_groups(db, page=1, page_size=200)

    listed = asyncio.run(_list())
    for item in listed.get("items") or []:
        for m in item.get("members") or []:
            assert m.get("id") != loser_id


def test_rejects_unassigned_as_survivor() -> None:
    _require_disposable_or_opt_in_db()
    from app.services.commercial_planner.unassigned_distributor import UNASSIGNED_DISTRIBUTOR_CODE
    from app.services.distributor_full_merge import _assert_survivor_valid

    with SessionLocal() as session:
        if not _migration_0063_applied(session):
            pytest.skip("migration 20260630_0063 not applied on test DB")
        unassigned = session.scalar(
            select(DimDistributor).where(DimDistributor.code == UNASSIGNED_DISTRIBUTOR_CODE)
        )
        assert unassigned is not None
        with pytest.raises(DistributorFullMergeError, match="UNASSIGNED"):
            _assert_survivor_valid(
                session,
                survivor_id=int(unassigned.id),
                member_ids=[int(unassigned.id), int(unassigned.id) + 99999],
            )
