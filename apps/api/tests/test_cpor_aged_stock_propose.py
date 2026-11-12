"""Aged-stock actions and promotion evidence. Fakes only — no write to cip."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.cpor.promo_plan_builder import (
    build_promo_plan_draft,
    customer_sku_cover_from_rows,
    load_promotion_line_evidence,
)
from app.services.store_dc.rules import stock_action_covers_site, stock_action_in_notes
from app.services.store_dc.stock_actions import auto_propose_from_intelligence, execute_aged_stock_action


@pytest.fixture(autouse=True)
def _no_budget_ledger(monkeypatch):
    monkeypatch.setattr("app.services.budget_ledger.used_usd", lambda *_a, **_k: None)


def test_stock_action_marker_reads_only_the_three_actions():
    assert stock_action_in_notes("stock_action=promote\nCreated from compose") == "promote"
    assert stock_action_in_notes("stock_action=return;not_a_support_claim=true") == "return"
    assert stock_action_in_notes("stock_action=invent") is None
    assert stock_action_in_notes(None) is None


def test_customer_sku_cover_is_a_flag_and_not_a_target():
    rows = [
        (date(2026, 10, 5), "week", "weekly", 1, 40, "North"),
        (date(2026, 10, 12), "week", "weekly", 1, 40, "North"),
        (date(2026, 10, 19), "week", "weekly", 1, 40, "North"),
        (date(2026, 10, 26), "week", "weekly", 1, 40, "North"),
    ]
    high = customer_sku_cover_from_rows(rows, target_weeks=6, multiple=2)
    assert high["grain"] == "customer_sku"
    assert high["weeks"] == 40
    assert high["flag"] == "high_cover"
    assert high["writes_target_cover"] is False
    assert "target_weeks" not in high or high.get("writes_target_cover") is False

    mild = customer_sku_cover_from_rows(
        [(date(2026, 10, 26), "week", "weekly", 1, 8, "North")],
        target_weeks=6,
        multiple=2,
    )
    assert mild["weeks"] == 8
    assert mild["flag"] == "observed_cover"
    assert mild["writes_target_cover"] is False


def test_customer_sku_cover_sums_sites_and_ignores_a_zero_rate():
    rows = [
        (date(2026, 10, 26), "week", "weekly", 2, 10, "North"),
        (date(2026, 10, 26), "week", "weekly", 2, 6, "South"),
    ]
    cover = customer_sku_cover_from_rows(rows, target_weeks=6, multiple=2)
    assert cover["soh_units"] == 16
    assert cover["weekly_rate"] == 4
    assert cover["weeks"] == 4
    assert cover["flag"] == "observed_cover"

    unsold = customer_sku_cover_from_rows(
        [(date(2026, 10, 26), "week", "weekly", 0, 12, "North")],
        target_weeks=6,
        multiple=2,
    )
    assert unsold["weeks"] is None
    assert unsold["flag"] is None


def test_an_older_chain_report_is_not_added_to_site_stock():
    # Chain-level (blank site) report on 5 Oct: 100 on hand, 10 sold.
    # Site reports on 26 Oct: North 40 on hand + 4 sold, South 60 on hand + 6 sold.
    # Sites exist, so the blank row is the collapsed grain (as in the store/DC read model):
    #   stock = 40 + 60 = 100 (not 100 + 40 + 60 = 200)
    #   rate  = (4 + 6) / 1 week = 10 (not (10 + 10) / 2 = 10 with a chain week mixed in)
    #   cover = 100 / 10 = 10 weeks < 2 x 6 = 12, so observed_cover
    #   (the old sum, 200 / 10 = 20 weeks, raised a false high_cover)
    rows = [
        (date(2026, 10, 5), "week", "weekly", 10, 100, None),
        (date(2026, 10, 26), "week", "weekly", 4, 40, "North"),
        (date(2026, 10, 26), "week", "weekly", 6, 60, "South"),
    ]
    cover = customer_sku_cover_from_rows(rows, target_weeks=6, multiple=2)
    assert cover["soh_units"] == 100
    assert cover["weekly_rate"] == 10
    assert cover["weeks"] == 10
    assert cover["flag"] == "observed_cover"


def test_a_same_week_chain_row_is_not_double_counted():
    # Same week, chain total 100 on hand / 10 sold beside the two sites that make it up.
    #   stock = 40 + 60 = 100 (not 200); rate = 4 + 6 = 10 (not 20); cover = 100 / 10 = 10
    rows = [
        (date(2026, 10, 26), "week", "weekly", 10, 100, ""),
        (date(2026, 10, 26), "week", "weekly", 4, 40, "North"),
        (date(2026, 10, 26), "week", "weekly", 6, 60, "South"),
    ]
    cover = customer_sku_cover_from_rows(rows, target_weeks=6, multiple=2)
    assert cover["soh_units"] == 100
    assert cover["weekly_rate"] == 10
    assert cover["weeks"] == 10


def test_site_labels_group_as_the_read_model_groups_them():
    # "North" and " north " are one site (norm_label). Latest report wins: 40, not 50 + 40 = 90.
    #   rate = (2 + 2) / 2 weeks = 2; cover = 40 / 2 = 20
    rows = [
        (date(2026, 10, 19), "week", "weekly", 2, 50, "North"),
        (date(2026, 10, 26), "week", "weekly", 2, 40, " north "),
    ]
    cover = customer_sku_cover_from_rows(rows, target_weeks=6, multiple=2)
    assert cover["soh_units"] == 40
    assert cover["weekly_rate"] == 2
    assert cover["weeks"] == 20


def test_account_grain_rows_count_when_no_site_reports():
    # Only chain-level rows: latest 100 on hand (26 Oct), rate (5 + 5) / 2 = 5, cover 100 / 5 = 20
    rows = [
        (date(2026, 10, 19), "week", "weekly", 5, 120, None),
        (date(2026, 10, 26), "week", "weekly", 5, 100, None),
    ]
    cover = customer_sku_cover_from_rows(rows, target_weeks=6, multiple=2)
    assert cover["soh_units"] == 100
    assert cover["weekly_rate"] == 5
    assert cover["weeks"] == 20
    assert cover["flag"] == "high_cover"


def test_aged_stock_rows_name_their_customer():
    from app.services.store_dc.stock_actions import _suggestion_rows

    view = {
        "customer_id": 3,
        "customer_name": "Northwind Stores",
        "customer_code": "C-003",
        "account": None,
        "sites": [
            {
                "site_label": "North",
                "customer_id": 3,
                "lines": [{"product_id": 9, "suggestions": ["promote"], "stock_on_hand": 5}],
            }
        ],
        "dc_sections": [],
    }
    rows = _suggestion_rows(view, customer_id=3)
    assert rows[0]["customer_id"] == 3
    assert rows[0]["customer_name"] == "Northwind Stores"
    assert "customer_code" not in rows[0]


class _Result:
    def __init__(self, *, scalar=None, rows=None):
        self._scalar = scalar
        self._rows = rows or []

    def scalar(self):
        return self._scalar

    def all(self):
        return list(self._rows)


def test_evidence_joins_approved_competitor_price_and_keeps_cover_grains_apart():
    statements: list[str] = []

    class Session:
        def __init__(self):
            self.plan = [
                _Result(rows=[]),
                _Result(scalar=3),
                _Result(rows=[("House", "C-1", "Other model", 199.5, "2026-11-01")]),
                _Result(
                    rows=[
                        (date(2026, 10, 5), "week", "weekly", 1, 40, "North"),
                        (date(2026, 10, 12), "week", "weekly", 1, 40, "North"),
                        (date(2026, 10, 19), "week", "weekly", 1, 40, "North"),
                        (date(2026, 10, 26), "week", "weekly", 1, 40, "North"),
                    ]
                ),
                _Result(rows=[(11.0,)]),
            ]

        def execute(self, stmt):
            statements.append(str(stmt))
            return self.plan.pop(0)

    evidence = load_promotion_line_evidence(
        Session(),
        customer_id=18,
        product_id=81,
        distributor_id=4,
        target_weeks=6,
        tenant_id="default",
    )

    assert evidence["read_failed"] is False
    assert evidence["competitor_price"]["data_unavailable"] is False
    assert evidence["competitor_price"]["mapped"] is True
    assert evidence["competitor_price"]["price"] == 199.5
    assert evidence["competitor_price"]["prices"][0]["label"] == "House Other model"
    assert "approval_status" in statements[2]
    assert evidence["observed_cover"]["weeks"] == 40
    assert evidence["observed_cover"]["grain"] == "customer_sku"
    assert evidence["observed_cover"]["flag"] == "high_cover"
    assert evidence["observed_cover"]["writes_target_cover"] is False
    assert evidence["observed_cover"]["distributor_product_weeks"] == 11.0


def test_competitor_prices_without_an_approved_map_stay_off_the_product():
    class Session:
        def execute(self, stmt):
            text = str(stmt).lower()
            if "count" in text:
                return _Result(scalar=4)
            return _Result(rows=[])

    evidence = load_promotion_line_evidence(
        Session(), customer_id=None, product_id=81, distributor_id=None
    )
    assert evidence["competitor_price"]["data_unavailable"] is False
    assert evidence["competitor_price"]["price"] is None
    assert evidence["competitor_price"]["mapped"] is False
    assert evidence["observed_cover"]["weeks"] is None
    assert evidence["observed_cover"]["writes_target_cover"] is False


def test_high_observed_cover_flags_and_does_not_set_quantity(monkeypatch):
    import app.services.cpor.promo_plan_builder as mod

    monkeypatch.setattr(
        mod,
        "load_promotion_line_evidence",
        lambda *_a, **_k: {
            "listing": {"listed": True, "listing_count": 1, "status": "active", "last_observed_price": 50.0},
            "competitor_price": {"data_unavailable": False, "row_count": 1, "price": 40.0, "mapped": True, "prices": []},
            "observed_cover": {
                "weeks": 40.0,
                "flag": "high_cover",
                "grain": "customer_sku",
                "writes_target_cover": False,
            },
            "read_failed": False,
        },
    )
    monkeypatch.setattr(mod, "resolve_target_cover_weeks_sync", lambda *_a, **_k: (6.0, "tenant_default"))
    monkeypatch.setattr(
        mod,
        "suggest_intake_weighted_mac",
        lambda *_a, **_k: SimpleNamespace(cost_basis=10.0, cost_source="intake_weighted", evidence={}, flags=["bucket_a"]),
    )
    monkeypatch.setattr(
        mod,
        "_forecast_volume_sync",
        lambda *_a, **_k: {"forecast_units": 12, "horizon_weeks": 13, "source": "fact_demand_forecast"},
    )
    monkeypatch.setattr(mod, "build_same_customer_comparables", lambda *_a, **_k: {"items": [], "same_customer_only": True})
    monkeypatch.setattr(
        mod,
        "derive_planned_reservation_sync",
        lambda *_a, **_k: {
            "planned_reservation_usd": 0,
            "planned_revenue_usd": 0,
            "planned_line_count": 0,
            "sku_assumption_count": 1,
            "skipped_missing_sku": 0,
            "skipped_missing_srp": 0,
            "reservation_source": "derived_from_profit",
            "from_lineup_derived": False,
        },
    )

    class Session:
        def execute(self, *_a, **_k):
            return _Result(scalar=0, rows=[])

        def one(self):
            return (0, 0)

        def get(self, *_a, **_k):
            return SimpleNamespace(sku="SKU-1", sales_model_name="Model", name="Name")

        def scalars(self, *_a, **_k):
            return MagicMock(all=MagicMock(return_value=[]))

    # execute().one() is what the draft draw uses.
    class SessionWithOne(Session):
        def execute(self, *_a, **_k):
            class R(_Result):
                def one(self_inner):
                    return (0, 0)

            return R(scalar=0, rows=[])

    out = build_promo_plan_draft(
        SessionWithOne(),
        customer_id=18,
        period_label="2026Q4",
        line_specs=[{"product_id": 81, "srp": 10, "estimate_qty": 1, "pod_quarter": "2026Q4"}],
    )
    line = out["lines"][0]
    assert line["suggested_estimate_qty"] == 12
    assert "observed_cover_high" in line["flags"]
    assert line["cover"]["weeks"] == 6
    assert line["cover"]["source"] == "tenant_default"
    assert line["promotion_evidence"]["observed_cover"]["writes_target_cover"] is False


def _slow_view():
    return {
        "sites": [
            {
                "site_label": "North",
                "lines": [
                    {
                        "product_id": 9,
                        "sku": "SKU-9",
                        "product_name": "Name",
                        "stock_on_hand": 12,
                        "weeks_of_cover": 30,
                        "slow": True,
                        "unsold": False,
                        "suggestions": ["promote", "move", "return"],
                        "suggestion_executed": False,
                    }
                ],
            }
        ],
        "account": None,
        "dc_sections": [],
    }


def _writers():
    return dict(
        generate_case_code=lambda _session: "CPOR-1",
        record_event=lambda *_a, **_k: None,
        recompute_case_line=lambda *_a, **_k: {},
        resolve_default_margin=lambda *_a, **_k: (0.12, "customer_default"),
        suggest_cost_basis=lambda *_a, **_k: None,
    )


class _OpenResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)

    def scalar(self):
        return None


def test_promote_creates_a_draft_and_a_second_call_does_not(monkeypatch):
    import app.services.store_dc.stock_actions as actions

    calls = []

    def create(_session, **kwargs):
        calls.append(kwargs)
        return {"created": True, "case_id": 5, "case_code": "CPOR-5", "href": "/commercial-planner/cpor-cases/5"}

    monkeypatch.setattr(actions, "create_case_from_promo_draft", create)
    monkeypatch.setattr(actions, "build_customer_view", lambda *_a, **_k: _slow_view())
    monkeypatch.setattr(actions, "_srp_for_line", lambda *_a, **_k: 100.0)

    class Empty:
        def execute(self, *_a, **_k):
            return _OpenResult([])

    first = execute_aged_stock_action(
        Empty(),
        tenant_id="tenant-a",
        customer_id=3,
        product_id=9,
        action="promote",
        actor="planner",
        **_writers(),
    )
    assert first["created"] is True
    assert first["support_claim"] is True
    assert calls[0]["promotion_type"] == "Stock PP (In-Direct)"
    assert calls[0]["case_origin"] == "proposed_by_cip"
    assert calls[0]["intelligence_exclude"] is False
    assert calls[0]["stock_action"] == "promote"
    assert calls[0]["lines"][0]["estimate_qty"] == 12
    assert calls[0]["lines"][0]["srp"] == 100.0

    class Open:
        def execute(self, *_a, **_k):
            return _OpenResult([(5, "stock_action=promote")])

    second = execute_aged_stock_action(
        Open(),
        tenant_id="tenant-a",
        customer_id=3,
        product_id=9,
        action="promote",
        actor="planner",
        **_writers(),
    )
    assert second["created"] is False
    assert second["reason"] == "already_open"
    assert len(calls) == 1


def test_move_and_return_are_not_support_claims(monkeypatch):
    import app.services.store_dc.stock_actions as actions

    calls = []
    monkeypatch.setattr(
        actions,
        "create_case_from_promo_draft",
        lambda _session, **kwargs: calls.append(kwargs) or {"case_id": 8, "case_code": "CPOR-8", "href": "/x"},
    )
    monkeypatch.setattr(actions, "build_customer_view", lambda *_a, **_k: _slow_view())
    monkeypatch.setattr(actions, "_srp_for_line", lambda *_a, **_k: 80.0)

    class Empty:
        def execute(self, *_a, **_k):
            return _OpenResult([])

    moved = execute_aged_stock_action(
        Empty(),
        tenant_id="tenant-a",
        customer_id=3,
        product_id=9,
        action="move",
        actor="planner",
        site_label="North",
        **_writers(),
    )
    assert moved["support_claim"] is False
    assert calls[0]["case_origin"] == "stock_action"
    assert calls[0]["intelligence_exclude"] is True
    assert calls[0]["case_name_override"] == "Move aged stock"

    execute_aged_stock_action(
        Empty(),
        tenant_id="tenant-a",
        customer_id=3,
        product_id=9,
        action="return",
        actor="planner",
        **_writers(),
    )
    assert calls[1]["case_name_override"] == "Return aged stock"
    assert calls[1]["intelligence_exclude"] is True


def test_action_refuses_a_line_that_is_not_slow_or_unsold(monkeypatch):
    import app.services.store_dc.stock_actions as actions

    monkeypatch.setattr(
        actions,
        "build_customer_view",
        lambda *_a, **_k: {"sites": [{"site_label": "North", "lines": [{"product_id": 9, "suggestions": [], "stock_on_hand": 4}]}], "account": None, "dc_sections": []},
    )
    with pytest.raises(ValueError, match="line_not_slow_or_unsold"):
        execute_aged_stock_action(
            SimpleNamespace(),
            tenant_id="tenant-a",
            customer_id=3,
            product_id=9,
            action="promote",
            actor="planner",
            **_writers(),
        )


def test_auto_propose_skips_a_line_without_a_price_and_opens_one_draft(monkeypatch):
    import app.services.store_dc.stock_actions as actions

    calls = []
    monkeypatch.setattr(
        actions,
        "_collect_aged_stock",
        lambda *_a, **_k: (
            [
                {"customer_id": 3, "product_id": 9, "stock_on_hand": 12, "suggestions": ["promote"]},
                {"customer_id": 3, "product_id": 10, "stock_on_hand": 4, "suggestions": ["promote"]},
            ],
            False,
        ),
    )
    monkeypatch.setattr(actions, "_open_case_id", lambda *_a, **_k: None)

    def srp(_session, *, customer_id, product_id, tenant_id):
        return 90.0 if product_id == 9 else None

    monkeypatch.setattr(actions, "_srp_for_line", srp)
    monkeypatch.setattr(
        actions,
        "create_case_from_promo_draft",
        lambda _session, **kwargs: calls.append(kwargs) or {"case_id": 11, "case_code": "CPOR-11", "href": "/x"},
    )

    out = auto_propose_from_intelligence(
        SimpleNamespace(),
        tenant_id="tenant-a",
        actor="planner",
        customer_id=3,
        period_label="2026Q4",
        **_writers(),
    )
    assert len(calls) == 1
    assert [line["product_id"] for line in calls[0]["lines"]] == [9]
    assert calls[0]["stock_action"] == "promote"
    assert calls[0]["case_origin"] == "proposed_by_cip"
    assert out["created"][0]["case_code"] == "CPOR-11"
    assert out["skipped"] == [{"customer_id": 3, "product_id": 10, "reason": "no_positive_srp"}]


def test_create_case_stamps_move_before_commit_and_keeps_cover_off_the_term(monkeypatch):
    import app.services.cpor.promo_plan_builder as mod
    from app.models.cpor import CporCase, CporCaseLine
    from app.services.cpor.promo_plan_builder import create_case_from_promo_draft

    added: list[object] = []
    monkeypatch.setattr(
        mod,
        "build_promo_plan_draft",
        lambda *_a, **_k: {
            "budget_check": {
                "create_blocked": False,
                "over_budget_warn": False,
                "tracks": {"money": {"status": "ok"}},
            },
            "product_set_source": "lines",
            "lines": [
                {
                    "product_id": 9,
                    "promotion_evidence": {
                        "observed_cover": {
                            "flag": "high_cover",
                            "weeks": 40,
                            "writes_target_cover": False,
                        }
                    },
                }
            ],
        },
    )
    monkeypatch.setattr(
        mod,
        "suggest_intake_weighted_mac",
        lambda *_a, **_k: SimpleNamespace(cost_basis=10.0, cost_source="intake_weighted", evidence={}, flags=["bucket_a"]),
    )

    class Session:
        def get(self, model, key):
            name = getattr(model, "__name__", "")
            if name == "DimCustomer":
                return SimpleNamespace(id=int(key), tenant_id="tenant-a")
            if name == "DimProduct":
                return SimpleNamespace(id=int(key), sku="SKU-9", name="Name", sales_model_name="Model")
            return None

        def execute(self, *_a, **_k):
            return _Result(scalar=0, rows=[])

        def add(self, obj):
            added.append(obj)

        def flush(self):
            nxt = 1
            for obj in added:
                if getattr(obj, "id", None) is None:
                    obj.id = nxt
                    nxt += 1

        def commit(self):
            return None

        def refresh(self, obj):
            return obj

    create_case_from_promo_draft(
        Session(),
        customer_id=3,
        promotion_type="Stock PP (In-Direct)",
        tenant_id="tenant-a",
        period_label="2026Q4",
        actor="planner",
        lines=[{"product_id": 9, "srp": 100, "estimate_qty": 12, "pod_quarter": "2026Q4"}],
        stock_action="move",
        case_origin="stock_action",
        case_name_override="Move aged stock",
        intelligence_exclude=True,
        generate_case_code=lambda _session: "CPOR-MOVE",
        record_event=lambda *_a, **_k: None,
        recompute_case_line=lambda *_a, **_k: {"flags": []},
        resolve_default_margin=lambda *_a, **_k: (0.12, "customer_default"),
        suggest_cost_basis=lambda *_a, **_k: None,
    )
    case = next(obj for obj in added if isinstance(obj, CporCase))
    line = next(obj for obj in added if isinstance(obj, CporCaseLine))
    assert case.origin == "stock_action"
    assert case.case_name == "Move aged stock"
    assert case.intelligence_exclude is True
    assert str(case.notes).startswith("stock_action=move;not_a_support_claim=true")
    assert line.cost_evidence_json["stock_action"] == "move"
    assert "observed_cover_high" in line.cost_evidence_json["flags"]
    assert line.cost_evidence_json["promotion_evidence"]["observed_cover"]["writes_target_cover"] is False
    assert line.cost_evidence_json["planner"]["cover_not_persisted_to_customer_term"] is True


def test_a_recorded_site_does_not_cover_every_site():
    assert stock_action_covers_site(None, "North") is True
    assert stock_action_covers_site({}, "North") is True
    assert stock_action_covers_site({"site_labels": ["North"]}, "North") is True
    assert stock_action_covers_site({"site_labels": ["North"]}, "South") is False
    assert stock_action_covers_site({"site_labels": ["North"]}, None) is False
    assert stock_action_covers_site({"site_labels": [None]}, None) is True
    assert stock_action_covers_site({"site_labels": [None]}, "North") is False


def test_lineup_price_stays_on_the_target_customer(monkeypatch):
    import app.services.store_dc.stock_actions as actions
    from sqlalchemy.dialects import postgresql

    monkeypatch.setattr(
        actions,
        "load_promotion_line_evidence",
        lambda *_a, **_k: {"listing": {"last_observed_price": None}},
    )
    seen = []

    class Session:
        def execute(self, statement, *_a, **_k):
            seen.append(statement)
            return _Result(scalar=80)

    price = actions._srp_for_line(Session(), customer_id=3, product_id=9, tenant_id="tenant-a")
    sql = str(seen[0].compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})).lower()
    assert price == 80.0
    assert "customer_id" in sql
    assert "superseded_by_case_id" in sql
    assert "cancelled" in sql
    assert "msrp_local" in sql
    assert "dap_evidence" not in sql


def _two_site_view():
    line = {
        "product_id": 9,
        "stock_on_hand": 12,
        "suggestions": ["promote", "move", "return"],
        "slow": True,
        "unsold": False,
    }
    return {
        "account": None,
        "sites": [
            {"site_label": "North", "customer_id": 3, "lines": [dict(line)]},
            {"site_label": "South", "customer_id": 3, "lines": [dict(line)]},
        ],
        "dc_sections": [],
    }


def test_one_sites_stock_action_does_not_suppress_another_site(monkeypatch):
    import app.services.store_dc.stock_actions as actions

    calls = []
    monkeypatch.setattr(actions, "build_customer_view", lambda *_a, **_k: _two_site_view())
    monkeypatch.setattr(actions, "_srp_for_line", lambda *_a, **_k: 100.0)
    monkeypatch.setattr(
        actions,
        "create_case_from_promo_draft",
        lambda _session, **kwargs: calls.append(kwargs) or {"case_id": 6, "case_code": "CPOR-6", "href": "/x"},
    )

    class OpenNorth:
        def execute(self, *_a, **_k):
            return _OpenResult([(5, "stock_action=promote", {"site_labels": ["North"], "stock_action": "promote"})])

    south = execute_aged_stock_action(
        OpenNorth(),
        tenant_id="tenant-a",
        customer_id=3,
        product_id=9,
        action="promote",
        actor="planner",
        site_label="South",
        **_writers(),
    )
    assert south["created"] is True
    assert calls[0]["lines"][0]["estimate_qty"] == 12
    assert calls[0]["lines"][0]["site_labels"] == ["South"]

    north = execute_aged_stock_action(
        OpenNorth(),
        tenant_id="tenant-a",
        customer_id=3,
        product_id=9,
        action="promote",
        actor="planner",
        site_label="North",
        **_writers(),
    )
    assert north["created"] is False
    assert north["reason"] == "already_open"
    assert len(calls) == 1


def test_account_grain_is_not_suppressed_by_a_named_site(monkeypatch):
    import app.services.store_dc.stock_actions as actions

    calls = []
    view = {
        "account": {
            "site_label": None,
            "customer_id": 3,
            "lines": [{"product_id": 9, "stock_on_hand": 4, "suggestions": ["promote"]}],
        },
        "sites": [
            {
                "site_label": "North",
                "customer_id": 3,
                "lines": [{"product_id": 9, "stock_on_hand": 12, "suggestions": ["promote"]}],
            }
        ],
        "dc_sections": [],
    }
    monkeypatch.setattr(actions, "build_customer_view", lambda *_a, **_k: view)
    monkeypatch.setattr(actions, "_srp_for_line", lambda *_a, **_k: 50.0)
    monkeypatch.setattr(
        actions,
        "create_case_from_promo_draft",
        lambda _session, **kwargs: calls.append(kwargs) or {"case_id": 7, "case_code": "CPOR-7", "href": "/x"},
    )

    class OpenNorth:
        def execute(self, *_a, **_k):
            return _OpenResult([(5, "stock_action=promote", {"site_labels": ["North"]})])

    account = execute_aged_stock_action(
        OpenNorth(),
        tenant_id="tenant-a",
        customer_id=3,
        product_id=9,
        action="promote",
        actor="planner",
        **_writers(),
    )
    assert account["created"] is True
    assert calls[0]["lines"][0]["estimate_qty"] == 4
    assert calls[0]["lines"][0]["site_labels"] == [None]


def test_auto_propose_keeps_a_site_the_open_case_does_not_cover(monkeypatch):
    import app.services.store_dc.stock_actions as actions

    calls = []
    monkeypatch.setattr(
        actions,
        "_collect_aged_stock",
        lambda *_a, **_k: (
            [
                {"customer_id": 3, "product_id": 9, "site_label": "North", "stock_on_hand": 10, "suggestions": ["promote"]},
                {"customer_id": 3, "product_id": 9, "site_label": "South", "stock_on_hand": 7, "suggestions": ["promote"]},
            ],
            False,
        ),
    )
    monkeypatch.setattr(
        actions,
        "_open_case_id",
        lambda *_a, **kwargs: 5 if kwargs.get("site_label") == "North" else None,
    )
    monkeypatch.setattr(actions, "_srp_for_line", lambda *_a, **_k: 90.0)
    monkeypatch.setattr(
        actions,
        "create_case_from_promo_draft",
        lambda _session, **kwargs: calls.append(kwargs) or {"case_id": 12, "case_code": "CPOR-12", "href": "/x"},
    )
    auto_propose_from_intelligence(
        SimpleNamespace(),
        tenant_id="tenant-a",
        actor="planner",
        customer_id=3,
        period_label="2026Q4",
        **_writers(),
    )
    assert calls[0]["lines"][0]["estimate_qty"] == 7
    assert calls[0]["lines"][0]["site_labels"] == ["South"]


def test_auto_propose_is_not_capped_at_the_display_list(monkeypatch):
    import app.services.store_dc.stock_actions as actions
    from app.services.store_dc.stock_actions import list_aged_stock

    rows = [
        {"product_id": i, "stock_on_hand": 1, "suggestions": ["promote"], "site_label": None}
        for i in range(1, 202)
    ]
    monkeypatch.setattr(actions, "build_lead_index", lambda *_a, **_k: {})
    monkeypatch.setattr(
        actions,
        "build_customer_view",
        lambda *_a, **_k: {"account": {"site_label": None, "customer_id": 3, "lines": rows}, "sites": [], "dc_sections": []},
    )
    monkeypatch.setattr(actions, "_open_case_id", lambda *_a, **_k: None)
    monkeypatch.setattr(actions, "_srp_for_line", lambda *_a, **_k: 10.0)
    calls = []
    monkeypatch.setattr(
        actions,
        "create_case_from_promo_draft",
        lambda _session, **kwargs: calls.append(kwargs) or {"case_id": 13, "case_code": "CPOR-13", "href": "/x"},
    )
    out = auto_propose_from_intelligence(
        SimpleNamespace(),
        tenant_id="tenant-a",
        actor="planner",
        customer_id=3,
        period_label="2026Q4",
        **_writers(),
    )
    assert len(calls[0]["lines"]) == 201
    assert out["truncated"] is False
    listed = list_aged_stock(SimpleNamespace(), tenant_id="tenant-a", customer_id=3)
    assert len(listed["lines"]) == 200
    assert listed["truncated"] is True


def test_display_list_is_truncated_when_another_customer_remains(monkeypatch):
    import app.services.store_dc.stock_actions as actions
    from app.services.store_dc.stock_actions import list_aged_stock

    def view(_session, _tenant, cid, **_kwargs):
        lines = [
            {"product_id": i, "suggestions": ["promote"], "stock_on_hand": 1, "site_label": None}
            for i in range(200)
        ]
        return {"account": {"site_label": None, "customer_id": cid, "lines": lines}, "sites": [], "dc_sections": []}

    monkeypatch.setattr(actions, "build_customer_view", view)
    monkeypatch.setattr(actions, "build_lead_index", lambda *_a, **_k: {})
    monkeypatch.setattr(
        actions, "_with_stock_evidence", lambda _s, *, tenant_id, customer_ids: customer_ids
    )

    class Session:
        def scalars(self, *_a, **_k):
            return SimpleNamespace(all=lambda: [3, 4])

    listed = list_aged_stock(Session(), tenant_id="tenant-a")
    assert len(listed["lines"]) == 200
    assert listed["truncated"] is True


def test_suggestion_rows_read_stores_and_need_from_distributor():
    from app.services.store_dc.stock_actions import _suggestion_rows

    view = {
        "account": None,
        "sites": [
            {
                "site_label": "North",
                "customer_id": 3,
                "lines": [{"product_id": 9, "suggestions": ["promote"], "stock_on_hand": 5}],
            }
        ],
        "dc_sections": [
            {
                "site_label": "Hub",
                "customer_id": 3,
                "stores": [
                    {
                        "site_label": "North",
                        "customer_id": 3,
                        "lines": [{"product_id": 9, "suggestions": ["promote"], "stock_on_hand": 5}],
                    },
                    {
                        "site_label": "Other",
                        "customer_id": 8,
                        "lines": [{"product_id": 7, "suggestions": ["promote"], "stock_on_hand": 9}],
                    },
                ],
                "need_from_distributor": [
                    {"product_id": 8, "suggestions": ["move"], "stock_on_hand": 3, "sku": "SKU-8"},
                ],
            },
            {
                "site_label": "Foreign",
                "customer_id": 8,
                "need_from_distributor": [
                    {"product_id": 4, "suggestions": ["promote"], "stock_on_hand": 2},
                ],
            },
            {
                "site_label": "Wrong",
                "sites": [
                    {
                        "site_label": "Ghost",
                        "lines": [{"product_id": 1, "suggestions": ["promote"], "stock_on_hand": 1}],
                    }
                ],
                "lines": [{"product_id": 2, "suggestions": ["return"], "stock_on_hand": 1}],
            },
        ],
    }
    rows = _suggestion_rows(view, customer_id=3)
    assert {(row["product_id"], row["site_label"]) for row in rows} == {(9, "North"), (8, "Hub")}


def test_explicit_line_keeps_promotion_evidence_when_the_draft_omits_it(monkeypatch):
    import app.services.cpor.promo_plan_builder as mod
    from app.models.cpor import CporCaseLine
    from app.services.cpor.promo_plan_builder import create_case_from_promo_draft

    added: list[object] = []
    draft_calls: list[dict] = []
    loaded: list[dict] = []

    def build(*_a, **kwargs):
        draft_calls.append(kwargs)
        return {
            "budget_check": {
                "create_blocked": False,
                "over_budget_warn": False,
                "tracks": {"money": {"status": "ok"}},
            },
            "product_set_source": "customer_history",
            "lines": [],
        }

    def load(_session, **kwargs):
        loaded.append(kwargs)
        return {
            "observed_cover": {"flag": "high_cover", "weeks": 40, "writes_target_cover": False},
            "read_failed": False,
        }

    monkeypatch.setattr(mod, "build_promo_plan_draft", build)
    monkeypatch.setattr(mod, "load_promotion_line_evidence", load)
    monkeypatch.setattr(mod, "resolve_target_cover_weeks_sync", lambda *_a, **_k: (6.0, "tenant_default"))
    monkeypatch.setattr(
        mod,
        "suggest_intake_weighted_mac",
        lambda *_a, **_k: SimpleNamespace(cost_basis=10.0, cost_source="intake_weighted", evidence={}, flags=[]),
    )

    class Session:
        def get(self, model, key):
            name = getattr(model, "__name__", "")
            if name == "DimCustomer":
                return SimpleNamespace(id=int(key), tenant_id="tenant-a")
            if name == "DimProduct":
                return SimpleNamespace(id=int(key), sku="SKU-9", name="Name")
            return None

        def execute(self, *_a, **_k):
            return _Result(scalar=0, rows=[])

        def add(self, obj):
            added.append(obj)

        def flush(self):
            nxt = 1
            for obj in added:
                if getattr(obj, "id", None) is None:
                    obj.id = nxt
                    nxt += 1

        def commit(self):
            return None

        def refresh(self, obj):
            return obj

    writers = dict(
        generate_case_code=lambda _session: "CPOR-EVID",
        record_event=lambda *_a, **_k: None,
        recompute_case_line=lambda *_a, **_k: {"flags": []},
        resolve_default_margin=lambda *_a, **_k: (0.12, "customer_default"),
        suggest_cost_basis=lambda *_a, **_k: None,
    )
    create_case_from_promo_draft(
        Session(),
        customer_id=3,
        promotion_type="Stock PP (In-Direct)",
        tenant_id="tenant-a",
        period_label="2026Q4",
        actor="planner",
        lines=[{"product_id": 9, "srp": 100, "estimate_qty": 12, "pod_quarter": "2026Q4", "site_labels": ["South"]}],
        stock_action="promote",
        **writers,
    )
    assert draft_calls[0]["line_specs"] is None
    assert loaded[0]["product_id"] == 9
    assert loaded[0]["target_weeks"] == 6.0
    line = next(obj for obj in added if isinstance(obj, CporCaseLine))
    assert line.cost_evidence_json["promotion_evidence"]["observed_cover"]["flag"] == "high_cover"
    assert "observed_cover_high" in line.cost_evidence_json["flags"]
    assert line.cost_evidence_json["site_labels"] == ["South"]

    loaded.clear()
    supplied = {"observed_cover": {"flag": "observed_cover", "weeks": 8, "writes_target_cover": False}}
    create_case_from_promo_draft(
        Session(),
        customer_id=3,
        promotion_type="Stock PP (In-Direct)",
        tenant_id="tenant-a",
        period_label="2026Q4",
        actor="planner",
        lines=[{"product_id": 9, "srp": 100, "estimate_qty": 12, "promotion_evidence": supplied}],
        stock_action="promote",
        **writers,
    )
    assert loaded == []
    explicit = [obj for obj in added if isinstance(obj, CporCaseLine)][-1]
    assert explicit.cost_evidence_json["promotion_evidence"] == supplied
