"""GOV-008 review 2 Nov, M1: the 20261101_0050 downgrade must put every closed_superseded row back to the state it had.

Two paths write ``closed_superseded``: the PO-less twin retire (the row was ``shipped``) and the orphan open-row retire
(the row was ``open_order``). The old downgrade set all of them to ``shipped``: an orphan-retired open order became shipped
units with no ship confirm date.

cip_test only, one transaction that is rolled back (Postgres DDL is transactional). Sequence per test: the migration's own
downgrade then upgrade (so the columns exist as if just upgraded), the fixture rows, the real retire functions, the
downgrade, and a comparison of every row with the state it had before the retire.
"""

from __future__ import annotations

import importlib.util
import secrets
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import text

from app.db.session_sync import SessionLocal
from app.models.facts import FactInboundShipment
from app.models.iam import Tenant
from app.models.ingestion import ImportJob, ImportTemplate, SourceDefinition
from app.models.purchase_order import PurchaseOrder
from app.models.shipment_evidence import ShipmentEvidenceLine
from app.services.imports.shipment_shipped_fact_identity_twin_merge import (
    plan_orphaned_open_rows,
    plan_po_less_shipped_twins,
    retire_orphaned_open_rows,
    retire_po_less_shipped_twins,
)

API_DIR = Path(__file__).resolve().parents[1]
UNSHIP, SHIPPED, SHIPMENT_0025 = "acza_workbook_unship", "acza_workbook_shipped", "xxomrpt0025_shipment"


def _migration():
    path = API_DIR / "alembic" / "versions" / "20261101_0050_fact_superseded.py"
    spec = importlib.util.spec_from_file_location("m0050", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _states(db, tenant) -> dict[int, str]:
    return {r[0]: r[1] for r in db.execute(text("SELECT id, line_state FROM fact_inbound_shipment WHERE tenant_id = :t"), {"t": tenant}).all()}


@pytest.fixture
def world():
    with SessionLocal() as db:
        if db.scalar(text("select current_database()")) != "cip_test":
            pytest.skip("cip_test only")
        mod = _migration()
        ops = Operations.context(MigrationContext.configure(db.connection()))
        with ops:
            mod.downgrade()
            mod.upgrade()
        tag = secrets.token_hex(4)
        tenant = f"m1-{tag}"
        db.add(Tenant(id=tenant, name="0050 downgrade fixture"))
        db.flush()
        tpl = ImportTemplate(slug=f"m1-{tag}", display_name="m1", pipeline_handler="inbound_shipments")
        db.add(tpl)
        db.flush()
        src = SourceDefinition(import_template_id=int(tpl.id), code=f"m1-{tag}", name="m1", source_kind="file")
        db.add(src)
        db.flush()
        jobs = []
        for name in ("ACZA Shipped Unshipped 20260721.xlsx", "ACZA Shipped Unshipped 20261027.xlsx"):
            j = ImportJob(tenant_id=tenant, source_id=int(src.id), template_slug="inbound_shipments", status="completed", stage="loaded",
                          file_name=name, completed_at=datetime(2026, 10, 29, tzinfo=timezone.utc))
            db.add(j)
            jobs.append(j)
        po = PurchaseOrder(po_number_raw=f"M1PO{tag}", po_number_norm=f"M1PO{tag}")
        db.add(po)
        db.flush()
        n = 0

        def fact(*, job, report_type, state, order="SO-1", oline="1", item="IT-1", qty=10.0, delivery=None, confirm=None, with_po=False, with_line=False):
            nonlocal n
            n += 1
            line_id = None
            if with_line:
                line = ShipmentEvidenceLine(
                    import_job_id=int(job.id), source_sheet="s", source_row_number=n, report_type=report_type, line_state=state,
                    source_key=f"ev-{tag}-{n}", raw_source_row={}, order_no=order, order_line=oline, item_code=item, quantity=qty,
                    product_resolution_status="unresolved", distributor_resolution_status="unresolved",
                )
                db.add(line)
                db.flush()
                line_id = int(line.id)
            f = FactInboundShipment(
                tenant_id=tenant, import_job_id=int(job.id), source_key=f"sk-{tag}-{n}", fact_upsert_key=f"fk-{tag}-{n}",
                shipment_evidence_line_id=line_id, source_row_number=n, report_type=report_type, line_state=state, raw_source_row={},
                order_no=order, order_line=oline, item_code=item, quantity=qty, delivery_no=delivery, ship_confirm_date=confirm,
                purchase_order_id=int(po.id) if with_po else None, product_resolution_status="unresolved",
                distributor_resolution_status="unresolved",
            )
            db.add(f)
            db.flush()
            return f

        yield db, mod, jobs, tenant, fact
        db.rollback()


def _downgrade(db, mod):
    with Operations.context(MigrationContext.configure(db.connection())):
        mod.downgrade()


def test_every_retired_row_comes_back_to_the_state_it_had(world):
    db, mod, (old_job, new_job), tenant, fact = world

    # 1. PO-less shipped twins (state 'shipped') of two report types, each with the PO-key twin a newer job wrote.
    twin_a = fact(job=old_job, report_type=SHIPPED, state="shipped", order="SO-A", item="IT-A", delivery="D-A", confirm=date(2026, 7, 1))
    fact(job=new_job, report_type=SHIPPED, state="shipped", order="SO-A", item="IT-A", delivery="D-A", confirm=date(2026, 7, 1), with_po=True)
    twin_d = fact(job=old_job, report_type=SHIPMENT_0025, state="shipped", order="SO-D", item="IT-D", delivery="D-D", confirm=date(2026, 7, 2))
    fact(job=new_job, report_type=SHIPMENT_0025, state="shipped", order="SO-D", item="IT-D", delivery="D-D", confirm=date(2026, 7, 2), with_po=True)

    # 2. Orphaned open orders (state 'open_order', no evidence line) with a replacement open fact carried by the job.
    orphan_b = fact(job=new_job, report_type=SHIPPED, state="open_order", order="SO-B", item="IT-B")
    fact(job=new_job, report_type=SHIPPED, state="open_order", order="SO-B", item="IT-B", with_line=True)
    orphan_c = fact(job=new_job, report_type=UNSHIP, state="open_order", order="SO-C", item="IT-C")
    fact(job=new_job, report_type=UNSHIP, state="open_order", order="SO-C", item="IT-C", with_line=True)
    # 3. An orphan whose replacement closed since (state of the pointer target is no longer 'open_order'); no confirm date.
    orphan_e = fact(job=new_job, report_type=SHIPPED, state="open_order", order="SO-E", item="IT-E")
    repl_e = fact(job=new_job, report_type=SHIPPED, state="open_order", order="SO-E", item="IT-E", with_line=True)

    before = _states(db, tenant)
    assert before[twin_a.id] == "shipped" and before[orphan_b.id] == "open_order"

    twins = [t for t in plan_po_less_shipped_twins(db) if t.old_id in (twin_a.id, twin_d.id)]
    assert retire_po_less_shipped_twins(db, twins) == 2
    plan = [r for r in plan_orphaned_open_rows(db, int(new_job.id)) if r["id"] in (orphan_b.id, orphan_c.id, orphan_e.id)]
    assert retire_orphaned_open_rows(db, int(new_job.id), plan) == {"superseded": 3, "disappeared": 0}
    db.execute(text("UPDATE fact_inbound_shipment SET line_state = 'closed_shipped' WHERE id = :i"), {"i": repl_e.id})
    retired = _states(db, tenant)
    assert {i for i, s in retired.items() if s == "closed_superseded"} == {twin_a.id, twin_d.id, orphan_b.id, orphan_c.id, orphan_e.id}

    _downgrade(db, mod)

    after = _states(db, tenant)
    expected = {**before, repl_e.id: "closed_shipped"}  # the replacement's own later close is not this migration's business
    assert after == expected
    assert "closed_superseded" not in after.values()
    # The point of M1: none of the orphan-retired open orders came back as shipped.
    assert after[orphan_b.id] == after[orphan_c.id] == after[orphan_e.id] == "open_order"
    cols = {r[0] for r in db.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'fact_inbound_shipment'")).all()}
    assert "superseded_by_key" not in cols and "superseded_by_fact_id" not in cols


def test_downgrade_never_turns_an_open_order_into_shipped_units(world):
    """Shipped quantity before and after a retire + downgrade is the same: no open order gains a 'shipped' state."""
    db, mod, (old_job, new_job), tenant, fact = world
    orphan = fact(job=new_job, report_type=SHIPPED, state="open_order", order="SO-Q", item="IT-Q", qty=921.0)
    fact(job=new_job, report_type=SHIPPED, state="open_order", order="SO-Q", item="IT-Q", qty=921.0, with_line=True)
    shipped_before = db.scalar(text("SELECT coalesce(sum(quantity),0) FROM fact_inbound_shipment WHERE tenant_id = :t AND line_state = 'shipped'"), {"t": tenant})
    plan = [r for r in plan_orphaned_open_rows(db, int(new_job.id)) if r["id"] == orphan.id]
    assert retire_orphaned_open_rows(db, int(new_job.id), plan)["superseded"] == 1
    _downgrade(db, mod)
    shipped_after = db.scalar(text("SELECT coalesce(sum(quantity),0) FROM fact_inbound_shipment WHERE tenant_id = :t AND line_state = 'shipped'"), {"t": tenant})
    assert shipped_before == shipped_after == 0
    assert db.scalar(text("SELECT line_state FROM fact_inbound_shipment WHERE id = :i"), {"i": orphan.id}) == "open_order"


def test_known_limit_open_shipped_sheet_orphan_with_a_confirm_date_and_a_closed_replacement_returns_shipped(world):
    """The one case the surviving columns cannot settle (see the migration comment): pinned so a change is noticed."""
    db, mod, (old_job, new_job), tenant, fact = world
    orphan = fact(job=new_job, report_type=SHIPPED, state="open_order", order="SO-L", item="IT-L", confirm=date(2026, 12, 1))
    repl = fact(job=new_job, report_type=SHIPPED, state="open_order", order="SO-L", item="IT-L", with_line=True)
    plan = [r for r in plan_orphaned_open_rows(db, int(new_job.id)) if r["id"] == orphan.id]
    retire_orphaned_open_rows(db, int(new_job.id), plan)
    db.execute(text("UPDATE fact_inbound_shipment SET line_state = 'closed_disappeared' WHERE id = :i"), {"i": repl.id})
    _downgrade(db, mod)
    assert db.scalar(text("SELECT line_state FROM fact_inbound_shipment WHERE id = :i"), {"i": orphan.id}) == "shipped"
