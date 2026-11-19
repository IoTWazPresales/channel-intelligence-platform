"""T1b: PO auto-link proposals read only what they can use.

Before: every shipment fact in the database (all columns, ``raw_source_row`` included) was loaded
as an ORM row whatever its date, every lineup line with its JSON payload, every purchase order in
those shipments; each shipment then scanned every linked case/PO pair, and the product-line lookup
covered every shipped product. Now: column reads, shipments bounded in SQL to the quarters of the
cases being matched (a fact outside every case window can match nothing), the linked-PO check is a
set lookup, and the competition inputs are read only for the PO numbers that two or more cases
claim. Output for the same arguments is unchanged.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from app.services.commercial_planner import lineup_po_auto_link as mod

Q2 = date(2098, 4, 1)
OC = 900


def _case(id_, label="2098Q2", start=Q2, file_name="2. Plan.xlsx"):
    return SimpleNamespace(
        id=id_,
        period_label=label,
        inferred_period_start=start,
        file_name=file_name,
        commercial_status="active",
        business_unit="AA",
        product_line="AA",
        superseded_by_case_id=None,
    )


def _line(case_id, product_id, customer_id, qty, staging=False):
    return SimpleNamespace(
        case_id=case_id,
        product_id=product_id,
        customer_id=customer_id,
        distributor_id=None,
        quantity_units=qty,
        staging_open_channel=staging,
    )


def _ship(id_, po, product, cust, state, crad, qty, counted, dist=7):
    return SimpleNamespace(
        id=id_,
        purchase_order_id=po,
        product_id=product,
        resolved_customer_id=cust,
        resolved_distributor_id=dist,
        line_state=state,
        crad_date=crad,
        schedule_ship_date=None,
        ship_confirm_date=None,
        quantity=qty,
        counted_quantity=counted,
    )


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)

    def scalars(self):
        return SimpleNamespace(all=lambda: list(self._rows))


class _Db:
    def __init__(self, *, cases, lines, linked, ships, pos, ship_pairs=(), products=(), product_lines=()):
        self.cases, self.lines, self.linked = cases, lines, linked
        self.ships, self.pos = ships, pos
        self.ship_pairs, self.products, self.product_lines = ship_pairs, products, product_lines
        self.sql: list[str] = []

    @asynccontextmanager
    async def begin_nested(self):
        yield

    async def execute(self, stmt):
        try:
            sql = str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
        except Exception:  # a JSONB bind has no literal form
            sql = str(stmt.compile(dialect=postgresql.dialect()))
        self.sql.append(sql)
        if "FROM commercial_lineup_po_auto_link_dismiss" in sql:
            return _Result([])
        if "FROM commercial_lineup_case_po" in sql:
            return _Result(self.linked)
        if "FROM commercial_lineup_case" in sql:
            return _Result(self.cases)
        if "FROM commercial_lineup_line" in sql:
            return _Result(self.lines)
        if "FROM fact_inbound_shipment" in sql:
            # the phase-2 competition read selects only (po, product); the main read has counted_quantity
            return _Result(self.ships if "counted_quantity" in sql else self.ship_pairs)
        if "FROM purchase_order" in sql:
            if "purchase_order.distributor_id" in sql:
                return _Result(self.pos)
            return _Result([(po.id, po.po_number_norm, po.po_number_raw) for po in self.pos])  # phase 2 lookup
        if "FROM dim_product" in sql:
            return _Result(self.products if "dim_product.sku" in sql else self.product_lines)
        if "FROM dim_customer" in sql:
            return _Result([(50, "C50", "Customer fifty")])
        if "FROM dim_distributor" in sql:
            return _Result([(7, "D7", "Distributor seven")])
        raise AssertionError(f"unexpected statement: {sql}")


def _po(id_, norm, dist=None, raw=None):
    return SimpleNamespace(id=id_, po_number_norm=norm, po_number_raw=raw or norm.lower(), distributor_id=dist)


def _db(**over):
    base = dict(
        cases=[_case(1), _case(2)],
        lines=[_line(1, 10, 50, 100), _line(2, 10, 50, 40)],
        linked=[(1, 2)],
        ships=[
            _ship(1, 1, 10, 50, "shipped", date(2098, 5, 10), 60, 60),
            _ship(2, 1, 10, 50, "open_order", date(2098, 6, 1), 25, 20),
            _ship(3, 2, 10, 50, "shipped", date(2098, 5, 2), 30, 30),  # PO-2 is already linked
        ],
        pos=[_po(1, "PO-1", dist=7), _po(2, "PO-2")],
        ship_pairs=[(1, 10)],
        products=[(10, "SKU-10", "Model 10", "Market 10")],
        product_lines=[(10, "aa")],
    )
    base.update(over)
    return _Db(**base)


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    async def oc(_db):
        return OC, frozenset({OC})

    monkeypatch.setattr(mod, "get_open_channel_canonical_and_aliases", oc)
    monkeypatch.setattr(mod, "protected_lineup_case_ids_from_config", lambda: frozenset())


def _run(db, **kw):
    return asyncio.run(mod._po_auto_link_proposals_inner(db, period=None, customer_id=None, confidence=None,
                                                         limit=kw.pop("limit", 500), include_dismissed=False))


def test_proposals_for_two_cases_claiming_one_po() -> None:
    out = _run(_db())
    assert out["data_unavailable"] is False
    assert out["total"] == 2 and out["returned"] == 2
    by_case = {p["case_id"]: p for p in out["proposals"]}
    assert set(by_case) == {1, 2}
    p1 = by_case[1]
    assert p1["proposal_key"] == "1:50:PO-1"
    assert p1["confidence"] == "high" and p1["reason"] == "customer_product_crad_in_period"
    assert p1["purchase_order_id"] == 1 and p1["po_number_norm"] == "PO-1"
    assert p1["customer_label"] == "C50 — Customer fifty"
    assert p1["distributor_name"] == "Distributor seven"
    assert p1["already_linked"] is False
    assert p1["total_shipped_units"] == 60.0 and p1["total_open_order_units"] == 20.0
    assert p1["total_planned_units"] == 100.0
    assert by_case[2]["total_planned_units"] == 40.0
    assert p1["matched_products"][0]["sku"] == "SKU-10"
    # PO-2 is linked to case 1: no proposal for it, and its shipped units are group coverage
    assert out["competition_summary"]["multi_case_po_norms"] == 1
    assert p1["competition"] is not None
    assert out["group_coverage_by_key"]["2098Q2|50"]["linked_shipped_units"] == 30.0
    assert out["group_coverage_by_key"]["2098Q2|50"]["group_planned_units"] == 140.0


def test_limit_cuts_the_page_not_the_total() -> None:
    out = _run(_db(), limit=1)
    assert out["total"] == 2 and out["returned"] == 1 and len(out["proposals"]) == 1


def test_shipments_are_read_as_columns_bounded_to_the_case_quarters() -> None:
    db = _db(cases=[_case(1), _case(2, label="2098Q3", start=date(2098, 7, 1))])
    _run(db)
    main = next(s for s in db.sql if "FROM fact_inbound_shipment" in s and "counted_quantity" in s)
    assert "raw_source_row" not in main  # no full ORM rows
    assert "fact_inbound_shipment.crad_date" in main
    # earliest quarter start, latest quarter end of the cases in play
    assert "2098-04-01" in main and "2098-10-01" in main
    assert "purchase_order_id IS NOT NULL" in main and "product_id IS NOT NULL" in main


def test_no_case_with_a_period_means_no_shipment_read() -> None:
    db = _db(cases=[_case(1, start=None, label=None)])
    out = _run(db)
    assert out["proposals"] == [] and out["total"] == 0
    assert not any("FROM fact_inbound_shipment" in s for s in db.sql)


def test_lines_and_purchase_orders_are_column_reads() -> None:
    db = _db()
    _run(db)
    lines = next(s for s in db.sql if "FROM commercial_lineup_line" in s)
    assert "pricing_chain_json" not in lines and "month_split_json" not in lines
    assert "commercial_lineup_line.raw_row_payload[" in lines  # one JSON value (the staging flag), not the payload
    assert "raw_row_payload," not in lines and "raw_row_payload " not in lines.split("FROM")[0].replace("raw_row_payload[", "")
    pos = next(s for s in db.sql if "FROM purchase_order" in s)
    assert "purchase_order.po_number_norm" in pos
    assert "created_at" not in pos


def test_no_per_shipment_scan_of_linked_pairs(monkeypatch) -> None:
    def boom(*a, **k):
        raise AssertionError("linked pairs are looked up in a set, not scanned per shipment")

    monkeypatch.setattr(mod, "_po_norm_already_linked_anywhere", boom)
    monkeypatch.setattr(mod, "_case_norm_already_linked", boom)
    out = _run(_db())
    assert out["total"] == 2


def test_competition_inputs_are_read_only_for_claimed_po_numbers() -> None:
    # one case only: nothing is claimed twice, so no competition read happens at all
    db = _db(cases=[_case(1)], lines=[_line(1, 10, 50, 100)])
    out = _run(db)
    assert out["total"] == 1
    assert sum("FROM fact_inbound_shipment" in s for s in db.sql) == 1
    assert sum("FROM dim_product" in s for s in db.sql) == 1  # proposal products only

    db = _db()
    _run(db)
    comp = [s for s in db.sql if "FROM fact_inbound_shipment" in s and "counted_quantity" not in s]
    assert len(comp) == 1
    assert "purchase_order_id IN (1)" in comp[0]  # the PO(s) behind the claimed number, nothing else
