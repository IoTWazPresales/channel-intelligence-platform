"""Sell-through AI summary (Warren 2026-10-19): the rules summary unless AI is configured; the model
gets a compact fact sheet, the answer is cached, and failures fall back to the rules."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.channel_intelligence import sell_through_narrative as sn


def _overview() -> dict:
    return {
        "filters": {"date_from": "2026-07-20", "date_to": "2026-10-18", "compare": "prior_year", "vat": "ex_vat"},
        "kpis": {
            "units": 1234.0,
            "units_change_pct": 0.12,
            "value": 98765.4,
            "value_change_pct": None,
            "stock_on_hand": 500.0,
            "weeks_of_cover": 4.2,
        },
        "top_sellers": [{"label": "Model A (SKU-A)", "units": 400.0, "change_pct": 0.5}],
        "customer_split": [{"name": "Amazon", "units": 900.0}],
        "problems": {
            "counts": {"needs_replen": 1},
            "rows": [
                {
                    "reason_label": "Needs replenishing",
                    "customer_name": "Amazon",
                    "product": "Model A (SKU-A)",
                    "detail": "2.0 weeks of cover (replenish below 4)",
                    "suggested_qty": 40,
                }
            ],
        },
        "quarters": [{"label": "26Q4", "units": 100.0, "last_year_units": 80.0, "partial": True}],
        "coverage": {"customers_missing": ["Pinnacle"]},
        "summary": ["Units sold up 12% on the same period last year (1,234 vs 1,102)."],
    }


class _FakeMessages:
    calls = 0

    def create(self, **kw):
        _FakeMessages.calls += 1
        assert kw["output_config"] == {"effort": "low"}
        assert "Pinnacle" in kw["messages"][0]["content"]
        return SimpleNamespace(
            stop_reason="end_turn",
            content=[SimpleNamespace(type="text", text="Units rose 12%. Restock Model A at Amazon.")],
            usage=SimpleNamespace(input_tokens=600, output_tokens=40),
        )


class _FakeClient:
    def __init__(self, **_kw):
        self.messages = _FakeMessages()


@pytest.fixture(autouse=True)
def _clear_cache():
    sn._cache.clear()
    yield
    sn._cache.clear()


def _settings(monkeypatch, enabled: bool):
    monkeypatch.setattr(
        sn,
        "get_settings",
        lambda: SimpleNamespace(ai_assist_enabled=enabled, ai_narrative_model="claude-opus-5-5", ai_narrative_cache_minutes=60),
    )


def test_rules_when_ai_is_off(monkeypatch):
    _settings(monkeypatch, False)
    out = sn.narrate(_overview(), tenant_id="t")
    assert out["source"] == "rules"
    assert out["text"].startswith("Units sold up 12%")


def test_rules_when_no_key(monkeypatch):
    _settings(monkeypatch, True)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert sn.narrate(_overview(), tenant_id="t")["source"] == "rules"


def test_ai_summary_is_cached(monkeypatch):
    anthropic = pytest.importorskip("anthropic")
    _settings(monkeypatch, True)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(anthropic, "Anthropic", _FakeClient)
    _FakeMessages.calls = 0
    first = sn.narrate(_overview(), tenant_id="t")
    second = sn.narrate(_overview(), tenant_id="t")
    assert first["source"] == "ai" and first["text"].startswith("Units rose")
    assert second.get("cached") is True
    assert _FakeMessages.calls == 1


def test_fact_sheet_is_compact():
    facts = sn.fact_sheet(_overview())
    assert facts["units_change"] == "+12%"
    assert facts["customers_with_missing_reports"] == ["Pinnacle"]
    assert facts["most_urgent_skus"][0]["suggested_order"] == 40
