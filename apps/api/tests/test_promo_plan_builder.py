from app.services.cpor.promo_plan_builder import build_promo_plan_draft

def test_build_promo_plan_draft_case_not_found(monkeypatch):
    class FakeSession:
        def execute(self, *_a, **_k):
            class R:
                def scalar(self):
                    return 0
                def one(self):
                    return (0, 0)
            return R()
        def get(self, *_a, **_k):
            return None

    # monkeypatch comparable to empty
    import app.services.cpor.promo_plan_builder as mod

    def fake_comp(session, *, case_id, limit=10):
        return {"case_id": case_id, "error": "case_not_found", "items": []}

    monkeypatch.setattr(mod, "build_comparable_cases", fake_comp)
    out = build_promo_plan_draft(FakeSession(), seed_case_id=999999)
    assert out["draft"] is True
    assert out["comparables"]["error"] == "case_not_found"
    assert out["budget_check"]["hard_enforce"] is False
    assert out["budget_check"]["binding_axis"] == "money"
    assert out["budget_check"]["reservation_source"] == "derived_from_profit"
    assert out["budget_check"]["over_budget_action"] == "require_reapproval"
