"""PO-less shipped facts a newer job re-wrote under a PO-inclusive key are soft-retired (closed_superseded).

cip_test only, one rolled-back transaction per test. The rule, the load-time call and the pointer refresh.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

import pytest
from sqlalchemy import select, text

from app.db.session_sync import SessionLocal
from app.models.facts import FactInboundShipment
from app.models.iam import Tenant
from app.models.ingestion import ImportJob, ImportTemplate, SourceDefinition
from app.models.purchase_order import PurchaseOrder
from app.services.imports.shipment_open_book import exclude_closed_inbound
from app.services.imports.shipment_shipped_fact_identity_twin_merge import (
    LINE_SUPERSEDED,
    plan_po_less_shipped_twins,
    refresh_superseded_pointers,
    retire_po_less_shipped_twins,
    retire_po_less_twins_written_by_job,
)


@pytest.fixture
def world():
    with SessionLocal() as db:
        if db.scalar(text("select current_database()")) != "cip_test":
            pytest.skip("cip_test only")
        tag = secrets.token_hex(4)
        tenant = f"twin-{tag}"
        db.add(Tenant(id=tenant, name="PO-less twin fixture"))
        db.flush()
        tpl = ImportTemplate(slug=f"twin-{tag}", display_name="twin", pipeline_handler="inbound_shipments")
        db.add(tpl)
        db.flush()
        src = SourceDefinition(import_template_id=int(tpl.id), code=f"twin-{tag}", name="twin", source_kind="file")
        db.add(src)
        db.flush()
        jobs = []
        for name in ("ACZA Shipped Unshipped 20260721.xlsx", "ACZA Shipped Unshipped 20261027.xlsx"):
            j = ImportJob(tenant_id=tenant, source_id=int(src.id), template_slug="inbound_shipments", status="completed", stage="loaded",
                          file_name=name, completed_at=datetime(2026, 10, 29, tzinfo=timezone.utc))
            db.add(j)
            jobs.append(j)
        po = PurchaseOrder(po_number_raw=f"PO{tag}", po_number_norm=f"PO{tag}")
        db.add(po)
        db.flush()
        n = 0

        def fact(*, job, qty=10, with_po=False, delivery="15260244136", item="90NB14Y1-M00DP0"):
            """A shipped fact; ``with_po`` writes it under a PO-inclusive key like the importer does."""
            nonlocal n
            n += 1
            key = "|".join(x for x in (delivery, item, str(po.id) if with_po else "") if x)
            f = FactInboundShipment(
                tenant_id=tenant, import_job_id=int(job.id), source_key=f"sk-{tag}-{n}", fact_upsert_key=f"ship:{key}:{tag}",
                source_row_number=n, report_type="acza_workbook_shipped", line_state="shipped", raw_source_row={}, delivery_no=delivery,
                item_code=item, quantity=qty, purchase_order_id=int(po.id) if with_po else None, product_resolution_status="unresolved",
                distributor_resolution_status="unresolved",
            )
            db.add(f)
            db.flush()
            return f

        yield db, jobs, fact, tenant
        db.rollback()


def _mine(plan, tenant, db):
    ids = set(db.scalars(select(FactInboundShipment.id).where(FactInboundShipment.tenant_id == tenant)).all())
    return [t for t in plan if t.old_id in ids]


def test_matching_twin_is_retired_and_kept(world):
    db, (old_job, new_job), fact, tenant = world
    old = fact(job=old_job, qty=40)
    twin = fact(job=new_job, qty=40, with_po=True)
    plan = _mine(plan_po_less_shipped_twins(db), tenant, db)
    assert [(t.old_id, t.keeper_id, t.qty_match) for t in plan] == [(old.id, twin.id, True)]
    assert retire_po_less_shipped_twins(db, plan) == 1
    db.refresh(old)
    assert old.line_state == LINE_SUPERSEDED
    assert old.superseded_by_fact_id == twin.id and old.superseded_by_key == twin.fact_upsert_key
    assert db.get(FactInboundShipment, old.id) is not None  # kept
    open_ids = set(db.scalars(select(FactInboundShipment.id).where(FactInboundShipment.tenant_id == tenant, exclude_closed_inbound(FactInboundShipment))).all())
    assert open_ids == {twin.id}  # excluded like the closed states
    assert not _mine(plan_po_less_shipped_twins(db), tenant, db)  # a second run plans nothing


def test_quantity_difference_is_listed_not_retired(world):
    db, (old_job, new_job), fact, tenant = world
    old = fact(job=old_job, qty=40)
    fact(job=new_job, qty=36, with_po=True)
    plan = _mine(plan_po_less_shipped_twins(db), tenant, db)
    assert [(t.old_id, t.qty_match, t.old_qty, t.twin_qty) for t in plan] == [(old.id, False, 40.0, 36.0)]
    assert retire_po_less_shipped_twins(db, plan) == 0
    db.refresh(old)
    assert old.line_state == "shipped" and old.superseded_by_fact_id is None


def test_only_a_newer_job_and_the_same_delivery_and_item_count(world):
    db, (old_job, new_job), fact, tenant = world
    older = fact(job=old_job, qty=10, delivery="D1", item="I1")
    fact(job=old_job, qty=10, delivery="D1", item="I1", with_po=True)  # written by the same job: not newer
    other_item = fact(job=old_job, qty=10, delivery="D2", item="I2")
    fact(job=new_job, qty=10, delivery="D2", item="I3", with_po=True)  # newer, but another item
    assert not _mine(plan_po_less_shipped_twins(db), tenant, db)
    assert older.line_state == other_item.line_state == "shipped"


def test_load_time_rule_only_retires_what_the_job_wrote(world):
    db, (old_job, new_job), fact, tenant = world
    old_a = fact(job=old_job, qty=5, delivery="DA", item="IA")
    twin_a = fact(job=new_job, qty=5, delivery="DA", item="IA", with_po=True)
    old_b = fact(job=old_job, qty=7, delivery="DB", item="IB")
    fact(job=old_job, qty=7, delivery="DB", item="IB", with_po=True)  # written by the old job, not by new_job
    out = retire_po_less_twins_written_by_job(db, int(new_job.id))
    assert out["retired"] == 1 and out["quantity_differs"] == []
    db.refresh(old_a)
    db.refresh(old_b)
    assert old_a.line_state == LINE_SUPERSEDED and old_b.line_state == "shipped"
    assert old_a.superseded_by_fact_id == twin_a.id


def test_pointer_follows_a_replaced_twin(world):
    db, (old_job, new_job), fact, tenant = world
    old = fact(job=old_job, qty=9, delivery="DR", item="IR")
    twin = fact(job=new_job, qty=9, delivery="DR", item="IR", with_po=True)
    retire_po_less_twins_written_by_job(db, int(new_job.id))
    key = twin.fact_upsert_key
    # a reload replaces the row: same key, new id
    db.execute(text("DELETE FROM fact_inbound_shipment WHERE id = :i"), {"i": twin.id})
    again = fact(job=new_job, qty=9, delivery="DR2", item="IR", with_po=True)
    db.execute(text("UPDATE fact_inbound_shipment SET fact_upsert_key = :k WHERE id = :i"), {"k": key, "i": again.id})
    db.flush()
    assert refresh_superseded_pointers(db) >= 1
    db.refresh(old)
    assert old.superseded_by_fact_id == again.id and old.superseded_by_key == key


def test_evidence_sum_rule_retires_a_partial_old_fact_only_when_asked_and_only_when_the_twin_adds_up(world):
    """An old job lost rows to the loader, so its fact is a part of what the twin holds: the twin equals its job's evidence lines."""
    from app.models.shipment_evidence import ShipmentEvidenceLine

    db, (old_job, new_job), fact, tenant = world
    old_ok = fact(job=old_job, qty=36, delivery="DE", item="IE")
    twin_ok = fact(job=new_job, qty=108, delivery="DE", item="IE", with_po=True)
    old_bad = fact(job=old_job, qty=36, delivery="DF", item="IF")
    twin_bad = fact(job=new_job, qty=108, delivery="DF", item="IF", with_po=True)
    n = 0
    for twin, delivery, item, quantities in ((twin_ok, "DE", "IE", (36, 36, 36)), (twin_bad, "DF", "IF", (36, 36))):  # the second adds up to 72, not 108
        for q in quantities:
            n += 1
            db.add(ShipmentEvidenceLine(
                import_job_id=int(new_job.id), source_sheet="Shipped", source_row_number=n, report_type="acza_workbook_shipped", line_state="shipped",
                source_key=f"ev-{twin.id}-{n}", raw_source_row={}, delivery_no=delivery, item_code=item, quantity=q, purchase_order_id=twin.purchase_order_id,
                product_resolution_status="unresolved", distributor_resolution_status="unresolved",
            ))
    db.flush()
    plan = {t.old_id: t for t in _mine(plan_po_less_shipped_twins(db), tenant, db)}
    assert plan[old_ok.id].qty_match is False and plan[old_ok.id].evidence_match is True
    assert plan[old_bad.id].evidence_match is False
    assert retire_po_less_shipped_twins(db, list(plan.values())) == 0  # the default rule leaves both
    assert retire_po_less_shipped_twins(db, list(plan.values()), accept_evidence_sum=True) == 1
    db.refresh(old_ok)
    db.refresh(old_bad)
    assert old_ok.line_state == LINE_SUPERSEDED and old_ok.superseded_by_fact_id == twin_ok.id
    assert old_bad.line_state == "shipped"


def test_orphaned_open_rows_of_a_re_read_job_are_retired_and_the_needs_a_look_rule_counts_each_line_once(world):
    """A re-read job leaves its old-key open facts behind (no evidence line, same job): they were counted beside the new ones."""
    from datetime import date

    from app.models.shipment_evidence import ShipmentEvidenceLine
    from app.services.imports.shipment_shipped_fact_identity_twin_merge import plan_orphaned_open_rows, retire_orphaned_open_rows
    from app.services.shipping_commercial_kpis import predicate_needs_look

    db, (old_job, new_job), fact, tenant = world
    n = 0

    def open_fact(*, with_line: bool, order: str, qty: float = 20.0):
        nonlocal n
        n += 1
        line_id = None
        if with_line:
            line = ShipmentEvidenceLine(
                import_job_id=int(new_job.id), source_sheet="Shipped", source_row_number=n, report_type="acza_workbook_shipped", line_state="open_order",
                source_key=f"ol-{n}", raw_source_row={}, order_no=order, order_line="1.1", item_code="I1", quantity=qty,
                product_resolution_status="unresolved", distributor_resolution_status="unresolved",
            )
            db.add(line)
            db.flush()
            line_id = int(line.id)
        f = FactInboundShipment(
            tenant_id=tenant, import_job_id=int(new_job.id), source_key=f"of-{n}", fact_upsert_key=f"of-key-{n}", shipment_evidence_line_id=line_id,
            source_row_number=n, report_type="acza_workbook_shipped", line_state="open_order", raw_source_row={}, order_no=order, order_line="1.1",
            item_code="I1", quantity=qty, exwork_date=date(2026, 9, 29), product_resolution_status="unresolved", distributor_resolution_status="unresolved",
        )
        db.add(f)
        db.flush()
        return f

    old_a = open_fact(with_line=False, order="SO-A")
    new_a = open_fact(with_line=True, order="SO-A")
    old_b = open_fact(with_line=False, order="SO-B")  # nothing carries SO-B any more
    keep_c = open_fact(with_line=True, order="SO-C")

    def card():
        return db.scalars(select(FactInboundShipment.id).where(FactInboundShipment.tenant_id == tenant, predicate_needs_look(date(2026, 11, 2), 7))).all()

    assert sorted(card()) == sorted([old_a.id, new_a.id, old_b.id, keep_c.id])  # before: the re-keyed line is counted twice
    plan = [r for r in plan_orphaned_open_rows(db, int(new_job.id)) if r["id"] in (old_a.id, old_b.id)]
    assert {r["id"]: r["replaced_by"] for r in plan} == {old_a.id: new_a.id, old_b.id: None}
    assert retire_orphaned_open_rows(db, int(new_job.id), plan) == {"superseded": 1, "disappeared": 1}
    db.refresh(old_a)
    db.refresh(old_b)
    assert old_a.line_state == LINE_SUPERSEDED and old_a.superseded_by_fact_id == new_a.id and old_a.superseded_by_key == new_a.fact_upsert_key
    assert old_b.line_state == "closed_disappeared"
    assert sorted(card()) == sorted([new_a.id, keep_c.id])  # after: each line once
    assert not [r for r in plan_orphaned_open_rows(db, int(new_job.id)) if r["id"] in (old_a.id, old_b.id)]
