"""GOV-008 review 2 Nov, B1: a closed shipment fact (closed_shipped / closed_disappeared / closed_moved /
closed_superseded) is history. It must not count as shipped, inbound, open, weight, evidence or a date anchor in any reader.

cip_test only. One tenant, one rolled-back transaction. The world holds ONE live shipped fact (100), ONE live open
order (40) and four closed facts that look like shipped lines in every other way (confirm date, PO, price, product,
distributor, customer, landing date). Each test calls one reader and checks that only the live facts count.

To prove the tests catch the old behaviour, empty ``shipment_live_line._CLOSED_SORTED``: every test below that reads a
quantity then fails.
"""

from __future__ import annotations

import secrets
from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy import select, text

from app.db.session import AsyncSessionLocal
from app.models.dimensions import DimCustomer, DimDistributor, DimProduct
from app.models.facts import FactInboundShipment
from app.models.iam import Tenant
from app.models.purchase_order import PurchaseOrder
from app.query.cache import clear_query_cache
from app.query.model.execute import run_v2
from app.query.model.graph import V2Request
from app.services import shipment_live_line
from app.services.shipment_live_line import CLOSED_LINE_STATES, is_live_state, live_line, live_line_sql
from app.services.shipment_strict_pair import (
    OPEN_TWIN_REMAINDER_SQL,
    TWIN_COUNTED_QTY_SQL,
    TWIN_KEPT_SQL,
    keep_counted_line,
    outerjoin_twin_remainder,
    twin_remainder,
)

TAG = secrets.token_hex(3)
T = f"b1-{TAG}"
CLOSED = ("closed_shipped", "closed_disappeared", "closed_moved", "closed_superseded")
CONFIRM = date(2026, 10, 14)
LANDING = date(2026, 10, 20)
LATE = date(2027, 3, 2)  # a closed fact dated later than every live one: it must not move an anchor or a quarter


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_query_cache()
    yield
    clear_query_cache()


class W:
    pass


async def _session_or_skip():
    db = AsyncSessionLocal()
    name = (await db.execute(text("select current_database()"))).scalar_one()
    if name != "cip_test":
        await db.close()
        pytest.skip("cip_test only")
    return db


_n = 0


def _fact(w: W, state: str, qty: float, *, confirm=CONFIRM, cust=None, po=None, price=10.0, est_pod=LANDING) -> FactInboundShipment:
    global _n
    _n += 1
    key = f"b1-{TAG}-{_n}"
    cust = cust or w.cust
    po = po or w.po
    return FactInboundShipment(
        tenant_id=T, source_key=key, fact_upsert_key=key, source_row_number=_n, report_type="acza_workbook_shipped",
        line_state=state, raw_source_row={}, order_no=f"SO-{key}", order_line="1", item_code=f"IT-{key}", delivery_no=f"D-{key}",
        quantity=qty, unit_price=price, ship_confirm_date=confirm, est_pod_date=est_pod, purchase_order_id=po.id,
        product_id=w.prod.id, distributor_id=w.dist.id, resolved_distributor_id=w.dist.id,
        customer_id=cust.id, resolved_customer_id=cust.id,
        product_resolution_status="resolved", distributor_resolution_status="resolved", status="scheduled",
    )


async def _world(db) -> W:
    w = W()
    db.add(Tenant(id=T, name="B1 live-line fixture"))
    await db.flush()
    w.prod = DimProduct(sku=f"B1-{TAG}-P", name="B1 product", sales_model_name=f"M-B1-{TAG}", product_line=f"NB{TAG}", tenant_id=T)
    w.dist = DimDistributor(code=f"B1D{TAG}", name=f"B1 distributor {TAG}", tenant_id=T)
    w.cust = DimCustomer(code=f"B1C{TAG}", name=f"B1 live customer {TAG}", tenant_id=T)
    w.cust2 = DimCustomer(code=f"B1X{TAG}", name=f"B1 closed customer {TAG}", tenant_id=T)
    db.add_all([w.prod, w.dist, w.cust, w.cust2])
    w.po = PurchaseOrder(po_number_raw=f"B1PO{TAG}", po_number_norm=f"B1PO{TAG}")
    w.po_closed_only = PurchaseOrder(po_number_raw=f"B1PX{TAG}", po_number_norm=f"B1PX{TAG}")
    db.add_all([w.po, w.po_closed_only])
    await db.flush()

    w.live_shipped = _fact(w, "shipped", 100)
    w.live_open = _fact(w, "open_order", 40, confirm=None)
    # Four closed facts, each a different customer from the live one so evidence readers can tell. The moved one is dated
    # months later than anything live.
    w.closed = [
        _fact(w, "closed_shipped", 7, cust=w.cust2),
        _fact(w, "closed_disappeared", 13, cust=w.cust2, price=50.0),
        _fact(w, "closed_moved", 17, cust=w.cust2, confirm=LATE, price=50.0),
        _fact(w, "closed_superseded", 11, cust=w.cust2, price=50.0),
    ]
    # A PO that has nothing but a closed fact.
    w.closed_only = _fact(w, "closed_shipped", 5, cust=w.cust2, po=w.po_closed_only, confirm=LATE)
    db.add_all([w.live_shipped, w.live_open, *w.closed, w.closed_only])
    await db.flush()
    return w


# ------------------------------------------------------------------------------------------ the rule itself


def test_the_rule_names_exactly_the_four_closed_states():
    assert set(CLOSED) == set(CLOSED_LINE_STATES)
    for s in CLOSED:
        assert not is_live_state(s) and not is_live_state(s.upper()) and not is_live_state(f" {s} ")
    for s in ("shipped", "open_order", "arrived", "", None):
        assert is_live_state(s)
    sql = live_line_sql("f.line_state")
    assert sql.startswith("lower(coalesce(f.line_state, '')) NOT IN (") and all(f"'{s}'" in sql for s in CLOSED)
    assert shipment_live_line._CLOSED_SORTED == tuple(sorted(CLOSED))


@pytest.mark.anyio
async def test_rule_as_orm_predicate_and_raw_sql_agree():
    db = await _session_or_skip()
    try:
        w = await _world(db)
        ids = {w.live_shipped.id, w.live_open.id}
        orm = set((await db.scalars(select(FactInboundShipment.id).where(FactInboundShipment.tenant_id == T, live_line(FactInboundShipment.line_state)))).all())
        raw = {r[0] for r in (await db.execute(text(f"SELECT id FROM fact_inbound_shipment WHERE tenant_id = :t AND {live_line_sql()}"), {"t": T})).all()}
        assert orm == raw == ids
    finally:
        await db.rollback()
        await db.close()


# ---------------------------------------------------------------------------- strict-pair helpers (every twin reader)


@pytest.mark.anyio
async def test_twin_helpers_never_keep_a_closed_fact():
    """keep_counted_line, twin_remainder().kept, outerjoin_twin_remainder and TWIN_KEPT_SQL: one rule, four forms.

    ``outerjoin_twin_remainder`` is what inbound_lineup_quarter and lineup_po_auto_link call; ``twin_remainder().kept`` is what
    channel_ops, intake_weighted_mac, net_requirement and lineup_bulk_rederivation use.
    """
    db = await _session_or_skip()
    try:
        w = await _world(db)
        live = {w.live_shipped.id, w.live_open.id}
        F = FactInboundShipment
        a = set((await db.scalars(select(F.id).where(F.tenant_id == T, keep_counted_line(F)))).all())
        tw = twin_remainder(F)
        b = {r[0] for r in (await db.execute(select(F.id).select_from(F).outerjoin(tw.subquery, tw.onclause).where(F.tenant_id == T, tw.kept))).all()}
        stmt, tw2 = outerjoin_twin_remainder(select(F.id).where(F.tenant_id == T), F)
        stmt = stmt.add_columns(tw2.counted_quantity)
        rows2 = (await db.execute(stmt)).all()
        c = {r[0] for r in rows2}
        assert sum(float(r[1] or 0) for r in rows2) == 140.0
        d = {
            r[0]
            for r in (
                await db.execute(
                    text(
                        f"SELECT fact_inbound_shipment.id FROM fact_inbound_shipment LEFT JOIN ({OPEN_TWIN_REMAINDER_SQL}) twin_rem "
                        f"ON twin_rem.fact_id = fact_inbound_shipment.id WHERE fact_inbound_shipment.tenant_id = :t AND {TWIN_KEPT_SQL}"
                    ),
                    {"t": T},
                )
            ).all()
        }
        assert a == b == c == d == live
        total = (
            await db.execute(
                text(
                    f"SELECT sum({TWIN_COUNTED_QTY_SQL}) FROM fact_inbound_shipment LEFT JOIN ({OPEN_TWIN_REMAINDER_SQL}) twin_rem "
                    f"ON twin_rem.fact_id = fact_inbound_shipment.id WHERE fact_inbound_shipment.tenant_id = :t AND {TWIN_KEPT_SQL}"
                ),
                {"t": T},
            )
        ).scalar_one()
        assert float(total) == 140.0
    finally:
        await db.rollback()
        await db.close()


# ---------------------------------------------------------------------------------- v2 model: shipments.quantity / lines


@pytest.mark.anyio
async def test_v2_shipped_quantity_and_lines_count_only_live_facts():
    db = await _session_or_skip()
    try:
        await _world(db)
        out = await run_v2(db, V2Request(measures=["shipments.quantity", "shipments.lines"], breakdowns=[]), tenant_id=T, skip_cache=True)
        assert out["ok"], out["refusals"]
        assert out["totals"]["shipments.quantity"] == 100.0  # not 100 + 7 + 13 + 17 + 11 + 5
        assert out["totals"]["shipments.lines"] == 1
        by_customer = await run_v2(db, V2Request(measures=["shipments.quantity"], breakdowns=["customer"]), tenant_id=T, skip_cache=True)
        assert {r["customer_id"] for r in by_customer["rows"]} == {(await db.scalar(select(DimCustomer.id).where(DimCustomer.code == f"B1C{TAG}")))}
        opened = await run_v2(db, V2Request(measures=["shipments.open_quantity", "shipments.open_lines"], breakdowns=[]), tenant_id=T, skip_cache=True)
        assert opened["totals"]["shipments.open_quantity"] == 40.0 and opened["totals"]["shipments.open_lines"] == 1
    finally:
        await db.rollback()
        await db.close()


# --------------------------------------------------------------------------------------------------- channel_ops


@pytest.mark.anyio
async def test_cover_distribution_open_inbound_leaves_out_closed_facts():
    from app.api.v1.endpoints.channel_ops import _open_inbound_by_pair

    db = await _session_or_skip()
    try:
        w = await _world(db)
        got = await _open_inbound_by_pair(db, T)
        assert got == {(w.dist.id, w.prod.id): 140.0}  # shipped 100 not landed + open 40; the six closed (68) are not inbound
    finally:
        await db.rollback()
        await db.close()


@pytest.mark.anyio
async def test_movement_lens_shipped_week_ignores_closed_facts_and_their_dates():
    from app.api.v1.endpoints.channel_ops import channel_ops_movement_lens

    db = await _session_or_skip()
    try:
        await _world(db)
        out = await channel_ops_movement_lens(db=db, user={"tenant_id": T}, weeks=13)
        assert out["headlines"]["shipped_units"] == 100.0
        assert out["headlines"]["shipped_week"] == "W42"  # 14 Oct 2026; the closed fact of 2 Mar 2027 would give W09
    finally:
        await db.rollback()
        await db.close()


@pytest.mark.anyio
async def test_forecast_weekly_flow_ignores_closed_facts_and_the_anchor_they_would_set():
    from app.api.v1.endpoints.channel_ops import _cover_weekly_flow

    db = await _session_or_skip()
    try:
        await _world(db)
        out = await _cover_weekly_flow(db, T)
        assert out["shipped_through"] == CONFIRM.isoformat()
        assert sum(p["shipped"] for p in out["points"]) == 100.0
    finally:
        await db.rollback()
        await db.close()


# ------------------------------------------------------------------------------------------- CPOR intake weighting


@pytest.mark.anyio
async def test_intake_weighted_mac_weights_only_live_facts():
    from app.services.cpor.intake_weighted_mac import _disti_cost_proxy_wavg, _intake_wavg

    db = await _session_or_skip()
    try:
        w = await _world(db)

        def read(s):
            intake = _intake_wavg(s, distributor_id=w.dist.id, product_id=w.prod.id, window_start=date(2026, 10, 1), window_end=date(2026, 10, 31))
            proxy = _disti_cost_proxy_wavg(s, distributor_id=w.dist.id, product_id=w.prod.id)
            return intake, proxy

        (qty, price, _asof, _flags), (proxy_price, _pod, _pflags) = await db.run_sync(read)
        assert float(qty) == 140.0 and float(price) == 10.0  # the closed facts are priced 50 and would pull the average up
        assert float(proxy_price) == 10.0
    finally:
        await db.rollback()
        await db.close()


# ------------------------------------------------------------------------------------ inbound shipments list endpoint


@pytest.mark.anyio
async def test_inbound_shipments_list_hides_closed_facts_unless_asked():
    from app.api.v1.endpoints.inbound_shipments import list_inbound

    db = await _session_or_skip()
    try:
        w = await _world(db)
        live = await list_inbound(include_closed=False, db=db, user={"tenant_id": T})
        assert {r["id"] for r in live} == {w.live_shipped.id, w.live_open.id}
        everything = await list_inbound(include_closed=True, db=db, user={"tenant_id": T})
        assert {r["line_state"] for r in everything} == {"shipped", "open_order", *CLOSED}
    finally:
        await db.rollback()
        await db.close()


# ---------------------------------------------------------------------------------------- lineup readers (attribution)


@pytest.mark.anyio
async def test_lineup_distributor_attribution_ships_are_live_only():
    from app.services.commercial_planner.lineup_distributor_attribution import _eligible_ships_for_products

    db = await _session_or_skip()
    try:
        w = await _world(db)
        hits = await _eligible_ships_for_products(db, product_ids={w.prod.id}, period_starts={date(2026, 10, 1)})
        assert [h.shipment_id for h in hits] == [w.live_shipped.id]  # the open order has no date; the four closed ones are dated in Q4 or later
        # the closed ones dated inside the quarter would all be hits without the rule
        assert {h.quantity for h in hits} == {100.0}
    finally:
        await db.rollback()
        await db.close()


@pytest.mark.anyio
async def test_lineup_case_po_attribution_suggests_only_from_live_facts():
    from app.services.commercial_planner.lineup_case_po_attribution_gap import _live_po_bearing_ships

    db = await _session_or_skip()
    try:
        w = await _world(db)
        rows = await _live_po_bearing_ships(db, [w.prod.id], [w.dist.id])
        assert {(r[0], r[1], r[2]) for r in rows} == {(w.prod.id, w.dist.id, w.po.id)}
        assert all(r[2] != w.po_closed_only.id for r in rows)  # a PO with only a closed fact is not suggested
    finally:
        await db.rollback()
        await db.close()


@pytest.mark.anyio
async def test_lineup_customer_token_evidence_is_live_only():
    from app.services.commercial_planner.lineup_customer_token_stamp import _live_ship_rows_for_pos, _ship_evidence_for_token_lines

    db = await _session_or_skip()
    try:
        w = await _world(db)
        rows = await _live_ship_rows_for_pos(db, [w.po.id, w.po_closed_only.id])
        assert {r[2] for r in rows} == {w.cust.id}  # the customer on the four closed facts is not evidence
        line = SimpleNamespace(case_id=1, product_id=w.prod.id, customer_token="b1-token", customer_id=None)
        cids, prov = await _ship_evidence_for_token_lines(
            db, token_lines=[line], case_lines_by_case={1: [line]}, po_ids_by_case={1: [w.po.id, w.po_closed_only.id]}
        )
        assert cids == {w.cust.id}
        assert {p["customer_id"] for p in prov} == {w.cust.id}
    finally:
        await db.rollback()
        await db.close()


@pytest.mark.anyio
async def test_lineup_net_requirement_in_transit_is_live_only():
    from app.services.lineup.net_requirement import _in_transit_by_dist_product

    db = await _session_or_skip()
    try:
        w = await _world(db)
        got = await _in_transit_by_dist_product(db, distributor_id=w.dist.id, product_id=w.prod.id)
        assert got == {(w.dist.id, w.prod.id): 140.0}
    finally:
        await db.rollback()
        await db.close()


@pytest.mark.anyio
async def test_lineup_bulk_rederivation_shipment_hint_is_live_only():
    from app.services.commercial_planner.lineup_bulk_rederivation import _shipment_q1_hint

    db = await _session_or_skip()
    try:
        w = await _world(db)
        hint = await db.run_sync(
            lambda s: _shipment_q1_hint(s, product_id=w.prod.id, customer_id=None, q1_start=date(2026, 10, 1), q2_start=date(2027, 4, 1))
        )
        assert hint == 100.0  # not 100 + the closed 7 + 13 + 17 + 11 (+5)
        cust2 = await db.run_sync(
            lambda s: _shipment_q1_hint(s, product_id=w.prod.id, customer_id=w.cust2.id, q1_start=date(2026, 10, 1), q2_start=date(2027, 4, 1))
        )
        assert cust2 == 0.0  # every fact of the second customer is closed
    finally:
        await db.rollback()
        await db.close()


# ------------------------------------------------------------------------------------------ PO observed (shipped) groups


@pytest.mark.anyio
async def test_po_management_observed_groups_ignore_closed_only_pos_and_closed_dates():
    from app.services.commercial_planner.po_management import _observed_groups

    db = await _session_or_skip()
    try:
        w = await _world(db)
        groups = await _observed_groups(db)
        mine = [(k, g) for k, g in groups.items() if w.po.id in g["po_ids"] or w.po_closed_only.id in g["po_ids"]]
        assert [k for k, _ in mine] == [(2026, 4, f"NB{TAG}")]  # the closed fact of 2027-03-02 would put the PO in 2027 Q1
        assert w.po_closed_only.id not in mine[0][1]["po_ids"]
        assert mine[0][1]["shipped_units"] == 100.0
    finally:
        await db.rollback()
        await db.close()


@pytest.mark.anyio
async def test_lineup_po_gap_worklist_ignores_closed_only_pos_and_closed_dates():
    from app.services.commercial_planner.lineup_po_gap import _po_gap_worklist_inner

    db = await _session_or_skip()
    try:
        w = await _world(db)
        out = await _po_gap_worklist_inner(db, include_dismissed=False)
        rows = [(g["quarter_label"], r) for g in out["groups"] for r in g["rows"] if r["purchase_order_id"] in (w.po.id, w.po_closed_only.id)]
        assert [(label, r["purchase_order_id"], r["shipped_units"]) for label, r in rows] == [("26Q4", w.po.id, 100.0)]
    finally:
        await db.rollback()
        await db.close()


# ---------------------------------------------------------------------------- CST SKU twin disambiguation (inbound qty)


@pytest.mark.anyio
async def test_cst_sku_twin_disambiguation_inbound_quantity_is_live_only():
    from app.services.imports.cst_sku_twin_disambiguate import _fetch_windows

    db = await _session_or_skip()
    try:
        w = await _world(db)
        got = await db.run_sync(lambda s: _fetch_windows(s, [w.prod.id], customer_id=None))
        assert got[w.prod.id].qty == 140.0  # live shipped 100 + live open 40, not the closed 68 + 5
    finally:
        await db.rollback()
        await db.close()


# ------------------------------------------------------------------------------------------------- supply overview


@pytest.mark.anyio
async def test_supply_overview_headline_counts_only_live_facts():
    from app.services.supply_overview import _ISO_WEEK_START_SAST, _TODAY_SAST, _headline_sql

    db = await _session_or_skip()
    try:
        await _world(db)
        row = (await db.execute(text(_headline_sql(_TODAY_SAST, _ISO_WEEK_START_SAST)), {"tenant": T})).mappings().one()
        assert row["open_lines"] == 2 and float(row["open_units"]) == 140.0
    finally:
        await db.rollback()
        await db.close()
