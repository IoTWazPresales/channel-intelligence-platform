"""T1b: the supply overview's PO totals (two distinct counts) equal ``po_management.coverage`` (cip_test).

World (synthetic, rolled back): a product; three purchase orders; a live shipment line with a product
on each of the first two POs; a shipment line with no product on the third; the first PO linked to an
active lineup case, the second only to a cancelled case. Both readers must see the same totals before
and after the fixture rows go in, and the overview must report them.
Real session inside an outer transaction rolled back at the end (``tests/rolled_back_async_session.py``).

Not run by the author: the coordinator runs it on cip_test.
"""

from __future__ import annotations

import secrets

import pytest
from app.models.commercial_lineup import CommercialLineupCase, CommercialLineupCasePo
from app.models.dimensions import DimProduct
from app.models.facts import FactInboundShipment
from app.models.purchase_order import PurchaseOrder
from app.services.commercial_planner.po_management import coverage
from app.services.supply_overview import po_totals_stmt, supply_overview
from sqlalchemy import func, select
from tests.rolled_back_async_session import leftover_counts, rolled_back_async_session


@pytest.fixture
async def session():
    async with rolled_back_async_session() as db:
        db.info["tag"] = secrets.token_hex(4)
        yield db
        tag = db.info["tag"]
    counts = await leftover_counts(
        {
            "purchase_order": select(func.count()).where(PurchaseOrder.po_number_norm.like(f"T1B-{tag}-%")),
            "dim_product": select(func.count()).where(DimProduct.sku == f"T1B-{tag}-SKU"),
        }
    )
    assert counts == {key: 0 for key in counts}, f"fixture rows left after teardown: {counts}"


def _ship(tag: str, n: int, *, po_id: int, product_id: int | None) -> FactInboundShipment:
    return FactInboundShipment(
        tenant_id="default",
        source_key=f"T1B-{tag}-{n}",
        fact_upsert_key=f"T1B-{tag}-{n}",
        report_type="shipment",
        line_state="shipped",
        raw_source_row={},
        quantity=10,
        purchase_order_id=po_id,
        product_id=product_id,
        product_resolution_status="resolved",
        distributor_resolution_status="resolved",
    )


async def _totals(db):
    observed, linked = (await db.execute(po_totals_stmt())).one()
    return int(observed), int(linked)


@pytest.mark.anyio
async def test_po_totals_match_coverage_and_the_fixture_delta(session, monkeypatch):
    # Warren 2026-11-27 decisions: the reporting timezone comes from the tenant profile.
    monkeypatch.setattr("app.services.supply_overview.reporting_timezone", lambda _tenant: "Africa/Johannesburg")
    tag = session.info["tag"]
    cov = await coverage(session)
    before = await _totals(session)
    assert before == (cov["total_pos_observed"], cov["total_pos_linked"])

    product = DimProduct(sku=f"T1B-{tag}-SKU", name=f"Product {tag}", tenant_id="default")
    pos = [PurchaseOrder(po_number_raw=f"T1B-{tag}-{i}", po_number_norm=f"T1B-{tag}-{i}") for i in (1, 2, 3)]
    active = CommercialLineupCase(commercial_status="po_issued", period_label="2098Q2")
    cancelled = CommercialLineupCase(commercial_status="cancelled", period_label="2098Q2")
    session.add_all([product, *pos, active, cancelled])
    await session.flush()
    session.add_all(
        [
            _ship(tag, 1, po_id=pos[0].id, product_id=product.id),
            _ship(tag, 2, po_id=pos[1].id, product_id=product.id),
            _ship(tag, 3, po_id=pos[2].id, product_id=None),  # no product: not an observed PO
            CommercialLineupCasePo(case_id=active.id, purchase_order_id=pos[0].id),
            CommercialLineupCasePo(case_id=cancelled.id, purchase_order_id=pos[1].id),  # cancelled: not linked
        ]
    )
    await session.flush()

    after = await _totals(session)
    cov = await coverage(session)
    assert after == (cov["total_pos_observed"], cov["total_pos_linked"])
    assert (after[0] - before[0], after[1] - before[1]) == (2, 1)

    out = await supply_overview(session, {"tenant_id": "default"})
    assert (out["po_observed"], out["po_linked"]) == after
    assert out["po_data_unavailable"] is False
