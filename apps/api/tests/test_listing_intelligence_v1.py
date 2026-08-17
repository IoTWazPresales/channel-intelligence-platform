"""P5 listing intelligence v1 unit tests (no DB)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.listing_capture.intelligence_v1 import build_listing_intelligence


def _obs(i: int, *, days: int, price: float | None, status: str | None) -> SimpleNamespace:
    return SimpleNamespace(
        id=i,
        fetched_at=datetime(2026, 8, 1, tzinfo=timezone.utc) + timedelta(days=days),
        extracted_price=price,
        parse_flags={"cpor_activation": {"status": status, "case_price": 1000}} if status else {},
    )


def test_accumulating_under_14_days() -> None:
    listing = SimpleNamespace(id=1, customer_id=11, product_id=9, marketplace="takealot", url="u", external_id="x")
    session = MagicMock()
    session.scalars.side_effect = [
        MagicMock(all=lambda: [listing]),
        MagicMock(all=lambda: [_obs(1, days=0, price=900, status="not_activated"), _obs(2, days=3, price=910, status="not_activated")]),
    ]
    out = build_listing_intelligence(session)
    assert out["ready"] == 0
    assert out["items"][0]["history_status"] == "accumulating"
    assert out["items"][0]["worklist"] is False


def test_ready_not_activated_enters_worklist() -> None:
    listing = SimpleNamespace(id=2, customer_id=11, product_id=9, marketplace="takealot", url="u", external_id="x")
    session = MagicMock()
    session.scalars.side_effect = [
        MagicMock(all=lambda: [listing]),
        MagicMock(
            all=lambda: [
                _obs(1, days=0, price=900, status="price_consistent"),
                _obs(2, days=14, price=1200, status="not_activated"),
            ]
        ),
    ]
    out = build_listing_intelligence(session)
    assert out["ready"] == 1
    assert out["not_activated_worklist"] == 1
    assert out["items"][0]["price_drift_pct"] == (1200 - 900) / 900
    assert out["worklist"][0]["listing_id"] == 2
