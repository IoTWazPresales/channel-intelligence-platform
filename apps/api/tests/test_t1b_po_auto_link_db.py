"""T1b: PO auto-link proposals on real SQL — column reads, the shipment date bound, competition (cip_test).

World (synthetic, rolled back): one customer and product; two active cases in the same far-future
quarter, each with one line for that product (plans 100 and 40); PO-1 with a shipped line (60) and an
open-order line (25) dated inside the quarter; PO-2 linked to the first case with a shipped line (30);
PO-3 whose only line is dated years outside every case quarter.
Expected: PO-1 is proposed to both cases (high confidence, shipped 60 / open 25, planned 100 / 40)
and is flagged as claimed by two cases; PO-2 yields no proposal but its 30 shipped units are the
group's linked coverage; PO-3 yields nothing. The same numbers the pure-Python path produced.
Real session inside an outer transaction rolled back at the end (``tests/rolled_back_async_session.py``).

Not run by the author: the coordinator runs it on cip_test.
"""

from __future__ import annotations

import secrets
from datetime import date

import pytest
from app.models.commercial_lineup import CommercialLineupCase, CommercialLineupCasePo, CommercialLineupLine
from app.models.dimensions import DimCustomer, DimProduct
from app.models.facts import FactInboundShipment
from app.models.purchase_order import PurchaseOrder
from app.services.commercial_planner.lineup_po_auto_link import po_auto_link_proposals
from sqlalchemy import func, select
from tests.rolled_back_async_session import leftover_counts, rolled_back_async_session

QUARTER_START = date(2098, 4, 1)


@pytest.fixture
async def session():
    async with rolled_back_async_session() as db:
        db.info["tag"] = secrets.token_hex(4)
        yield db
        tag = db.info["tag"]
    counts = await leftover_counts(
        {
            "purchase_order": select(func.count()).where(PurchaseOrder.po_number_norm.like(f"T1B-{tag}-%")),
            "dim_customer": select(func.count()).where(DimCustomer.code == f"T1B-{tag}-C"),
            "dim_product": select(func.count()).where(DimProduct.sku == f"T1B-{tag}-SKU"),
            "fact_inbound_shipment": select(func.count()).where(FactInboundShipment.source_key.like(f"T1B-{tag}-%")),
        }
    )
    assert counts == {key: 0 for key in counts}, f"fixture rows left after teardown: {counts}"


def _ship(tag, n, *, po_id, customer_id, product_id, state, crad, qty):
    return FactInboundShipment(
        tenant_id="default",
        source_key=f"T1B-{tag}-{n}",
        fact_upsert_key=f"T1B-{tag}-{n}",
        report_type="shipment",
        line_state=state,
        raw_source_row={},
        quantity=qty,
        purchase_order_id=po_id,
        product_id=product_id,
        resolved_customer_id=customer_id,
        crad_date=crad,
        product_resolution_status="resolved",
        distributor_resolution_status="resolved",
    )


@pytest.mark.anyio
async def test_proposals_coverage_and_competition_on_real_sql(session):
    tag = session.info["tag"]
    cust = DimCustomer(code=f"T1B-{tag}-C", name=f"Customer {tag}", tenant_id="default")
    product = DimProduct(sku=f"T1B-{tag}-SKU", name=f"Product {tag}", tenant_id="default", product_line="AA")
    pos = [PurchaseOrder(po_number_raw=f"T1B-{tag}-{i}", po_number_norm=f"T1B-{tag}-{i}") for i in (1, 2, 3)]
    case_a = CommercialLineupCase(commercial_status="po_issued", period_label="2098Q2", inferred_period_start=QUARTER_START, product_line="AA")
    case_b = CommercialLineupCase(commercial_status="po_issued", period_label="2098Q2", inferred_period_start=QUARTER_START, product_line="AA")
    session.add_all([cust, product, *pos, case_a, case_b])
    await session.flush()
    session.add_all(
        [
            CommercialLineupLine(case_id=case_a.id, product_id=product.id, customer_id=cust.id, quantity_units=100),
            CommercialLineupLine(case_id=case_b.id, product_id=product.id, customer_id=cust.id, quantity_units=40),
            CommercialLineupCasePo(case_id=case_a.id, purchase_order_id=pos[1].id),
            _ship(tag, 1, po_id=pos[0].id, customer_id=cust.id, product_id=product.id, state="shipped", crad=date(2098, 5, 10), qty=60),
            _ship(tag, 2, po_id=pos[0].id, customer_id=cust.id, product_id=product.id, state="open_order", crad=date(2098, 6, 1), qty=25),
            _ship(tag, 3, po_id=pos[1].id, customer_id=cust.id, product_id=product.id, state="shipped", crad=date(2098, 5, 2), qty=30),
            _ship(tag, 4, po_id=pos[2].id, customer_id=cust.id, product_id=product.id, state="shipped", crad=date(2090, 5, 2), qty=99),
        ]
    )
    await session.flush()

    out = await po_auto_link_proposals(session, limit=0)
    assert out["data_unavailable"] is False
    ours = {p["case_id"]: p for p in out["proposals"] if p["case_id"] in (case_a.id, case_b.id)}
    assert set(ours) == {case_a.id, case_b.id}
    for case_id, planned in ((case_a.id, 100.0), (case_b.id, 40.0)):
        p = ours[case_id]
        assert p["po_number_norm"] == f"T1B-{tag}-1"
        assert p["confidence"] == "high" and p["reason"] == "customer_product_crad_in_period"
        assert p["customer_id"] == cust.id
        assert p["total_shipped_units"] == 60.0 and p["total_open_order_units"] == 25.0
        assert p["total_planned_units"] == planned
        assert p["matched_products"][0]["sku"] == f"T1B-{tag}-SKU"
        assert p["competition"] is not None  # two cases claim PO-1
    # PO-2 is linked to case A: never proposed; PO-3 is outside every quarter: never proposed
    assert not any(p["po_number_norm"] in (f"T1B-{tag}-2", f"T1B-{tag}-3") for p in out["proposals"])
    group = out["group_coverage_by_key"][f"2098Q2|{cust.id}"]
    assert group["linked_shipped_units"] == 30.0
    assert group["group_planned_units"] == 140.0
