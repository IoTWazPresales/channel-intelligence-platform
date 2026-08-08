from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.cpor.promo_plan_builder import build_promo_plan_draft, derive_planned_reservation_sync


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
