from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from app.services.cpor import planner_sellthrough
from app.services.cpor.promo_plan_builder import (
    COST_SOURCE_MANUAL,
    COST_SOURCE_SELLTHROUGH,
    build_promo_plan_draft,
    create_case_from_promo_draft,
    load_promotion_line_evidence,
)


@pytest.fixture(autouse=True)
def _no_budget_ledger(monkeypatch):
    """N-0079 draws the campaign headroom from the budget ledger (a savepoint query), which these
    hand-built sessions cannot run. Pin "no ledger"; the ledger path has its own test below."""
    monkeypatch.setattr("app.services.budget_ledger.used_usd", lambda *_a, **_k: None)


def test_draw_comes_from_the_budget_ledger_when_there_is_one(monkeypatch):
    seen = {}

    def ledger(session, *, landed_quarter=None):
        seen["quarter"] = landed_quarter
        return 123.5

    monkeypatch.setattr("app.services.budget_ledger.used_usd", ledger)

    class R:
        def scalar(self):
            return 0

        def one(self):
            return (999, 3)  # case-line draw, which the ledger replaces

        def all(self):
            return []

    class Session:
        def execute(self, *_a, **_k):
            return R()

        def get(self, *_a, **_k):
            return None

        def scalars(self, *_a, **_k):
            return MagicMock(all=MagicMock(return_value=[]))

    out = build_promo_plan_draft(
        Session(), seed_case_id=1, period_label="26Q2", planned_support_usd=1000
    )
    check = out["budget_check"]
    assert check["drawn_source"] == "budget_ledger"
    assert check["tracks"]["money"]["drawn_cpor_usd"] == 123.5
    assert check["tracks"]["money"]["remaining_usd"] == 876.5
    assert seen["quarter"] == "26Q2"


def test_build_promo_plan_draft_case_not_found(monkeypatch):
    class FakeSession:
        def execute(self, *_a, **_k):
            class R:
                def scalar(self):
                    return 0

                def one(self):
                    return (0, 0)

                def all(self):
                    return []

            return R()

        def get(self, *_a, **_k):
            return None

        def scalars(self, *_a, **_k):
            return MagicMock(all=MagicMock(return_value=[]))

    out = build_promo_plan_draft(FakeSession(), seed_case_id=999999)
    assert out["draft"] is True
    assert out["lines"] == []
    assert out["comparables"]["count"] == 0
    assert out["budget_check"]["hard_enforce"] is True
    assert out["budget_check"]["binding_axis"] == "money"
    assert out["budget_check"]["reservation_source"] == "derived_from_profit"
    assert out["budget_check"]["over_budget_action"] == "require_reapproval"
    # Customer sell-through has no planned reservation: not available, never a fake 0.
    money = out["budget_check"]["tracks"]["money"]
    assert money["status"] == "not_available"
    assert money["planned_reservation_usd"] is None
    assert money["remaining_usd"] is None
    assert out["budget_check"]["over_budget_warn"] is False
    assert out["budget_check"]["create_blocked"] is False


def _reservation_stub():
    return {
        "available": False,
        "reason": "reservation_needs_lineup_and_sku_assumptions_not_in_sellthrough",
        "planned_reservation_usd": None,
        "planned_revenue_usd": None,
        "planned_line_count": 0,
        "sku_assumption_count": None,
        "skipped_missing_sku": 0,
        "skipped_missing_srp": 0,
        "reservation_source": "derived_from_profit",
        "from_lineup_derived": False,
    }


class _FakeCost:
    def __init__(self, cost_basis=12.5, flags=None):
        self.cost_basis = cost_basis
        self.cost_source = "cst_reported" if cost_basis is not None else None
        self.flags = flags or []
        self.evidence = {
            "composer": "sellthrough_mac",
            "field_used": "unit_mac",
            "as_of": "2026-08-01",
            "blend": {"formula": "latest reported week", "cost_basis": cost_basis},
            "not_in_blend": ["shipments", "buy_plan"],
        }


def _book(customer_id, *, weekly_units_by_product=None):
    """Sell-through already read for the draft: weekly chain rows per product."""
    from datetime import date, timedelta

    book = planner_sellthrough.SellthroughBook(customer_id=customer_id, window_weeks=8)
    for pid, units in (weekly_units_by_product or {}).items():
        book.window_rows[pid] = [
            (date(2026, 3, 2) + timedelta(weeks=i), "week", "week", u, None, None)
            for i, u in enumerate(units)
        ]
    return book


def test_build_promo_plan_draft_emits_per_line_mac_and_units(monkeypatch):
    from datetime import date

    seed = SimpleNamespace(
        id=10,
        customer_id=7,
        promotion_type="instant_rebate",
        window_start=date(2026, 4, 1),
        window_end=date(2026, 6, 30),
        channel="reseller",
    )
    line_a = SimpleNamespace(
        id=1, product_id=101, distributor_id=3, srp=19999, estimate_qty=4, pod_quarter="26Q2"
    )
    line_b = SimpleNamespace(
        id=2, product_id=102, distributor_id=3, srp=8999, estimate_qty=8, pod_quarter="26Q2"
    )
    prod_a = SimpleNamespace(sales_model_name="X-SALES-MODEL", id=101, sku="SKU-A", name="Alpha")
    prod_b = SimpleNamespace(sales_model_name="X-SALES-MODEL", id=102, sku="SKU-B", name="Beta")

    class FakeSession:
        def get(self, model, key):
            name = getattr(model, "__name__", str(model))
            if name == "CporCase" and key == 10:
                return seed
            if name == "DimProduct":
                return {101: prod_a, 102: prod_b}.get(int(key))
            return None

        def scalars(self, *_a, **_k):
            return MagicMock(all=MagicMock(return_value=[line_a, line_b]))

        def execute(self, *_a, **_k):
            class R:
                def scalar(self):
                    return 0

                def one(self):
                    return (0, 0)

                def all(self):
                    return []

            return R()

    import app.services.cpor.promo_plan_builder as mod

    monkeypatch.setattr(
        mod, "derive_planned_reservation_sync", lambda *_a, **_k: _reservation_stub()
    )
    monkeypatch.setattr(
        mod.planner_sellthrough,
        "read_book",
        lambda *_a, **_k: _book(7, weekly_units_by_product={101: [10.0, 10.0], 102: [5.0]}),
    )
    monkeypatch.setattr(mod, "suggest_sellthrough_mac", lambda *_a, **_k: _FakeCost())
    monkeypatch.setattr(
        mod, "resolve_target_cover_weeks_sync", lambda *_a, **_k: (6.0, "customer_term")
    )

    out = build_promo_plan_draft(FakeSession(), seed_case_id=10, period_label="26Q2")
    assert len(out["lines"]) == 2
    # Expected units: sell-through run rate (10 and 5 a week) times the 13 week horizon.
    assert out["lines"][0]["suggested_estimate_qty"] == 130
    assert out["lines"][1]["suggested_estimate_qty"] == 65
    assert out["lines"][0]["volume"]["source"] == "customer_sellthrough_run_rate"
    assert out["lines"][0]["suggested_cost_basis"] == 12.5
    assert out["lines"][0]["suggested_cost_source"] == "cst_reported"
    # A seed price is not sell-through evidence and cannot supply the suggestion.
    assert out["lines"][0]["srp"] is None
    assert out["lines"][0]["srp_source"] is None
    assert out["lines"][0]["intake_weighted"]["bucket_a_on_hand"] is None
    assert out["lines"][0]["intake_weighted"]["sellout_value"] is None
    assert out["lines"][0]["cover"]["weeks"] == 6.0
    assert out["lines"][0]["cover"]["source"] == "customer_term"
    assert "cost_basis" in out["lines"][0]["editable_fields"]
    assert out["lines"][0]["display_only_fields"] == []
    assert out["volume"]["forecast_units"] == 195


def test_create_case_from_promo_draft_carries_edits_and_skips_cover_persist(monkeypatch):
    from datetime import date

    seed = SimpleNamespace(
        id=10,
        case_code="C-SEED",
        tenant_id="default",
        customer_id=7,
        promotion_type="instant_rebate",
        window_start=date(2026, 4, 1),
        window_end=date(2026, 6, 30),
        channel="reseller",
        roe_snapshot=18.5,
        currency_code="ZAR",
    )
    prod = SimpleNamespace(sales_model_name="X-SALES-MODEL", id=101, sku="SKU-A", name="Alpha")
    added = []
    events = []
    committed = {"n": 0}

    class FakeSession:
        def get(self, model, key):
            name = getattr(model, "__name__", str(model))
            if name == "CporCase":
                return seed
            if name == "DimProduct":
                return (
                    prod
                    if int(key) == 101
                    else SimpleNamespace(
                        id=int(key), sku="X", name="X", sales_model_name="X-SALES-MODEL"
                    )
                )
            return None

        def scalars(self, *_a, **_k):
            return MagicMock(all=MagicMock(return_value=[]))

        def execute(self, *_a, **_k):
            class R:
                def scalar(self):
                    return 0

                def one(self):
                    return (0, 0)

                def all(self):
                    return []

            return R()

        def add(self, obj):
            added.append(obj)

        def flush(self):
            nxt = 1
            for obj in added:
                if getattr(obj, "id", None) is None:
                    obj.id = nxt
                    nxt += 1

        def commit(self):
            committed["n"] += 1

        def refresh(self, obj):
            return obj

    import app.services.cpor.promo_plan_builder as mod
    from app.models.cpor import CporCaseLine

    monkeypatch.setattr(
        mod, "derive_planned_reservation_sync", lambda *_a, **_k: _reservation_stub()
    )
    monkeypatch.setattr(mod.planner_sellthrough, "read_book", lambda *_a, **_k: _book(7))
    monkeypatch.setattr(
        mod, "suggest_sellthrough_mac", lambda *_a, **_k: _FakeCost(cost_basis=12.5)
    )
    monkeypatch.setattr(
        mod, "resolve_target_cover_weeks_sync", lambda *_a, **_k: (4.0, "tenant_default")
    )

    def generate_case_code(_s):
        return "C-NEW"

    def record_event(_s, **kwargs):
        events.append(kwargs)

    def recompute_case_line(_s, line, **_k):
        return {"flags": []}

    def resolve_default_margin(_s, _cid):
        return (0.12, "customer_default")

    snapshot_called = {"n": 0}

    def suggest_cost_basis(*_a, **_k):
        snapshot_called["n"] += 1
        return SimpleNamespace(cost_basis=1.0, cost_source="cst_reported", evidence={}, flags=[])

    out = create_case_from_promo_draft(
        FakeSession(),
        seed_case_id=10,
        confirm_over_budget=True,
        actor="test",
        lines=[
            {
                "product_id": 101,
                "distributor_id": 3,
                "srp": 19999,
                "estimate_qty": 40,
                "cost_basis": 18.0,
                "pod_quarter": "26Q2",
                "cover_override": 8.0,
                "dirty_fields": ["cost_basis"],
            },
            {
                "product_id": 102,
                "distributor_id": 3,
                "srp": 8999,
                "estimate_qty": 22,
                "cost_basis": None,
                "pod_quarter": "26Q2",
                "dirty_fields": ["estimate_qty"],
            },
        ],
        generate_case_code=generate_case_code,
        record_event=record_event,
        recompute_case_line=recompute_case_line,
        resolve_default_margin=resolve_default_margin,
        suggest_cost_basis=suggest_cost_basis,
    )
    assert snapshot_called["n"] == 0
    assert committed["n"] == 1
    written = [o for o in added if isinstance(o, CporCaseLine)]
    assert len(written) == 2
    assert written[0].cost_source == COST_SOURCE_MANUAL
    assert float(written[0].cost_basis) == 18.0
    assert written[1].cost_source == COST_SOURCE_SELLTHROUGH
    assert float(written[1].cost_basis) == 12.5
    assert float(written[1].estimate_qty) == 22
    planner = written[0].cost_evidence_json["planner"]
    assert planner["cover_override"] == 8.0
    assert planner["cover_not_persisted_to_customer_term"] is True
    assert out["lines"][0]["cost_source"] == COST_SOURCE_MANUAL
    assert out["lines"][1]["cost_source"] == COST_SOURCE_SELLTHROUGH
    from app.models.cpor import CporCase

    created_case = next(o for o in added if isinstance(o, CporCase))
    assert created_case.origin == "proposed_by_cip"


def test_window_from_period_label_quarter_bounds():
    from datetime import date

    from app.services.cpor.promo_plan_builder import window_from_period_label

    assert window_from_period_label("2026Q2") == (date(2026, 4, 1), date(2026, 6, 30))
    assert window_from_period_label("2026 Q2") == (date(2026, 4, 1), date(2026, 6, 30))
    assert window_from_period_label("26Q2") == (date(2026, 4, 1), date(2026, 6, 30))


def test_build_promo_plan_draft_requires_seed_or_customer_period():
    import pytest

    with pytest.raises(ValueError, match="missing_seed_or_customer_period"):
        build_promo_plan_draft(MagicMock())


def test_build_promo_plan_draft_from_customer_period_same_customer_only(monkeypatch):
    import app.services.cpor.promo_plan_builder as mod
    from app.services.cpor.promo_plan_builder import PRODUCT_SET_SELLTHROUGH

    class FakeSession:
        def execute(self, *_a, **_k):
            class R:
                def scalar(self):
                    return 0

                def one(self):
                    return (0, 0)

                def all(self):
                    return []

            return R()

        def get(self, model, key):
            name = getattr(model, "__name__", str(model))
            if name == "DimProduct":
                return SimpleNamespace(
                    id=int(key), sku="SKU", name="Name", sales_model_name="X-SALES-MODEL"
                )
            return None

        def scalar(self, *_a, **_k):
            return None

        def scalars(self, *_a, **_k):
            return MagicMock(all=MagicMock(return_value=[]))

    monkeypatch.setattr(
        mod,
        "product_specs_for_customer_period",
        lambda *_a, **_k: (
            [
                {
                    "seed_line_id": None,
                    "product_id": 81,
                    "distributor_id": None,
                    "srp": 2699.0,
                    "estimate_qty": 10,
                    "pod_quarter": "2026Q2",
                    "cover_override": None,
                }
            ],
            PRODUCT_SET_SELLTHROUGH,
        ),
    )
    monkeypatch.setattr(mod.planner_sellthrough, "read_book", lambda *_a, **_k: _book(18))
    monkeypatch.setattr(
        mod, "suggest_sellthrough_mac", lambda *_a, **_k: _FakeCost(cost_basis=10.0)
    )
    monkeypatch.setattr(
        mod, "resolve_target_cover_weeks_sync", lambda *_a, **_k: (4.0, "tenant_default")
    )

    out = build_promo_plan_draft(FakeSession(), customer_id=18, period_label="2026Q2")
    assert out["seed_case_id"] is None
    assert out["product_set_source"] == PRODUCT_SET_SELLTHROUGH
    assert out["customer_id"] == 18
    assert out["window_start"] == "2026-04-01"
    assert out["window_end"] == "2026-06-30"
    assert out["comparables"]["same_customer_only"] is True
    assert out["comparables"]["count"] == 0  # earlier cases are not a planner source
    assert out["lines"][0]["product_id"] == 81
    evidence = out["lines"][0]["promotion_evidence"]
    assert evidence["read_failed"] is False
    assert evidence["listing"]["listed"] is None  # shopper listings are not a planner source
    assert evidence["listing"]["data_unavailable"] is True
    assert evidence["competitor_price"]["data_unavailable"] is True
    assert evidence["competitor_price"]["price"] is None
    assert evidence["observed_cover"]["writes_target_cover"] is False
    assert evidence["observed_cover"]["flag"] is None
    assert out["uncovered"] == ["uplift_from_claim_evidence"]


def test_load_promotion_line_evidence_failed_read_is_not_an_honest_empty(caplog):
    class Boom:
        def scalar(self, *_a, **_k):
            return None

        def execute(self, *_a, **_k):
            raise RuntimeError("db down")

    with caplog.at_level("ERROR"):
        evidence = load_promotion_line_evidence(
            Boom(), customer_id=18, product_id=81, distributor_id=None
        )

    assert evidence["read_failed"] is True
    assert evidence["listing"]["listed"] is None
    assert evidence["listing"]["data_unavailable"] is True
    assert evidence["competitor_price"]["price"] is None
    assert evidence["competitor_price"]["data_unavailable"] is True
    assert evidence["observed_cover"]["weeks"] is None
    assert evidence["observed_cover"]["data_unavailable"] is True
    assert any("promotion line evidence read failed" in record.message for record in caplog.records)
    assert any(record.exc_info and record.exc_info[0] is RuntimeError for record in caplog.records)
