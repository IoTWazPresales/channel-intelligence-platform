"""Opus R-05: draft case creation refuses when tenant VAT is unset."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def test_create_case_from_promo_draft_raises_when_vat_rate_not_configured(monkeypatch):
    from app.services.cpor import promo_plan_builder as mod
    from app.services.cpor.promo_plan_builder import create_case_from_promo_draft

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

    class FakeSession:
        def get(self, model, key):
            if getattr(model, "__name__", str(model)) == "CporCase":
                return seed
            return SimpleNamespace(id=int(key), sku="SKU", name="Prod", sales_model_name="M")

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

        def add(self, _obj):
            pass

        def flush(self):
            pass

    monkeypatch.setattr(mod, "derive_planned_reservation_sync", lambda *_a, **_k: {"available": False})
    monkeypatch.setattr(mod.planner_sellthrough, "read_book", lambda *_a, **_k: {"rows": []})
    def _draft(*_a, **_k):
        return {
            "lines": [{"product_id": 1}],
            "budget_check": {"create_blocked": False, "tracks": {"money": {"status": "ok"}}},
        }

    monkeypatch.setattr(mod, "build_promo_plan_draft", _draft)
    monkeypatch.setattr(
        "app.services.commercial_tenant_profile.configured_vat_rate_pct",
        lambda *_a: None,
    )

    with pytest.raises(ValueError, match="vat_rate_not_configured"):
        create_case_from_promo_draft(
            FakeSession(),
            seed_case_id=10,
            confirm_over_budget=True,
            actor="test",
            lines=[{"product_id": 1, "distributor_id": 3, "srp": 100, "estimate_qty": 1}],
            generate_case_code=lambda *_a: "C-NEW",
            record_event=lambda *_a, **_k: None,
            recompute_case_line=lambda *_a, **_k: {"flags": []},
            resolve_default_margin=lambda *_a, **_k: (0.12, "default"),
            suggest_cost_basis=lambda *_a, **_k: SimpleNamespace(cost_basis=1.0),
        )


def test_create_case_from_promo_draft_proceeds_when_vat_rate_is_configured(monkeypatch):
    from app.models.cpor import CporCaseLine
    from app.services.cpor import promo_plan_builder as mod
    from app.services.cpor.promo_plan_builder import create_case_from_promo_draft

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
    added: list[object] = []

    class FakeSession:
        def get(self, model, key):
            if getattr(model, "__name__", str(model)) == "CporCase":
                return seed
            return SimpleNamespace(
                id=int(key), sku="SKU-A", name="Alpha", sales_model_name="M"
            )

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
            pass

        def refresh(self, _obj):
            pass

    monkeypatch.setattr(mod, "derive_planned_reservation_sync", lambda *_a, **_k: {"available": False})
    monkeypatch.setattr(mod.planner_sellthrough, "read_book", lambda *_a, **_k: {"rows": []})
    def _draft(*_a, **_k):
        return {
            "lines": [{"product_id": 101}],
            "budget_check": {"create_blocked": False, "tracks": {"money": {"status": "ok"}}},
        }

    monkeypatch.setattr(mod, "build_promo_plan_draft", _draft)
    monkeypatch.setattr(
        "app.services.commercial_tenant_profile.configured_vat_rate_pct",
        lambda *_a: 0.15,
    )
    monkeypatch.setattr(
        mod,
        "suggest_sellthrough_mac",
        lambda *_a, **_k: SimpleNamespace(cost_basis=12.5, cost_source="cst_reported", evidence={}, flags=[]),
    )
    monkeypatch.setattr(
        mod, "resolve_target_cover_weeks_sync", lambda *_a, **_k: (4.0, "tenant_default")
    )

    create_case_from_promo_draft(
        FakeSession(),
        seed_case_id=10,
        confirm_over_budget=True,
        actor="test",
        lines=[{"product_id": 101, "distributor_id": 3, "srp": 199, "estimate_qty": 2}],
        generate_case_code=lambda *_a: "C-NEW",
        record_event=lambda *_a, **_k: None,
        recompute_case_line=lambda *_a, **_k: {"flags": []},
        resolve_default_margin=lambda *_a, **_k: (0.12, "default"),
        suggest_cost_basis=lambda *_a, **_k: SimpleNamespace(cost_basis=1.0),
    )
    lines = [o for o in added if isinstance(o, CporCaseLine)]
    assert len(lines) == 1
    assert float(lines[0].vat_rate) == pytest.approx(0.15)