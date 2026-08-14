from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.cpor.promo_plan_builder import (
    COST_SOURCE_INTAKE_WEIGHTED,
    COST_SOURCE_MANUAL,
    build_promo_plan_draft,
    create_case_from_promo_draft,
    derive_planned_reservation_sync,
)


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

    import app.services.cpor.promo_plan_builder as mod

    def fake_comp(session, *, case_id, limit=10):
        return {"case_id": case_id, "error": "case_not_found", "items": []}

    monkeypatch.setattr(mod, "build_comparable_cases", fake_comp)
    monkeypatch.setattr(
        mod,
        "derive_planned_reservation_sync",
        lambda *_a, **_k: {
            "planned_reservation_usd": 0,
            "planned_revenue_usd": 0,
            "planned_line_count": 0,
            "sku_assumption_count": 0,
            "skipped_missing_sku": 0,
            "skipped_missing_srp": 0,
            "reservation_source": "derived_from_profit",
            "from_lineup_derived": False,
        },
    )
    out = build_promo_plan_draft(FakeSession(), seed_case_id=999999)
    assert out["draft"] is True
    assert out["lines"] == []
    assert out["comparables"]["error"] == "case_not_found"
    assert out["budget_check"]["hard_enforce"] is True
    assert out["budget_check"]["binding_axis"] == "money"
    assert out["budget_check"]["reservation_source"] == "derived_from_profit"
    assert out["budget_check"]["over_budget_action"] == "require_reapproval"
    assert out["budget_check"]["tracks"]["money"]["status"] == "missing_sku_economics"


def test_derive_planned_skips_missing_srp(monkeypatch):
    item = SimpleNamespace(product_id=10, planned_volume_units=100, period_label="26Q2")
    sku = SimpleNamespace(
        product_id=10,
        controlled_cost_amount=500.0,
        reserve_total_pct=0.1,
        promo_reserve_split_pct=0.5,
        vat_rate_pct=0.15,
        fx_plan_currency_per_cost_currency=1.0,
    )

    class FakeSession:
        def scalars(self, stmt):
            # FactLineupPlanItem then CommercialSkuAssumption
            text = str(stmt)
            if "commercial_sku_assumption" in text.lower() or "CommercialSkuAssumption" in text:
                return MagicMock(all=MagicMock(return_value=[sku]))
            return MagicMock(all=MagicMock(return_value=[item]))

        def execute(self, *_a, **_k):
            class R:
                def all(self):
                    return []

                def scalar(self):
                    return 1

            return R()

    import app.services.cpor.promo_plan_builder as mod

    monkeypatch.setattr(mod, "_srp_evidence_by_product_sync", lambda *_a, **_k: {})
    out = derive_planned_reservation_sync(FakeSession(), period_label="26Q2")
    assert out["planned_line_count"] == 0
    assert out["skipped_missing_srp"] == 1


def _reservation_stub():
    return {
        "planned_reservation_usd": 0,
        "planned_revenue_usd": 0,
        "planned_line_count": 0,
        "sku_assumption_count": 1,
        "skipped_missing_sku": 0,
        "skipped_missing_srp": 0,
        "reservation_source": "derived_from_profit",
        "from_lineup_derived": False,
    }


class _FakeIntake:
    def __init__(self, cost_basis=12.5, flags=None):
        self.cost_basis = cost_basis
        self.cost_source = "intake_weighted"
        self.flags = flags or ["cross_grain_valuation"]
        self.evidence = {
            "composer": "intake_weighted_mac",
            "bucket_a_on_hand": {"qty": 10, "unit_cost": 10.0, "as_of": "2026-08-01", "flags": []},
            "bucket_b_intake": {"qty": 2, "unit_cost": 20.0, "as_of": "2026-08-10", "flags": ["intake_is_oem_sell_in_evidence"]},
            "planned_supply": {"qty": 5, "unit_cost": 10.0, "flags": ["planned_supply_no_native_cost"]},
            "sellout_value": {"qty": 10, "unit_amount": 99.0, "flags": ["sellout_value_display_only"]},
            "disti_cost": {"unit_cost_proxy": 11.0, "flags": ["dsi_wac_not_ingested"]},
            "blend": {"formula": "(Aq·CST_MAC + Bq·inbound_unit_price) / (Aq+Bq)", "cost_basis": 12.5},
        }


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
    line_a = SimpleNamespace(id=1, product_id=101, distributor_id=3, srp=19999, estimate_qty=4, pod_quarter="26Q2")
    line_b = SimpleNamespace(id=2, product_id=102, distributor_id=3, srp=8999, estimate_qty=8, pod_quarter="26Q2")
    prod_a = SimpleNamespace(id=101, sku="SKU-A", name="Alpha")
    prod_b = SimpleNamespace(id=102, sku="SKU-B", name="Beta")

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

    monkeypatch.setattr(mod, "build_comparable_cases", lambda *_a, **_k: {"items": []})
    monkeypatch.setattr(mod, "derive_planned_reservation_sync", lambda *_a, **_k: _reservation_stub())
    monkeypatch.setattr(
        mod,
        "_forecast_volume_sync",
        lambda *_a, **k: {
            "horizon_weeks": 13,
            "forecast_units": 40 if k.get("product_id") == 101 else 15,
            "source": "fact_demand_forecast",
        },
    )
    monkeypatch.setattr(mod, "suggest_intake_weighted_mac", lambda *_a, **_k: _FakeIntake())
    monkeypatch.setattr(mod, "resolve_target_cover_weeks_sync", lambda *_a, **_k: (6.0, "customer_term"))

    out = build_promo_plan_draft(FakeSession(), seed_case_id=10, period_label="26Q2")
    assert len(out["lines"]) == 2
    assert out["lines"][0]["suggested_estimate_qty"] == 40
    assert out["lines"][1]["suggested_estimate_qty"] == 15
    assert out["lines"][0]["suggested_cost_basis"] == 12.5
    assert out["lines"][0]["intake_weighted"]["bucket_a_on_hand"]["qty"] == 10
    assert "sellout_value_display_only" in (
        out["lines"][0]["intake_weighted"]["sellout_value"]["flags"]
    )
    assert out["lines"][0]["cover"]["weeks"] == 6.0
    assert out["lines"][0]["cover"]["source"] == "customer_term"
    assert "cost_basis" in out["lines"][0]["editable_fields"]
    assert "bucket_a_on_hand" in out["lines"][0]["display_only_fields"]


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
    prod = SimpleNamespace(id=101, sku="SKU-A", name="Alpha")
    added = []
    events = []
    committed = {"n": 0}

    class FakeSession:
        def get(self, model, key):
            name = getattr(model, "__name__", str(model))
            if name == "CporCase":
                return seed
            if name == "DimProduct":
                return prod if int(key) == 101 else SimpleNamespace(id=int(key), sku="X", name="X")
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

    monkeypatch.setattr(mod, "build_comparable_cases", lambda *_a, **_k: {"items": []})
    monkeypatch.setattr(mod, "derive_planned_reservation_sync", lambda *_a, **_k: _reservation_stub())
    monkeypatch.setattr(
        mod,
        "_forecast_volume_sync",
        lambda *_a, **_k: {"horizon_weeks": 13, "forecast_units": 10, "source": "fact_demand_forecast"},
    )
    monkeypatch.setattr(mod, "suggest_intake_weighted_mac", lambda *_a, **_k: _FakeIntake(cost_basis=12.5))
    monkeypatch.setattr(mod, "resolve_target_cover_weeks_sync", lambda *_a, **_k: (4.0, "tenant_default"))

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
    assert written[1].cost_source == COST_SOURCE_INTAKE_WEIGHTED
    assert float(written[1].estimate_qty) == 22
    planner = written[0].cost_evidence_json["planner"]
    assert planner["cover_override"] == 8.0
    assert planner["cover_not_persisted_to_customer_term"] is True
    assert out["lines"][0]["cost_source"] == COST_SOURCE_MANUAL
    assert out["lines"][1]["cost_source"] == COST_SOURCE_INTAKE_WEIGHTED
