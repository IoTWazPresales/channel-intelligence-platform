"""Aged-stock rule consistency (BACKLOG-227 residuals, 2026-11-18). Fakes only, no DB."""

from datetime import date
from types import SimpleNamespace

from app.services.cpor.promo_plan_builder import load_promotion_line_evidence


class _Result:
    def __init__(self, *, scalar=None, rows=None):
        self._scalar = scalar
        self._rows = rows or []

    def scalar(self):
        return self._scalar

    def all(self):
        return list(self._rows)


def _session(cfg, scalar_calls):
    # 40 units on hand, 1 sold a week: 40 weeks of cover against a 6 week target.
    class Session:
        def __init__(self):
            # Sell-through only: the window cutoff, then the window rows.
            weeks = [date(2026, 10, 5), date(2026, 10, 12), date(2026, 10, 19), date(2026, 10, 26)]
            self.plan = [
                _Result(rows=[(d,) for d in reversed(weeks)]),
                _Result(rows=[(81, d, "week", "weekly", 1, 40, "North") for d in weeks]),
            ]

        def scalar(self, stmt):
            scalar_calls.append(str(stmt))
            return cfg

        def execute(self, _stmt):
            return self.plan.pop(0)

    return Session()


def _evidence(cfg, **kwargs):
    calls: list[str] = []
    out = load_promotion_line_evidence(
        _session(cfg, calls),
        customer_id=18,
        product_id=81,
        distributor_id=None,
        target_weeks=6,
        **kwargs,
    )
    return out, calls


def test_planner_cover_uses_the_customer_slow_multiple():
    out, calls = _evidence(SimpleNamespace(slow_cover_multiple=8))
    cover = out["observed_cover"]
    assert out["read_failed"] is False
    assert cover["weeks"] == 40
    assert cover["slow_multiple"] == 8.0
    # 40 < 8 x 6, so this customer's setting says the line is not slow.
    assert cover["flag"] == "observed_cover"
    assert len(calls) == 1 and "customer_report_config" in calls[0]


def test_planner_cover_falls_back_to_the_shared_multiple():
    out, _calls = _evidence(None)
    cover = out["observed_cover"]
    assert cover["slow_multiple"] == 2.0
    assert cover["flag"] == "high_cover"

    unset, _ = _evidence(SimpleNamespace(slow_cover_multiple=None))
    assert unset["observed_cover"]["slow_multiple"] == 2.0


def test_an_explicit_multiple_is_not_overridden():
    out, calls = _evidence(SimpleNamespace(slow_cover_multiple=8), slow_multiple=3)
    assert out["observed_cover"]["slow_multiple"] == 3.0
    assert out["observed_cover"]["flag"] == "high_cover"
    assert calls == []
