"""Each promotion-planner path reads customer sell-through and nothing else (Warren 2026-11-19).

Driven with a capturing fake session (no database). For every path the compiled statements are
captured and checked: they touch ``fact_customer_sellthrough`` and none of the dropped sources
(line-ups, SKU assumptions, demand forecast, listings, competitor prices, distributor cover,
shipments, buy plan, distributor sell-out, earlier cases). A figure sell-through does not carry
comes back as ``None`` with a reason, never as a filled-in value or a zero.

Paths (numbers follow section 1.4 of the live screen audit):
1 products proposed · 2 price for reserve · 3 planned reservation · 4 expected units ·
5 listing price · 6 competitor price · 7 stock health · 8 cost (MAC) · 9 earlier cases ·
10 aged-stock Promote price.

Generic platform rule: nothing here names a customer, retailer, distributor, site or product.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import app.services.cpor.promo_plan_builder as builder
import pytest
from app.services.cpor import planner_sellthrough as st
from app.services.cpor.intake_weighted_mac import suggest_sellthrough_mac
from app.services.store_dc import stock_actions as actions
from sqlalchemy.dialects import postgresql

SELLTHROUGH = "fact_customer_sellthrough"
DROPPED = (
    "commercial_lineup_case",
    "commercial_lineup_line",
    "fact_lineup_plan_item",
    "commercial_sku_assumption",
    "fact_demand_forecast",
    "customer_listing",
    "listing_observation",
    "fact_competitor_price",
    "fact_competitor_mapping",
    "dim_competitor_product",
    "dim_competitor_brand",
    "weeks_of_cover_observation",
    "fact_inbound_shipment",
    "fact_buy_plan",
    "fact_sales_sellout",
    "cpor_case_line",
    "cpor_case ",
    "from cpor_case",
)
CUTOFF = date(2026, 1, 5)
LATEST = date(2026, 2, 23)


def _sql(stmt: Any) -> str:
    return str(stmt.compile(dialect=postgresql.dialect())).lower()


class _Rows(list):
    def all(self) -> list[Any]:
        return list(self)

    def first(self) -> Any:
        return self[0] if self else None

    def one(self) -> Any:
        return self[0]

    def scalars(self) -> _Rows:
        return self

    def unique(self) -> _Rows:
        return self

    def scalar(self) -> Any:
        return self[0][0] if self else None


def _classify(sql: str) -> str:
    if "distinct on" in sql and "unit_sell_price" in sql:
        return "price"
    if "distinct on" in sql and "unit_mac" in sql:
        return "cost"
    if "select distinct fact_customer_sellthrough.product_id" in sql:
        return "products"
    if "select distinct fact_customer_sellthrough.period_start_date" in sql:
        return "cutoff"
    if "max(fact_customer_sellthrough.period_start_date)" in sql:
        return "latest"
    if (
        "fact_customer_sellthrough.site_label" in sql
        and "fact_customer_sellthrough.period_grain" in sql
    ):
        return "window"
    return "other"


class FakeSession:
    """Captures every statement. ``data`` maps a statement kind to the rows it returns."""

    def __init__(self, data: dict[str, list[tuple]] | None = None) -> None:
        self.statements: list[str] = []
        self.data = data or {}

    def _run(self, stmt: Any) -> _Rows:
        sql = _sql(stmt)
        self.statements.append(sql)
        return _Rows(self.data.get(_classify(sql), []))

    def execute(self, stmt: Any, *_a: Any, **_k: Any) -> _Rows:
        return self._run(stmt)

    def scalars(self, stmt: Any, *_a: Any, **_k: Any) -> _Rows:
        return self._run(stmt)

    def scalar(self, stmt: Any, *_a: Any, **_k: Any) -> Any:
        rows = self._run(stmt)
        return rows[0][0] if rows and isinstance(rows[0], tuple) else (rows[0] if rows else None)

    def get(self, *_a: Any, **_k: Any) -> None:
        return None


def _assert_sellthrough_only(session: FakeSession, *, must_read: bool = True) -> None:
    joined = "\n".join(session.statements)
    if must_read:
        assert SELLTHROUGH in joined
    for table in DROPPED:
        assert table not in joined, f"dropped source still queried: {table.strip()}"


def _book_data(
    *, price: float | None = 250.0, mac: float | None = 100.0, cost: float | None = 120.0
) -> dict:
    window = [
        (date(2026, 2, 9), "week", "week", 10.0, None, None),
        (date(2026, 2, 16), "week", "week", 20.0, None, None),
        (LATEST, "week", "week", 30.0, 90.0, None),
    ]
    # window rows carry the product id first
    window = [(7, *row) for row in window]
    return {
        "cutoff": [(CUTOFF,), (date(2026, 2, 9),)],
        "window": window,
        "price": [(7, LATEST, price)] if price is not None else [],
        "cost": [(7, LATEST, mac, cost)] if (mac is not None or cost is not None) else [],
        "products": [(7,), (9,)],
    }


# 1. which products are proposed ---------------------------------------------------------------


def test_products_proposed_are_the_customers_own_sellthrough_products():
    data = _book_data()
    session = FakeSession(data)
    specs, source = builder.product_specs_for_customer_period(
        session, customer_id=3, period_label="2026Q2", tenant_id="tenant-a"
    )
    assert source == builder.PRODUCT_SET_SELLTHROUGH
    assert [s["product_id"] for s in specs] == [7, 9]
    assert all(s["seed_line_id"] is None and s["distributor_id"] is None for s in specs)
    _assert_sellthrough_only(session)


def test_product_proposal_reads_only_the_product_set_and_leaves_price_to_the_line():
    session = FakeSession(_book_data(price=250.0))
    specs, _ = builder.product_specs_for_customer_period(
        session, customer_id=3, period_label="2026Q2"
    )
    assert all(s["srp"] is None and s["estimate_qty"] == 0.0 for s in specs)
    kinds = {_classify(sql) for sql in session.statements}
    assert kinds == {
        "cutoff",
        "products",
    }  # no price, cost or run-rate read for the proposal itself


def test_no_sellthrough_means_no_proposed_products():
    session = FakeSession({})
    specs, source = builder.product_specs_for_customer_period(
        session, customer_id=3, period_label="2026Q2"
    )
    assert specs == [] and source is None
    _assert_sellthrough_only(session)


def test_earlier_cases_and_lineups_are_not_a_product_source():
    assert not hasattr(builder, "_specs_from_lineup")
    assert not hasattr(builder, "_specs_from_customer_history")
    assert not hasattr(builder, "PRODUCT_SET_LINEUP")
    assert not hasattr(builder, "PRODUCT_SET_CUSTOMER_HISTORY")


# 2 + 3. planned reservation: no line-up, no SKU assumption -----------------------------------


def test_planned_reservation_reads_nothing_and_says_not_available():
    session = FakeSession({})
    out = builder.derive_planned_reservation_sync(session, period_label="2026Q2", limit=50)
    assert session.statements == []
    assert out["available"] is False
    assert out["planned_reservation_usd"] is None
    assert out["planned_revenue_usd"] is None
    assert out["reason"] == builder.RESERVATION_NOT_AVAILABLE
    assert out["from_lineup_derived"] is False
    assert out["planned_line_count"] == 0


def test_srp_evidence_and_lineup_price_helpers_are_gone():
    assert not hasattr(builder, "_srp_evidence_by_product_sync")
    assert not hasattr(builder, "_forecast_volume_sync")


# 4. expected units -----------------------------------------------------------------------------


def test_expected_units_are_the_sellthrough_run_rate_times_the_horizon():
    session = FakeSession(_book_data())
    out = builder.sellthrough_volume_sync(
        session, product_id=7, customer_id=3, horizon_weeks=13, tenant_id="tenant-a"
    )
    assert out["source"] == st.VOLUME_SOURCE
    assert out["weekly_run_rate"] == pytest.approx(20.0)
    assert out["forecast_units"] == pytest.approx(20.0 * 13)
    assert out["available"] is True
    _assert_sellthrough_only(session)


def test_expected_units_missing_when_the_customer_has_no_sellthrough():
    session = FakeSession({})
    out = builder.sellthrough_volume_sync(session, product_id=7, customer_id=3, horizon_weeks=13)
    assert out["forecast_units"] is None and out["available"] is False
    assert out["reason"] in {st.NO_SELLTHROUGH, st.NO_WEEKLY}
    _assert_sellthrough_only(session, must_read=False)


def test_expected_units_without_a_customer_read_nothing():
    session = FakeSession({})
    out = builder.sellthrough_volume_sync(session, product_id=7, customer_id=None, horizon_weeks=13)
    assert session.statements == []
    assert out["forecast_units"] is None and out["reason"] == st.NO_CUSTOMER


# 5 + 6 + 7. line evidence: listing, competitor, cover ---------------------------------------


def _evidence(session: FakeSession, monkeypatch: pytest.MonkeyPatch, **kw: Any) -> dict[str, Any]:
    monkeypatch.setattr(builder, "_customer_slow_multiple", lambda *_a, **_k: 2.0)
    return builder.load_promotion_line_evidence(
        session,
        customer_id=3,
        product_id=7,
        distributor_id=11,
        target_weeks=4.0,
        tenant_id="tenant-a",
        **kw,
    )


def test_line_evidence_does_not_query_listing_competitor_or_distributor_cover(monkeypatch):
    session = FakeSession(_book_data())
    ev = _evidence(session, monkeypatch)
    _assert_sellthrough_only(session)
    assert ev["listing"]["last_observed_price"] is None
    assert ev["listing"]["data_unavailable"] is True
    assert ev["competitor_price"]["price"] is None
    assert ev["competitor_price"]["data_unavailable"] is True
    assert ev["competitor_price"]["prices"] == []
    assert ev["observed_cover"]["distributor_product_weeks"] is None
    assert ev["read_failed"] is False


def test_stock_health_is_sellthrough_soh_over_the_run_rate(monkeypatch):
    session = FakeSession(_book_data())
    ev = _evidence(session, monkeypatch)
    cover = ev["observed_cover"]
    assert cover["soh_units"] == pytest.approx(90.0)
    assert cover["weekly_rate"] == pytest.approx(20.0)
    assert cover["weeks"] == pytest.approx(4.5)
    assert cover["window_weeks"] == st.run_rate_weeks()
    assert cover["flag"] == "observed_cover"  # 4.5 weeks < 2 x the 4 week target


def test_stock_health_flags_high_cover_against_the_target(monkeypatch):
    data = _book_data()
    data["window"] = [(7, LATEST, "week", "week", 1.0, 90.0, None)]
    session = FakeSession(data)
    ev = _evidence(session, monkeypatch)
    assert ev["observed_cover"]["weeks"] == pytest.approx(90.0)
    assert ev["observed_cover"]["flag"] == "high_cover"


def test_stock_health_unavailable_without_sellthrough(monkeypatch):
    session = FakeSession({})
    ev = _evidence(session, monkeypatch)
    assert ev["observed_cover"]["weeks"] is None
    assert ev["observed_cover"]["flag"] is None
    assert ev["observed_cover"]["cover_reason"] in {st.NO_SELLTHROUGH, st.NO_WEEKLY}
    _assert_sellthrough_only(session, must_read=False)


def test_competitor_price_helper_is_not_called_by_the_planner(monkeypatch):
    def boom(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("competitor prices are not a planner source")

    monkeypatch.setattr(builder, "_approved_competitor_prices", boom)
    ev = _evidence(FakeSession(_book_data()), monkeypatch)
    assert ev["competitor_price"]["data_unavailable"] is True


# 8. cost ---------------------------------------------------------------------------------------


def test_cost_is_sellthrough_unit_mac_for_that_customer_and_product():
    session = FakeSession(_book_data(mac=100.0, cost=120.0))
    sug = suggest_sellthrough_mac(session, customer_id=3, product_id=7, tenant_id="tenant-a")
    assert float(sug.cost_basis) == pytest.approx(100.0)
    assert sug.cost_source == "cst_reported"
    assert sug.evidence["composer"] == "sellthrough_mac"
    assert sug.evidence["field_used"] == "unit_mac"
    assert sug.evidence["as_of"] == LATEST.isoformat()
    assert sug.flags == []
    _assert_sellthrough_only(session)


def test_cost_falls_back_to_unit_cost_and_is_missing_without_either():
    session = FakeSession(_book_data(mac=None, cost=120.0))
    sug = suggest_sellthrough_mac(session, customer_id=3, product_id=7)
    assert float(sug.cost_basis) == pytest.approx(120.0)
    assert sug.evidence["field_used"] == "unit_cost"

    empty = suggest_sellthrough_mac(FakeSession({}), customer_id=3, product_id=7)
    assert empty.cost_basis is None
    assert empty.cost_source is None
    assert "no_sellthrough_cost" in empty.flags


def test_cost_does_not_read_shipments_buy_plan_sellout_or_lineups():
    session = FakeSession(_book_data())
    suggest_sellthrough_mac(session, customer_id=3, product_id=7)
    _assert_sellthrough_only(session)


# 4 + 8 + 9. the whole draft ------------------------------------------------------------------


def _draft(monkeypatch: pytest.MonkeyPatch, session: FakeSession, **kw: Any) -> dict[str, Any]:
    monkeypatch.setattr(builder, "_customer_slow_multiple", lambda *_a, **_k: 2.0)
    monkeypatch.setattr(
        builder, "resolve_target_cover_weeks_sync", lambda *_a, **_k: (4.0, "customer")
    )
    import app.services.budget_ledger as ledger

    monkeypatch.setattr(ledger, "used_usd", lambda *_a, **_k: None)
    return builder.build_promo_plan_draft(
        session, customer_id=3, period_label="2026Q2", tenant_id="tenant-a", **kw
    )


class _DraftSession(FakeSession):
    def _run(self, stmt: Any) -> _Rows:
        sql = _sql(stmt)
        if "cpor_case_line.ttl_support_usd" in sql:
            self.statements.append(sql)
            return _Rows([(0, 0)])
        return super()._run(stmt)


def _assert_draft_sources(session: FakeSession) -> None:
    joined = "\n".join(
        s
        for s in session.statements
        if "cpor_case_line.ttl_support_usd" not in s  # spend already drawn
    )
    assert SELLTHROUGH in joined
    for table in DROPPED:
        assert table not in joined, f"dropped source still queried: {table.strip()}"


def test_draft_rows_carry_only_sellthrough_price_cost_stock_and_units(monkeypatch):
    session = _DraftSession(_book_data())
    out = _draft(monkeypatch, session)
    _assert_draft_sources(session)
    rows = {r["product_id"]: r for r in out["lines"]}
    seven = rows[7]
    assert seven["srp"] == pytest.approx(250.0)
    assert seven["suggested_cost_basis"] == pytest.approx(100.0)
    assert seven["suggested_cost_source"] == "cst_reported"
    assert seven["volume"]["forecast_units"] == pytest.approx(20.0 * 13)
    assert seven["promotion_evidence"]["observed_cover"]["soh_units"] == pytest.approx(90.0)
    assert seven["quantity_evidence"]["history_units"] is None
    assert seven["quantity_evidence"]["fallback"] is None
    # product 9 has no sell-through figures at all: missing, with reasons, never filled
    nine = rows[9]
    assert nine["srp"] is None
    assert nine["suggested_cost_basis"] is None
    assert nine["volume"]["forecast_units"] is None
    assert nine["suggested_estimate_qty"] is None
    assert nine["missing"]["price"] in {st.NO_PRICE, st.NO_SELLTHROUGH}
    assert nine["missing"]["cost"] in {st.NO_COST, st.NO_SELLTHROUGH}
    assert nine["missing"]["units"] in {st.NO_WEEKLY, st.NO_SELLTHROUGH}
    assert rows[7]["missing"]["price"] is None and rows[7]["missing"]["cost"] is None
    assert out["comparables"]["count"] == 0
    assert out["product_set_source"] == builder.PRODUCT_SET_SELLTHROUGH


def test_draft_budget_check_says_the_reservation_is_not_available(monkeypatch):
    out = _draft(monkeypatch, _DraftSession(_book_data()))
    money = out["budget_check"]["tracks"]["money"]
    assert money["status"] == "not_available"
    assert money["planned_reservation_usd"] is None
    assert money["remaining_usd"] is None
    assert out["budget_check"]["planned_from_lineup_derived"] is False
    assert out["budget_check"]["over_budget_warn"] is False
    assert out["budget_check"]["create_blocked"] is False
    assert (
        out["budget_check"]["reservation_not_available_reason"] == builder.RESERVATION_NOT_AVAILABLE
    )


def test_an_operator_entered_reservation_is_still_honoured(monkeypatch):
    session = _DraftSession(_book_data())
    out = _draft(monkeypatch, session, planned_support_usd=1000.0)
    money = out["budget_check"]["tracks"]["money"]
    assert money["status"] == "ok"
    assert money["planned_reservation_usd"] == pytest.approx(1000.0)


def test_suggested_quantity_blends_run_rate_and_cover_surplus_only():
    out = builder.blend_cip_quantity(
        forecast_units=260.0,
        cover_surplus_units=60.0,
        spec_units=0.0,
    )
    assert out["suggested_estimate_qty"] == pytest.approx(160.0)
    assert [s["source"] for s in out["signals"]] == ["forecast", "cover"]
    assert out["history_units"] is None
    assert out["fallback"] is None


def test_suggested_quantity_is_missing_when_sellthrough_gives_no_units():
    out = builder.blend_cip_quantity(forecast_units=None, cover_surplus_units=None, spec_units=0.0)
    assert out["suggested_estimate_qty"] is None
    assert out["forecast_units"] is None


def test_an_existing_line_estimate_is_not_a_sellthrough_quantity_fallback():
    out = builder.blend_cip_quantity(forecast_units=None, cover_surplus_units=None, spec_units=40.0)
    assert out["suggested_estimate_qty"] is None
    assert out["fallback"] is None
    assert out["unavailable_reason"] == "no_sellthrough_units"


def test_reported_zero_sales_is_available_and_does_not_reuse_a_case_estimate():
    out = builder.blend_cip_quantity(forecast_units=0.0, cover_surplus_units=None, spec_units=40.0)
    assert out["suggested_estimate_qty"] == 0.0
    assert out["unavailable_reason"] is None


@pytest.mark.parametrize("price,expected", [(250.0, 250.0), (None, None)])
def test_recompute_ignores_seed_or_payload_prices_and_estimates(monkeypatch, price, expected):
    session = _DraftSession(_book_data(price=price))
    out = _draft(
        monkeypatch,
        session,
        line_specs=[
            {
                "product_id": 7,
                "seed_line_id": 123,
                "srp": 9999.0,
                "estimate_qty": 9999.0,
            }
        ],
    )
    row = out["lines"][0]
    assert row["srp"] == expected
    assert row["srp_source"] == (st.SOURCE_LABEL if expected is not None else None)
    assert row["suggested_estimate_qty"] == pytest.approx(
        135.0
    )  # mean of 260 expected and 10 surplus
    _assert_draft_sources(session)


def test_price_and_cost_queries_are_weekly_and_scoped_to_tenant_customer_and_product():
    session = FakeSession(_book_data())
    st.read_book(
        session, tenant_id="tenant-a", customer_id=3, product_ids=[7], want=("price", "cost")
    )
    assert len(session.statements) == 2
    for sql in session.statements:
        where = sql.split("where", 1)[1]
        assert "fact_customer_sellthrough.tenant_id =" in where
        assert "fact_customer_sellthrough.customer_id =" in where
        assert "fact_customer_sellthrough.product_id in" in where
        assert "fact_customer_sellthrough.period_grain" in where
        assert "fact_customer_sellthrough.period_type" in where


def test_earlier_case_helpers_are_not_part_of_the_planner():
    assert not hasattr(builder, "build_same_customer_comparables")
    assert not hasattr(builder, "customer_product_history_units")
    assert not hasattr(builder, "build_comparable_cases")


def test_line_editor_cost_suggestion_uses_sellthrough_without_snapshot_or_intake(monkeypatch):
    from types import SimpleNamespace

    from app.api.v1.endpoints import cpor_cases as endpoint

    session = FakeSession(_book_data())
    case = SimpleNamespace(id=1, customer_id=3, tenant_id="tenant-a", created_at=None)
    line = SimpleNamespace(
        id=2, case_id=1, product_id=7, cost_source=None, cost_evidence_json=None, cost_basis=None
    )

    class Context:
        def __enter__(self):
            return session

        def __exit__(self, *_args):
            return False

    def forbidden(*_args, **_kwargs):
        raise AssertionError("snapshot/intake fallback must not supply planner cost")

    monkeypatch.setattr(endpoint, "SessionLocal", Context)
    monkeypatch.setattr(endpoint, "_load_case", lambda *_a, **_k: case)
    monkeypatch.setattr(session, "get", lambda *_a, **_k: line)
    monkeypatch.setattr(endpoint, "suggest_cost_basis", forbidden)
    if hasattr(endpoint, "suggest_intake_weighted_mac"):
        monkeypatch.setattr(endpoint, "suggest_intake_weighted_mac", forbidden)
    monkeypatch.setattr(endpoint, "resolve_stored_mac_vat", lambda *_a, **_k: (False, None))
    monkeypatch.setattr(endpoint, "customer_soh_check", lambda *_a, **_k: {})
    out = endpoint.cost_suggest(1, 2)
    assert out["cost_basis"] == 100.0
    assert out["cost_source"] == "cst_reported"
    assert out["intake_weighted"]["cost_basis"] == 100.0
    _assert_sellthrough_only(session)


# 10. aged-stock Promote price -----------------------------------------------------------------


def test_aged_stock_promote_price_is_the_sellthrough_unit_sell_price():
    session = FakeSession(_book_data(price=199.0))
    price = actions._srp_for_line(session, customer_id=3, product_id=7, tenant_id="tenant-a")
    assert price == pytest.approx(199.0)
    _assert_sellthrough_only(session)


def test_aged_stock_promote_without_a_sellthrough_price_has_no_price_so_no_draft():
    session = FakeSession(_book_data(price=None))
    assert actions._srp_for_line(session, customer_id=3, product_id=7, tenant_id="tenant-a") is None
    _assert_sellthrough_only(session)


def test_aged_stock_promote_keeps_the_no_positive_srp_outcome(monkeypatch):
    monkeypatch.setattr(actions, "_srp_for_line", lambda *_a, **_k: None)
    skipped: list[dict[str, Any]] = []

    class _S(FakeSession):
        pass

    monkeypatch.setattr(actions, "_lock_stock_action_create", lambda *_a, **_k: None)
    monkeypatch.setattr(actions, "_open_case_id", lambda *_a, **_k: None)
    ready = actions._merged_promote_lines(
        _S(),
        tenant_id="tenant-a",
        customer_id=3,
        rows=[{"product_id": 7, "stock_on_hand": 5, "site_label": None}],
        skipped=skipped,
    )
    assert ready == []
    assert skipped == [{"customer_id": 3, "product_id": 7, "reason": "no_positive_srp"}]


def test_the_shopper_listing_and_lineup_price_rule_is_gone():
    import inspect

    src = inspect.getsource(actions._srp_for_line)
    assert "CommercialLineup" not in src
    assert "load_promotion_line_evidence" not in src
    assert "last_observed_price" not in src
