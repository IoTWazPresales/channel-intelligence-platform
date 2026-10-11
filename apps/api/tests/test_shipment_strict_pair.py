"""N-0071 / D-0057 + D-0065: an open shipment line counts only what its strict shipped twins have not shipped.

Strict pair = tenant + operating unit + order number + item code (case- and edge-space-insensitive).
Fact rows are never rewritten; readers skip the open row. The value of a partly shipped open
line is pro-rata, amount x remainder / open quantity (Warren 2026-10-07, round 3).

No ``cip`` access: every test runs on an isolated in-memory SQLite copy of
``fact_inbound_shipment`` (JSONB rendered as JSON for SQLite only). Async readers get a
thin async wrapper over the sync SQLite session.
"""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any

import pytest
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from app.models.dimensions import DimDistributor
from app.models.facts import FactInboundShipment as F
from app.services.shipment_strict_pair import (
    OPEN_HAS_SHIPPED_TWIN_SQL,
    OPEN_TWIN_REMAINDER_SQL,
    TWIN_COUNTED_AMOUNT_SQL,
    TWIN_COUNTED_QTY_SQL,
    TWIN_KEPT_SQL,
    exclude_open_when_shipped_twin,
    keep_counted_line,
    open_has_shipped_twin,
    outerjoin_twin_remainder,
    skipped_open_twin_line,
)


@compiles(JSONB, "sqlite")
def _jsonb_as_json_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL rendering only
    return "JSON"


_seq = {"n": 0}


def _row(
    line_state: str,
    *,
    order_no: str | None = "SO-1",
    item_code: str | None = "90NX0001",
    operating_unit: str | None = "ACZA",
    quantity: float = 10,
    tenant_id: str = "default",
    status: str = "scheduled",
    pod_date: date | None = None,
    **extra: Any,
) -> F:
    _seq["n"] += 1
    n = _seq["n"]
    return F(
        tenant_id=tenant_id,
        source_key=f"k{n}",
        source_row_number=n,
        report_type="test",
        line_state=line_state,
        raw_source_row={},
        operating_unit=operating_unit,
        order_no=order_no,
        item_code=item_code,
        quantity=quantity,
        status=status,
        pod_date=pod_date,
        product_resolution_status="resolved",
        distributor_resolution_status="resolved",
        **extra,
    )


@pytest.fixture()
def db() -> Session:
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _pg_left(dbapi_conn, _record):  # Postgres left(text, n) used by the summary buckets
        dbapi_conn.create_function("left", 2, lambda s, n: None if s is None else str(s)[: int(n)])

    F.__table__.create(engine)
    DimDistributor.__table__.create(engine)
    with Session(engine) as session:
        yield session


def _kept_ids(db: Session) -> set[int]:
    return set(db.scalars(select(F.id).where(exclude_open_when_shipped_twin(F))).all())


def _raw_twin_ids(db: Session) -> set[int]:
    sql = f"SELECT id FROM fact_inbound_shipment WHERE lower(line_state) = 'open_order' AND {OPEN_HAS_SHIPPED_TWIN_SQL}"
    return {int(r[0]) for r in db.execute(text(sql)).all()}


# --- the rule -------------------------------------------------------------------------------


def test_open_with_exact_shipped_twin_is_skipped(db: Session) -> None:
    open_row, shipped = _row("open_order"), _row("shipped")
    db.add_all([open_row, shipped])
    db.flush()
    assert _kept_ids(db) == {shipped.id}
    assert _raw_twin_ids(db) == {open_row.id}


def test_match_ignores_case_and_edge_spaces(db: Session) -> None:
    open_row = _row("Open_Order", order_no=" so-1 ", item_code="90nx0001 ", operating_unit="acza")
    shipped = _row("SHIPPED", order_no="SO-1", item_code="90NX0001", operating_unit=" ACZA")
    db.add_all([open_row, shipped])
    db.flush()
    assert _kept_ids(db) == {shipped.id}


def test_d0057_helper_still_skips_a_partial_ship(db: Session) -> None:
    """The D-0057 helper (readers not yet on D-0065) compares keys only, not quantity.

    An open 10 with a shipped 4 is skipped by ``exclude_open_when_shipped_twin``. Readers on
    D-0065 use ``keep_counted_line`` / ``twin_remainder`` instead (tests below).
    """
    open_row, shipped = _row("open_order", quantity=10), _row("shipped", quantity=4)
    db.add_all([open_row, shipped])
    db.flush()
    assert _kept_ids(db) == {shipped.id}


@pytest.mark.parametrize(
    "shipped_kwargs",
    [
        {"order_no": "SO-2"},
        {"item_code": "90NX0002"},
        {"operating_unit": "ACKE"},
        {"tenant_id": "other"},
    ],
    ids=["different_order", "different_item", "different_operating_unit", "different_tenant"],
)
def test_open_without_strict_twin_is_kept(db: Session, shipped_kwargs: dict[str, Any]) -> None:
    open_row, shipped = _row("open_order"), _row("shipped", **shipped_kwargs)
    db.add_all([open_row, shipped])
    db.flush()
    assert _kept_ids(db) == {open_row.id, shipped.id}
    assert _raw_twin_ids(db) == set()


@pytest.mark.parametrize("blank", [None, "", "   "])
def test_open_without_order_or_item_is_never_paired(db: Session, blank: str | None) -> None:
    a = _row("open_order", order_no=blank)
    b = _row("open_order", item_code=blank)
    shipped_a = _row("shipped", order_no=blank)
    shipped_b = _row("shipped", item_code=blank)
    db.add_all([a, b, shipped_a, shipped_b])
    db.flush()
    assert {a.id, b.id} <= _kept_ids(db)


def test_shipped_row_with_null_key_does_not_hide_unrelated_open(db: Session) -> None:
    """NULL safety: a shipped row with a NULL order number must not turn NOT IN into NULL."""
    open_row = _row("open_order", order_no="SO-9")
    db.add_all([open_row, _row("shipped", order_no=None), _row("shipped", item_code=None)])
    db.flush()
    assert open_row.id in _kept_ids(db)


def test_only_open_rows_are_dropped(db: Session) -> None:
    rows = [_row("shipped"), _row("shipped"), _row("arrived"), _row("open_order")]
    db.add_all(rows)
    db.flush()
    assert _kept_ids(db) == {rows[0].id, rows[1].id, rows[2].id}


def test_raw_sql_and_orm_helper_agree(db: Session) -> None:
    db.add_all(
        [
            _row("open_order"),
            _row("open_order", order_no="SO-2"),
            _row("open_order", item_code=None),
            _row("shipped"),
            _row("shipped", order_no=None),
            _row("arrived", order_no="SO-2"),
        ]
    )
    db.flush()
    orm_twins = set(
        db.scalars(select(F.id).where(func.lower(F.line_state) == "open_order", open_has_shipped_twin(F))).all()
    )
    assert orm_twins == _raw_twin_ids(db)
    assert len(orm_twins) == 1


def test_fact_rows_are_not_rewritten(db: Session) -> None:
    db.add_all([_row("open_order"), _row("shipped")])
    db.flush()
    before = db.execute(select(F.id, F.line_state, F.quantity, F.updated_at)).all()
    _kept_ids(db)
    _raw_twin_ids(db)
    assert db.execute(select(F.id, F.line_state, F.quantity, F.updated_at)).all() == before
    assert db.scalar(select(func.count()).select_from(F)) == 2


# --- readers ---------------------------------------------------------------------------------


class _AsyncOverSync:
    """Just enough AsyncSession for readers that only call execute/scalar."""

    def __init__(self, session: Session) -> None:
        self._s = session

    async def execute(self, stmt: Any, *args: Any, **kwargs: Any) -> Any:
        return self._s.execute(stmt, *args, **kwargs)

    async def scalar(self, stmt: Any, *args: Any, **kwargs: Any) -> Any:
        return self._s.scalar(stmt, *args, **kwargs)


def _pair_fixture(db: Session) -> None:
    db.add_all(
        [
            _row("open_order", quantity=10),
            _row("shipped", quantity=10),
            _row("open_order", order_no="SO-2", quantity=5),
        ]
    )
    db.flush()


def test_brief_and_dashboard_not_received_count_skips_twin(db: Session) -> None:
    from app.services.brief_signals import inbound_not_received_count_stmt

    _pair_fixture(db)
    assert db.scalar(inbound_not_received_count_stmt(None)) == 2


def test_lineup_quarter_summary_does_not_count_twin_as_pipeline(db: Session, monkeypatch) -> None:
    from app.services.commercial_planner import inbound_lineup_quarter as ilq

    _pair_fixture(db)

    async def _ctx(_db):
        return ilq.AttributionContext(open_channel_customer_id=None, open_channel_alias_ids=frozenset())

    async def _planned(_db, **_kw):
        return 0.0

    monkeypatch.setattr(ilq, "load_attribution_context", _ctx)
    monkeypatch.setattr(ilq, "planned_units_for_quarter", _planned)
    out = asyncio.run(ilq.lineup_quarter_summary(_AsyncOverSync(db), plan_quarter="26Q2"))
    # No PO links: everything is unattributed. Before D-0057 wiring this was 25 (10 counted twice).
    assert out["unattributed_units"] == 15.0


def test_eta_shift_scope_skips_twin_without_filters(db: Session, monkeypatch) -> None:
    from app.api.v1.endpoints import shipping

    _pair_fixture(db)
    for i, r in enumerate(db.scalars(select(F)).all(), start=1):
        r.shipment_evidence_line_id = i  # SQLite does not enforce the FK by default
    db.flush()
    captured: dict[str, Any] = {}

    def _capture(fact_scope):
        captured["ids"] = set(db.scalars(select(fact_scope.c.id)).all())
        return select(text("1")), select(text("1"))

    async def _shifts(_db, **_kw):
        return {"ok": True}

    monkeypatch.setattr(shipping, "identity_scope_from_fact_subquery", _capture)
    monkeypatch.setattr(shipping, "compute_eta_shifts", _shifts)
    asyncio.run(
        shipping._eta_shift_metrics(
            _AsyncOverSync(db), sample_limit=5, require_current_incoming=False, today=date(2026, 10, 7)
        )
    )
    ids = captured["ids"]
    states = dict(db.execute(select(F.id, F.line_state).where(F.id.in_(ids))).all())
    assert sorted(states.values()) == ["open_order", "shipped"]


def test_shipping_summary_counts_match_grid_and_report_skipped(db: Session) -> None:
    from app.api.v1.endpoints.shipping import shipping_evidence_summary

    _pair_fixture(db)
    out = asyncio.run(shipping_evidence_summary(db=_AsyncOverSync(db), user=None))
    assert out["total_lines"] == 2
    assert out["open_lines_skipped_shipped_twin"] == 1
    by_state = {b["key"]: b["count"] for b in out["by_line_state"]}
    assert by_state == {"open_order": 1, "shipped": 1}


def test_cpor_intake_mac_does_not_count_twin_twice(db: Session) -> None:
    from app.services.cpor.intake_weighted_mac import _intake_wavg

    common = {"purchase_order_id": 7, "product_id": 3, "unit_price": 100, "est_pod_date": date(2026, 10, 1)}
    db.add_all(
        [
            _row("open_order", quantity=10, **common),
            _row("shipped", quantity=10, **common),
            _row("open_order", order_no="SO-2", quantity=5, **common),
        ]
    )
    db.flush()
    qty, wavg, _as_of, _flags = _intake_wavg(
        db, distributor_id=None, product_id=3, window_start=date(2026, 9, 1), window_end=date(2026, 10, 31)
    )
    assert float(qty) == 15.0  # was 25 with the open twin counted again
    assert float(wavg) == 100.0


# --- D-0065: partial shipments count the remainder ------------------------------------------


def _line_kept_ids(db: Session) -> set[int]:
    return set(db.scalars(select(F.id).where(keep_counted_line(F))).all())


def _counted_by_id(db: Session) -> dict[int, float]:
    stmt, twin = outerjoin_twin_remainder(select(F.id), F)
    return {int(i): float(q or 0) for i, q in db.execute(stmt.add_columns(twin.counted_quantity)).all()}


def _raw_counted_by_id(db: Session) -> dict[int, float]:
    sql = (
        f"SELECT fact_inbound_shipment.id, {TWIN_COUNTED_QTY_SQL} FROM fact_inbound_shipment "
        f"LEFT JOIN ({OPEN_TWIN_REMAINDER_SQL}) twin_rem ON twin_rem.fact_id = fact_inbound_shipment.id "
        f"WHERE {TWIN_KEPT_SQL}"
    )
    return {int(i): float(q or 0) for i, q in db.execute(text(sql)).all()}


@pytest.mark.parametrize(
    ("open_qty", "shipped_qtys", "counted"),
    [
        (10, [6], 4.0),
        (6, [6], None),
        (5, [6], None),
        (10, [3, 4], 3.0),
        (10, [3, 3, 4], None),
    ],
    ids=[
        "open10_shipped6_counts4",
        "open6_shipped6_skipped",
        "open5_shipped6_skipped",
        "two_twins_summed",
        "three_twins_cover",
    ],
)
def test_partial_ship_counts_the_remainder(
    db: Session, open_qty: float, shipped_qtys: list[float], counted: float | None
) -> None:
    open_row = _row("open_order", quantity=open_qty)
    shipped = [_row("shipped", quantity=q) for q in shipped_qtys]
    db.add_all([open_row, *shipped])
    db.flush()
    got = _counted_by_id(db)
    kept = _line_kept_ids(db)
    if counted is None:
        assert open_row.id not in got
        assert open_row.id not in kept
    else:
        assert got[open_row.id] == counted
        assert open_row.id in kept  # still one open line
    for r in shipped:
        assert got[r.id] == float(r.quantity)  # shipped rows are never adjusted
        assert r.id in kept
    assert _raw_counted_by_id(db) == got  # raw SQL text and ORM agree


def test_remainder_sums_only_the_strict_key(db: Session) -> None:
    """Shipped rows of another operating unit, order or tenant do not add to the shipped total."""
    open_row = _row("open_order", quantity=10)
    db.add_all(
        [
            open_row,
            _row("shipped", quantity=4),
            _row("shipped", quantity=50, operating_unit="ACKE"),
            _row("shipped", quantity=50, order_no="SO-2"),
            _row("shipped", quantity=50, tenant_id="other"),
        ]
    )
    db.flush()
    assert _counted_by_id(db)[open_row.id] == 6.0


def test_remainder_null_open_quantity_is_skipped(db: Session) -> None:
    open_row = _row("open_order", quantity=None)
    db.add_all([open_row, _row("shipped", quantity=1)])
    db.flush()
    assert open_row.id not in _line_kept_ids(db)


def test_remainder_never_pairs_blank_keys(db: Session) -> None:
    a = _row("open_order", order_no="", quantity=10)
    b = _row("open_order", item_code=None, quantity=10)
    c = _row("open_order", order_no="SO-9", quantity=7)
    db.add_all([a, b, c, _row("shipped", order_no="", quantity=1), _row("shipped", item_code=None, quantity=1)])
    db.flush()
    got = _counted_by_id(db)
    assert (got[a.id], got[b.id], got[c.id]) == (10.0, 10.0, 7.0)


def test_line_rule_forms_agree(db: Session) -> None:
    rows = [
        _row("open_order", quantity=10),
        _row("shipped", quantity=6),
        _row("open_order", order_no="SO-2", quantity=5),
        _row("shipped", order_no="SO-2", quantity=5),
        _row("open_order", order_no="SO-3", quantity=5),
        _row("arrived", order_no="SO-2", quantity=2),
    ]
    db.add_all(rows)
    db.flush()
    kept = _line_kept_ids(db)
    assert kept == set(_counted_by_id(db)) == set(_raw_counted_by_id(db))
    assert kept == {r.id for r in rows} - {rows[2].id}
    skipped = db.scalar(select(func.count().filter(skipped_open_twin_line(F))).select_from(F))
    assert skipped == 1


def test_remainder_does_not_rewrite_fact_rows(db: Session) -> None:
    db.add_all([_row("open_order", quantity=10), _row("shipped", quantity=6)])
    db.flush()
    before = db.execute(select(F.id, F.line_state, F.quantity, F.updated_at)).all()
    _counted_by_id(db)
    _raw_counted_by_id(db)
    _line_kept_ids(db)
    assert db.execute(select(F.id, F.line_state, F.quantity, F.updated_at)).all() == before


# --- supply overview headline (GOV-008 finding + D-0065) ------------------------------------

_SO_TODAY = "julianday('2026-10-07')"
_SO_WEEK = "julianday('2026-10-05')"


def _supply_headline(db: Session) -> dict[str, Any]:
    """Run the real headline SQL on SQLite. Dates become julian day numbers for date arithmetic."""
    from app.services.supply_overview import _headline_sql

    for col in ("eta_date", "promise_date", "pod_date"):
        db.execute(text(f"UPDATE fact_inbound_shipment SET {col} = julianday({col}) WHERE {col} IS NOT NULL"))
    return dict(db.execute(text(_headline_sql(_SO_TODAY, _SO_WEEK)), {"tenant": "default"}).mappings().one())


def _julian(d: date) -> float:
    return 2440587.5 + (d - date(1970, 1, 1)).days


def test_supply_overview_eta_past_and_oldest_skip_covered_twin(db: Session) -> None:
    db.add_all(
        [
            _row("open_order", quantity=10, eta_date=date(2026, 5, 1)),  # covered twin, oldest: skipped
            _row("shipped", quantity=10, eta_date=date(2026, 9, 1), pod_date=date(2026, 9, 3)),
            _row("open_order", order_no="SO-2", quantity=5, eta_date=date(2026, 6, 1)),
            _row("open_order", order_no="SO-3", quantity=10, eta_date=date(2026, 7, 1)),  # partial: kept
            _row("shipped", order_no="SO-3", quantity=6, eta_date=date(2026, 9, 1), pod_date=date(2026, 9, 2)),
        ]
    )
    db.flush()
    out = _supply_headline(db)
    assert out["eta_past_no_pod_lines"] == 2  # SO-2 and the SO-3 remainder line; 3 with the twin
    assert out["oldest_eta_past"] == _julian(date(2026, 6, 1))  # 2026-05-01 with the twin
    assert out["oldest_days_past_eta"] == (date(2026, 10, 7) - date(2026, 6, 1)).days


def test_supply_overview_overdue_commercial_skips_covered_twin(db: Session) -> None:
    window = {"promise_date": date(2026, 9, 1), "eta_date": date(2026, 10, 20)}
    db.add_all(
        [
            _row("open_order", quantity=10, **window),  # covered twin: skipped
            _row("shipped", quantity=10, status="in_transit", **window),
            _row("open_order", order_no="SO-2", quantity=5, **window),
            _row("open_order", order_no="SO-3", quantity=10, **window),  # partial: one line
            _row("shipped", order_no="SO-3", quantity=6, status="in_transit", **window),
        ]
    )
    db.flush()
    assert _supply_headline(db)["overdue_commercial_lines"] == 2  # 3 with the twin


def test_supply_overview_open_and_pipeline_count_the_remainder(db: Session) -> None:
    db.add_all(
        [
            _row("open_order", quantity=10),
            _row("shipped", quantity=10),
            _row("open_order", order_no="SO-2", quantity=5),
            _row("open_order", order_no="SO-3", quantity=10),
            _row("shipped", order_no="SO-3", quantity=6),
        ]
    )
    db.flush()
    out = _supply_headline(db)
    assert out["pipeline_lines"] == 2
    assert float(out["pipeline_units"]) == 9.0  # 5 + remainder 4 (D-0065); D-0057 gave 5
    assert out["shipped_lines"] == 2
    assert float(out["shipped_units"]) == 16.0
    assert out["open_lines"] == 4
    assert float(out["open_units"]) == 25.0  # 9 pipeline + 16 shipped


# --- readers on D-0065 -------------------------------------------------------------------------


def _partial_fixture(db: Session, **common: Any) -> dict[str, F]:
    rows = {
        "covered_open": _row("open_order", quantity=10, **common),
        "covered_shipped": _row("shipped", quantity=10, **common),
        "partial_open": _row("open_order", order_no="SO-3", quantity=10, **common),
        "partial_shipped": _row("shipped", order_no="SO-3", quantity=6, **common),
        "plain_open": _row("open_order", order_no="SO-2", quantity=5, **common),
    }
    db.add_all(list(rows.values()))
    db.flush()
    return rows


def test_brief_count_keeps_partial_line(db: Session) -> None:
    from app.services.brief_signals import inbound_not_received_count_stmt

    _partial_fixture(db)
    assert db.scalar(inbound_not_received_count_stmt(None)) == 4  # D-0057 gave 3


def test_lineup_quarter_summary_counts_remainder(db: Session, monkeypatch) -> None:
    from app.services.commercial_planner import inbound_lineup_quarter as ilq

    _partial_fixture(db)

    async def _ctx(_db):
        return ilq.AttributionContext(open_channel_customer_id=None, open_channel_alias_ids=frozenset())

    async def _planned(_db, **_kw):
        return 0.0

    monkeypatch.setattr(ilq, "load_attribution_context", _ctx)
    monkeypatch.setattr(ilq, "planned_units_for_quarter", _planned)
    out = asyncio.run(ilq.lineup_quarter_summary(_AsyncOverSync(db), plan_quarter="26Q2"))
    assert out["unattributed_units"] == 25.0  # shipped 10 + 6, open 5, remainder 4; D-0057 gave 21


def test_eta_shift_scope_keeps_partial_line(db: Session, monkeypatch) -> None:
    from app.api.v1.endpoints import shipping

    rows = _partial_fixture(db)
    for i, r in enumerate(rows.values(), start=1):
        r.shipment_evidence_line_id = i
    db.flush()
    captured: dict[str, Any] = {}

    def _capture(fact_scope):
        captured["ids"] = set(db.scalars(select(fact_scope.c.id)).all())
        return select(text("1")), select(text("1"))

    async def _shifts(_db, **_kw):
        return {"ok": True}

    monkeypatch.setattr(shipping, "identity_scope_from_fact_subquery", _capture)
    monkeypatch.setattr(shipping, "compute_eta_shifts", _shifts)
    asyncio.run(
        shipping._eta_shift_metrics(
            _AsyncOverSync(db), sample_limit=5, require_current_incoming=False, today=date(2026, 10, 7)
        )
    )
    assert captured["ids"] == {r.id for k, r in rows.items() if k != "covered_open"}


def test_shipping_summary_counts_partial_line_once(db: Session) -> None:
    from app.api.v1.endpoints.shipping import shipping_evidence_summary

    _partial_fixture(db)
    out = asyncio.run(shipping_evidence_summary(db=_AsyncOverSync(db), user=None))
    assert out["total_lines"] == 4
    assert out["open_lines_skipped_shipped_twin"] == 1
    assert {b["key"]: b["count"] for b in out["by_line_state"]} == {"open_order": 2, "shipped": 2}


def test_shipping_kpi_quantity_counts_remainder(db: Session) -> None:
    from app.api.v1.endpoints.shipping import _aggregate_currency_qty_lines

    _partial_fixture(db, amount=100, currency_code="USD")
    by_currency, qty, lines = asyncio.run(_aggregate_currency_qty_lines(_AsyncOverSync(db), {}))
    assert qty == 25.0  # shipped 10 + 6, open 5, remainder 4; D-0057 gave 21
    assert lines == 4
    # Value: shipped 100 + 100, plain open 100, partial open pro-rata 100 x 4 / 10 = 40.
    # Round 2 (no amount for the partial line) gave 300; the full stored amount would give 400.
    assert by_currency == [{"currency_code": "USD", "amount": 340.0}]


def test_cpor_intake_mac_weights_by_remainder(db: Session) -> None:
    from app.services.cpor.intake_weighted_mac import _intake_wavg

    common = {"purchase_order_id": 7, "product_id": 3, "est_pod_date": date(2026, 10, 1)}
    db.add_all(
        [
            _row("open_order", quantity=10, unit_price=100, **common),
            _row("shipped", quantity=6, unit_price=200, **common),
        ]
    )
    db.flush()
    qty, wavg, _as_of, _flags = _intake_wavg(
        db, distributor_id=None, product_id=3, window_start=date(2026, 9, 1), window_end=date(2026, 10, 31)
    )
    assert float(qty) == 10.0  # shipped 6 + remainder 4 (D-0057 gave 6, no rule 16)
    assert float(wavg) == 160.0  # (6*200 + 4*100) / 10


def test_cpor_disti_cost_proxy_weights_by_remainder(db: Session) -> None:
    from app.services.cpor.intake_weighted_mac import _disti_cost_proxy_wavg

    common = {"purchase_order_id": 7, "product_id": 3, "distributor_id": 4}
    db.add_all(
        [
            _row("open_order", quantity=10, unit_price=100, **common),
            _row("shipped", quantity=6, unit_price=200, pod_date=date(2026, 9, 2), **common),
        ]
    )
    db.flush()
    wavg, max_pod, _flags = _disti_cost_proxy_wavg(db, distributor_id=4, product_id=3)
    assert float(wavg) == 160.0  # D-0057 gave 200, no rule 137.5
    assert max_pod == date(2026, 9, 2)


# --- round 3: pro-rata value (Warren 2026-10-07, N-0071) -------------------------------------


def _amounts_by_id(db: Session) -> dict[int, float | None]:
    stmt, twin = outerjoin_twin_remainder(select(F.id), F)
    rows = db.execute(stmt.add_columns(twin.counted_amount)).all()
    return {int(i): (None if a is None else float(a)) for i, a in rows}


def _raw_amounts_by_id(db: Session) -> dict[int, float | None]:
    sql = (
        f"SELECT fact_inbound_shipment.id, {TWIN_COUNTED_AMOUNT_SQL} FROM fact_inbound_shipment "
        f"LEFT JOIN ({OPEN_TWIN_REMAINDER_SQL}) twin_rem ON twin_rem.fact_id = fact_inbound_shipment.id "
        f"WHERE {TWIN_KEPT_SQL}"
    )
    return {int(i): (None if a is None else float(a)) for i, a in db.execute(text(sql)).all()}


@pytest.mark.parametrize(
    ("open_qty", "shipped_qtys", "amount", "counted"),
    [
        (10, [6], 1000, 400.0),
        (10, [], 1000, 1000.0),
        (10, [3, 4], 1000, 300.0),
        (6, [6], 1000, None),
        (5, [6], 1000, None),
        (10, [6], None, None),
    ],
    ids=[
        "open10_shipped6_amount1000_counts400",
        "fully_open_counts_its_amount",
        "two_twins_summed_counts300",
        "covered_skipped",
        "over_covered_skipped",
        "partial_without_amount_is_null",
    ],
)
def test_partial_line_value_is_pro_rata(
    db: Session, open_qty: float, shipped_qtys: list[float], amount: float | None, counted: float | None
) -> None:
    open_row = _row("open_order", quantity=open_qty, amount=amount)
    shipped = [_row("shipped", quantity=q, amount=q * 100) for q in shipped_qtys]
    db.add_all([open_row, *shipped])
    db.flush()
    got = _amounts_by_id(db)
    covered = bool(shipped_qtys) and open_qty <= sum(shipped_qtys)
    if covered:
        assert open_row.id not in got  # skipped line: not in the kept set, so it adds 0
    else:
        assert got[open_row.id] == counted
    for r in shipped:
        assert got[r.id] == float(r.amount)  # shipped rows keep their stored amount
    assert _raw_amounts_by_id(db) == got  # raw SQL text and ORM agree


def test_covered_line_counted_amount_is_zero_without_kept_filter(db: Session) -> None:
    from app.services.shipment_strict_pair import twin_remainder

    open_row = _row("open_order", quantity=6, amount=600)
    db.add_all([open_row, _row("shipped", quantity=6, amount=600)])
    db.flush()
    twin = twin_remainder(F)
    amt = db.scalar(
        select(twin.counted_amount)
        .select_from(F)
        .outerjoin(twin.subquery, twin.onclause)
        .where(F.id == open_row.id)
    )
    assert float(amt) == 0.0


def test_shipping_kpi_value_is_pro_rata(db: Session) -> None:
    from app.api.v1.endpoints.shipping import _aggregate_currency_qty_lines

    db.add_all(
        [
            _row("open_order", order_no="SO-3", quantity=10, amount=1000, currency_code="USD"),
            _row("shipped", order_no="SO-3", quantity=6, amount=600, currency_code="USD"),
            _row("open_order", quantity=10, amount=1000, currency_code="USD"),  # covered: skipped
            _row("shipped", quantity=10, amount=1000, currency_code="USD"),
            _row("open_order", order_no="SO-2", quantity=5, amount=500, currency_code="EUR"),  # fully open
        ]
    )
    db.flush()
    by_currency, qty, lines = asyncio.run(_aggregate_currency_qty_lines(_AsyncOverSync(db), {}))
    # USD: shipped 600 + 1000, partial 1000 x 4 / 10 = 400. The full stored amount would give 2600.
    assert {c["currency_code"]: c["amount"] for c in by_currency} == {"USD": 2000.0, "EUR": 500.0}
    assert qty == 25.0
    assert lines == 4


# --- round 3: the five readers moved from D-0057 to the remainder ----------------------------


def _create(db: Session, *models: Any) -> None:
    for m in models:
        m.__table__.create(db.get_bind(), checkfirst=True)


_SHIP_DAY = date(2026, 9, 7)  # a Monday


def _channel_fixture(db: Session) -> None:
    _partial_fixture(db, distributor_id=4, product_id=3, ship_confirm_date=_SHIP_DAY)


def test_channel_ops_movement_shipped_units_count_remainder(db: Session, monkeypatch) -> None:
    from app.api.v1.endpoints import channel_ops
    from app.models.facts import FactSalesSellout

    _create(db, FactSalesSellout)
    _channel_fixture(db)

    async def _no_obs(_db, **_kw):
        return []

    monkeypatch.setattr(channel_ops, "latest_woc_observations", _no_obs)
    out = asyncio.run(channel_ops.channel_ops_movement_lens(db=_AsyncOverSync(db), user=None, weeks=13))
    assert out["headlines"]["shipped_units"] == 25.0  # shipped 10 + 6, open 5, remainder 4; D-0057 gave 21


def test_channel_ops_weekly_flow_counts_remainder(db: Session, monkeypatch) -> None:
    from app.api.v1.endpoints import channel_ops
    from app.models.facts import FactSalesSellout

    _create(db, FactSalesSellout)
    _channel_fixture(db)
    # SQLite has no extract('isodow'); every fixture date is already a Monday.
    monkeypatch.setattr(channel_ops, "_iso_week_start_expr", lambda col: col)
    out = asyncio.run(channel_ops._cover_weekly_flow(_AsyncOverSync(db), "default"))
    assert sum(p["shipped"] for p in out["points"]) == 25.0  # D-0057 gave 21


def test_channel_ops_cover_inbound_open_counts_remainder(db: Session, monkeypatch) -> None:
    from types import SimpleNamespace

    from app.api.v1.endpoints import channel_ops
    from app.models.dimensions import DimProduct

    _create(db, DimProduct)
    _channel_fixture(db)
    obs = SimpleNamespace(
        distributor_id=4, product_id=3, weeks_of_cover=5.0, cover_as_of_date=date(2026, 10, 1),
        derived_stock=10.0, weekly_velocity=2.0, replenishment_flag=None,
    )

    async def _obs(_db, **_kw):
        return [obs]

    async def _flow(_db, _tid, weeks=13):
        return {"points": [], "sell_out_through": None, "shipped_through": None}

    monkeypatch.setattr(channel_ops, "latest_woc_observations", _obs)
    monkeypatch.setattr(channel_ops, "_cover_weekly_flow", _flow)
    out = asyncio.run(channel_ops.channel_ops_cover_distribution(db=_AsyncOverSync(db), user=None))
    assert out["items"][0]["inbound_open"] == 25.0  # D-0057 gave 21


def test_net_requirement_in_transit_counts_remainder(db: Session) -> None:
    from app.services.lineup.net_requirement import _in_transit_by_dist_product

    _partial_fixture(db, distributor_id=4, product_id=3, purchase_order_id=7)
    db.add(
        _row("shipped", order_no="SO-8", quantity=50, distributor_id=4, product_id=3, purchase_order_id=7,
             pod_date=date(2026, 9, 1))  # landed: not in transit
    )
    db.flush()
    out = asyncio.run(_in_transit_by_dist_product(_AsyncOverSync(db)))
    assert out == {(4, 3): 25.0}  # shipped-not-landed 10 + 6, open 5, remainder 4; D-0057 gave 21


def test_1h_hint_counts_remainder(db: Session) -> None:
    from app.services.commercial_planner.lineup_bulk_rederivation import _shipment_q1_hint

    _partial_fixture(db, product_id=3, ship_confirm_date=date(2026, 2, 2))
    hint = _shipment_q1_hint(db, product_id=3, customer_id=None, q1_start=date(2026, 1, 1), q2_start=date(2026, 4, 1))
    assert hint == 25.0  # D-0057 gave 21


def test_po_auto_link_open_order_units_count_remainder(db: Session, monkeypatch) -> None:
    from app.models.commercial_lineup import CommercialLineupCase, CommercialLineupCasePo, CommercialLineupLine
    from app.models.dimensions import DimProduct
    from app.services.commercial_planner import lineup_po_auto_link as al

    _create(db, DimProduct, CommercialLineupCase, CommercialLineupCasePo, CommercialLineupLine, al.PurchaseOrder,
            al.CommercialLineupPoAutoLinkDismiss)
    db.add(DimProduct(id=3, sku="SKU-3", name="Product Three"))
    db.add(al.PurchaseOrder(id=7, po_number_raw="PO-7", po_number_norm="PO-7"))
    db.add(CommercialLineupCase(id=1, commercial_status="po_issued", inferred_period_start=date(2026, 7, 1),
                                period_label="26Q3", product_line="PC"))
    db.flush()
    db.add(CommercialLineupLine(case_id=1, product_id=3, customer_id=None, quantity_units=100))
    _partial_fixture(db, product_id=3, purchase_order_id=7, crad_date=date(2026, 8, 3))

    async def _open_channel(_db):
        return None, frozenset()

    monkeypatch.setattr(al, "get_open_channel_canonical_and_aliases", _open_channel)
    out = asyncio.run(
        al._po_auto_link_proposals_inner(
            _AsyncOverSync(db), period=None, customer_id=None, confidence=None, limit=500, include_dismissed=False
        )
    )
    assert len(out["proposals"]) == 1, out
    p = out["proposals"][0]
    assert p["total_open_order_units"] == 9.0  # open 5 + remainder 4; D-0057 gave 5
    assert p["total_shipped_units"] == 16.0


def test_po_reconciliation_pipeline_counts_remainder(db: Session, monkeypatch) -> None:
    from datetime import datetime, timezone

    from app.models.commercial_lineup import CommercialLineupCase, CommercialLineupCasePo, CommercialLineupLine
    from app.models.dimensions import DimCustomer, DimProduct
    from app.services.commercial_planner import lineup_po_reconciliation as rec

    ev = rec.EV
    _create(db, DimProduct, DimCustomer, CommercialLineupCase, CommercialLineupCasePo, CommercialLineupLine,
            rec.PurchaseOrder, rec.CommercialSkuAssumption, ev)
    db.add(DimProduct(id=3, sku="SKU-3", name="Product Three"))
    db.add(rec.PurchaseOrder(id=7, po_number_raw="PO-7", po_number_norm="PO-7"))
    case = CommercialLineupCase(id=1, commercial_status="po_issued", currency_code="ZAR", product_line="PC")
    db.add(case)
    db.flush()
    db.add(CommercialLineupCasePo(case_id=1, purchase_order_id=7))
    db.add(CommercialLineupLine(case_id=1, product_id=3, customer_id=None, quantity_units=100, row_status="active"))
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    specs = [
        ("open_order", "SO-1", 10), ("shipped", "SO-1", 10),  # covered: skipped
        ("open_order", "SO-3", 10), ("shipped", "SO-3", 6),  # partial: remainder 4
        ("open_order", "SO-2", 5),  # plain open
    ]
    for n, (state, order_no, qty) in enumerate(specs, start=1):
        db.add(
            ev(
                id=n, line_identity_key=f"L{n}", import_job_id=1, source_key=f"k{n}", source_row_hash="h",
                valid_from=now, observed_at=now, source_row_number=n, report_type="test", line_state=state,
                raw_source_row={}, operating_unit="ACZA", order_no=order_no, item_code="90NX0001", quantity=qty,
                purchase_order_id=7, product_id=3, product_resolution_status="resolved",
                distributor_resolution_status="resolved",
            )
        )
    db.flush()

    async def _open_channel(_db):
        return None, frozenset()

    monkeypatch.setattr(rec, "get_open_channel_canonical_and_aliases", _open_channel)
    out = asyncio.run(rec._reconcile_case_inner(_AsyncOverSync(db), case))
    pipeline = sum(float(p.get("pipeline_units") or 0) for p in out["products"])
    assert pipeline == 9.0  # open 5 + remainder 4; D-0057 gave 5


def test_shipping_grid_still_to_ship(db: Session) -> None:
    from app.api.v1.endpoints.shipping import _fact_to_dict, _still_to_ship_by_id
    from app.services.grid_fields import GRID_FIELDS, grid_field_items

    rows = _partial_fixture(db)
    got = asyncio.run(_still_to_ship_by_id(_AsyncOverSync(db), list(rows.values())))
    assert got == {
        rows["covered_open"].id: 0.0,  # never listed by the grid (keep_counted_line); 0 if asked
        rows["partial_open"].id: 4.0,
        rows["plain_open"].id: 5.0,
    }
    payload = _fact_to_dict(
        rows["partial_open"], product_name=None, product_sku=None, distributor_name=None, distributor_code=None,
        customer_name=None, customer_code=None, include_raw_row=False, still_to_ship=got[rows["partial_open"].id],
    )
    assert payload["quantity"] == 10.0  # stored quantity unchanged
    assert payload["still_to_ship"] == 4.0
    items = {it["field"]: it for it in grid_field_items(GRID_FIELDS["inbound-shipments"])}
    assert items["still_to_ship"]["label"] == "Still to ship"
    assert items["still_to_ship"]["group"] == "fact"
