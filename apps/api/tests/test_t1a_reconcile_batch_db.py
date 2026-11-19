"""T1a: batched PO reconciliation against a real database (cip_test only, rolled back).

NOT run by the author (no DB access in the T1a lane): the coordinator runs this on cip_test.

* The batched SQL (case-scoped joins to the PO link table, twin-remainder CTE, distinct reads)
  executes on Postgres and ``reconcile_cases`` returns, per case, exactly what ``reconcile_case``
  returns for that case alone.
* Two cases linked to the SAME purchase order each get the PO's evidence (no cross-case leakage,
  no double counting) and a case with no PO is unaffected.
* The number of SQL statements is the same for 1 case and for many cases.
"""

from __future__ import annotations

import secrets
from datetime import UTC, date, datetime

import pytest
from app.models.commercial_lineup import (
    CommercialLineupCase,
    CommercialLineupCasePo,
    CommercialLineupLine,
)
from app.models.dimensions import DimCustomer, DimProduct
from app.models.iam import Tenant
from app.models.ingestion import ImportJob, ImportTemplate, SourceDefinition
from app.models.purchase_order import PurchaseOrder
from app.services.commercial_planner.lineup_po_reconciliation import (
    reconcile_case,
    reconcile_cases,
)
from sqlalchemy import event
from tests.rolled_back_async_session import rolled_back_async_session
from tests.shipment_evidence_fixtures import add_evidence_line


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def session():
    async with rolled_back_async_session() as db:
        yield db


def _count_statements(db):
    """Count SQL statements the session's connection executes from now on."""
    counter = {"n": 0}
    sync_conn = db.bind.sync_connection

    def _bump(*_args, **_kwargs):
        counter["n"] += 1

    event.listen(sync_conn, "before_cursor_execute", _bump)
    return counter, lambda: event.remove(sync_conn, "before_cursor_execute", _bump)


async def _plan_case(db, *, tag, label, product, customer, units, po=None):
    case = CommercialLineupCase(
        period_label=label,
        inferred_period_start=date(2026, 10, 1),
        commercial_status="po_issued",
        business_unit="BU",
        product_line="PL",
        currency_code="ZAR",
    )
    db.add(case)
    await db.flush()
    db.add(
        CommercialLineupLine(
            case_id=case.id,
            product_id=product.id,
            customer_id=customer.id,
            quantity_units=units,
            row_status="active",
        )
    )
    if po is not None:
        db.add(CommercialLineupCasePo(case_id=case.id, purchase_order_id=po.id))
    await db.flush()
    return case


async def _world(db, *, extra_cases=0):
    tag = secrets.token_hex(4)
    tenant = f"t1a-{tag}"
    product = DimProduct(sku=f"T1A-{tag}-SKU", name=f"Product {tag}", tenant_id=tenant)
    customer = DimCustomer(code=f"T1A-{tag}-C", name=f"Customer {tag}", tenant_id=tenant)
    shared_po = PurchaseOrder(po_number_raw=f"T1A{tag}A", po_number_norm=f"T1A{tag}A")
    silent_po = PurchaseOrder(po_number_raw=f"T1A{tag}B", po_number_norm=f"T1A{tag}B")
    db.add_all([product, customer, shared_po, silent_po])
    await db.flush()

    case_a = await _plan_case(
        db, tag=tag, label="26Q4", product=product, customer=customer, units=100, po=shared_po
    )
    case_b = await _plan_case(
        db, tag=tag, label="26Q4", product=product, customer=customer, units=40, po=shared_po
    )
    case_c = await _plan_case(
        db, tag=tag, label="26Q4", product=product, customer=customer, units=10, po=silent_po
    )
    case_none = await _plan_case(
        db, tag=tag, label="26Q4", product=product, customer=customer, units=5, po=None
    )
    extras = [
        await _plan_case(
            db, tag=tag, label="26Q4", product=product, customer=customer, units=7, po=silent_po
        )
        for _ in range(extra_cases)
    ]
    return tenant, product, customer, shared_po, [case_a, case_b, case_c, case_none, *extras]


async def _seed_evidence(db, *, tenant, product, customer, shared_po):
    """Shipped 60 + open-order 40 on the shared PO (through the evidence loader's own helpers)."""

    def _seed(sync_session):
        sync_session.add(Tenant(id=tenant, name="T1A fixture"))
        sync_session.flush()
        tpl = ImportTemplate(
            slug=f"{tenant}-tpl", display_name="t1a", pipeline_handler="inbound_shipments"
        )
        sync_session.add(tpl)
        sync_session.flush()
        src = SourceDefinition(
            import_template_id=int(tpl.id), code=f"{tenant}-src", name="t1a", source_kind="file"
        )
        sync_session.add(src)
        sync_session.flush()
        job = ImportJob(
            tenant_id=tenant,
            source_id=int(src.id),
            template_slug="inbound_shipments",
            status="completed",
            stage="loaded",
            file_name="t1a.xlsx",
            completed_at=datetime(2026, 10, 29, tzinfo=UTC),
        )
        sync_session.add(job)
        sync_session.flush()
        for n, (state, order_no, qty) in enumerate(
            [("shipped", "T1A-SO-1", 60), ("open_order", "T1A-SO-2", 40)], start=1
        ):
            add_evidence_line(
                sync_session,
                import_job_id=int(job.id),
                source_sheet="Shipped",
                source_row_number=n,
                report_type="acza_workbook_shipped",
                line_state=state,
                source_key=f"t1a-{tenant}-{n}",
                raw_source_row={},
                order_no=order_no,
                item_code="T1A-ITEM",
                quantity=qty,
                purchase_order_id=int(shared_po.id),
                product_id=int(product.id),
                resolved_customer_id=int(customer.id),
                product_resolution_status="resolved",
                distributor_resolution_status="unresolved",
            )

    await db.run_sync(_seed)


async def test_batch_equals_single_case_path_without_evidence(session):
    _tenant, _product, _customer, _po, cases = await _world(session)
    ids = [int(c.id) for c in cases]
    batch = await reconcile_cases(session, ids)
    assert set(batch) == set(ids)
    for cid in ids:
        assert batch[cid] == await reconcile_case(session, cid)
        assert batch[cid]["data_unavailable"] is False
    # planned units come from each case's own lines; the case without a PO links nothing
    by_case = {cid: batch[cid] for cid in ids}
    assert by_case[ids[3]]["linked_po_count"] == 0
    assert by_case[ids[0]]["linked_po_count"] == 1
    assert sum(p["planned_units"] for p in by_case[ids[0]]["products"]) == 100
    assert sum(p["planned_units"] for p in by_case[ids[1]]["products"]) == 40


async def test_shared_po_evidence_reaches_each_linked_case_once(session):
    tenant, product, customer, shared_po, cases = await _world(session)
    await _seed_evidence(
        session, tenant=tenant, product=product, customer=customer, shared_po=shared_po
    )
    ids = [int(c.id) for c in cases]
    batch = await reconcile_cases(session, ids)

    def _row(payload):
        rows = [p for p in payload["products"] if p["product_id"] == int(product.id)]
        assert len(rows) == 1
        return rows[0]

    # PO shared by case A and case B: each sees the PO's 60 shipped / 40 open once (not 120/80).
    for cid in (ids[0], ids[1]):
        row = _row(batch[cid])
        assert row["shipped_units"] == 60.0
        assert row["pipeline_units"] == 40.0
    assert _row(batch[ids[0]])["units_flag"] == "short"  # plan 100, shipped 60
    assert _row(batch[ids[1]])["units_flag"] == "over"  # plan 40, shipped 60
    # The case linked only to a PO with no evidence and the unlinked case see none of it.
    assert batch[ids[2]]["po_flags"] and batch[ids[2]]["po_flags"][0]["flag"] == "po_no_match"
    assert all(p["shipped_units"] == 0 for p in batch[ids[3]]["products"])
    for cid in ids:
        assert batch[cid] == await reconcile_case(session, cid)


async def test_statement_count_does_not_grow_with_the_number_of_cases(session):
    tenant, product, customer, shared_po, cases = await _world(session, extra_cases=20)
    await _seed_evidence(
        session, tenant=tenant, product=product, customer=customer, shared_po=shared_po
    )
    ids = [int(c.id) for c in cases]

    one, stop_one = _count_statements(session)
    await reconcile_cases(session, ids[:1])
    stop_one()

    many, stop_many = _count_statements(session)
    out = await reconcile_cases(session, ids)
    stop_many()

    assert len(out) == len(ids) == 24
    assert many["n"] == one["n"], (one["n"], many["n"])
    assert many["n"] <= 14
