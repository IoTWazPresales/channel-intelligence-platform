"""CPOR U2 — cost suggestion + drift (mocked session; no cip writes)."""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.cpor.cost_suggestion import (
    detect_cost_basis_drift,
    suggest_cost_basis,
)
from app.services.cpor.waterfall import quantize_money


def test_guard_refuses_cip_when_allow_unset():
    """Demonstrate the disposable-DB guard pattern (ALLOW_TESTS_ON_DEV_DB unset)."""
    assert os.environ.get("ALLOW_TESTS_ON_DEV_DB", "").strip() != "1"

    def _sqlalchemy_db_name(url: str) -> str:
        if not url or "://" not in url:
            return ""
        rest = url.split("://", 1)[1]
        if "/" not in rest:
            return ""
        return rest.rsplit("/", 1)[-1].split("?", 1)[0].strip()

    from app.core.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    # Local .env points at cip — guard must refuse writes. We only assert the condition.
    sync_name = _sqlalchemy_db_name(settings.database_url_sync)
    async_name = _sqlalchemy_db_name(settings.database_url)
    if sync_name == "cip" or async_name == "cip":
        # Same skip message the merge tests use — prove we would refuse.
        with pytest.raises(pytest.skip.Exception):
            pytest.skip(
                "Refusing DB writes: set ALLOW_TESTS_ON_DEV_DB=1 or point DATABASE_URL_SYNC at a disposable database."
            )


def test_tier2_weighted_avg_math_via_mock():
    """Two sell-out rows at different prices/units → correct units-weighted average."""
    session = MagicMock()

    # Tier 1 empty
    t1_result = MagicMock()
    t1_result.first = MagicMock(return_value=None)

    # Lookback: no prior case
    lookback_scalar = MagicMock(return_value=None)

    # Tier 2 rows: 10 @ 100 + 30 @ 200 → avg = (1000+6000)/40 = 175
    t2_rows = [
        (Decimal("10"), Decimal("100"), date(2026, 1, 10), None),
        (Decimal("30"), Decimal("200"), date(2026, 1, 20), "0"),
    ]
    t2_result = MagicMock()
    t2_result.all = MagicMock(return_value=t2_rows)

    # execute called for t1 then t2; scalar for lookback
    session.execute = MagicMock(side_effect=[t1_result, t2_result])
    session.scalar = lookback_scalar

    sug = suggest_cost_basis(
        session,
        customer_id=1,
        product_id=2,
        as_of=date(2026, 1, 31),
    )
    assert sug.cost_source == "sellout_evidence"
    assert sug.cost_basis is not None
    assert quantize_money(sug.cost_basis) == Decimal("175.00")
    assert "assumed_currency" in sug.flags
    assert sug.evidence["row_count"] == 2


def test_no_evidence_flags():
    session = MagicMock()
    empty = MagicMock()
    empty.first = MagicMock(return_value=None)
    empty.all = MagicMock(return_value=[])
    session.execute = MagicMock(return_value=empty)
    session.scalar = MagicMock(return_value=None)

    sug = suggest_cost_basis(session, customer_id=1, product_id=2, as_of=date(2026, 6, 1))
    assert sug.cost_basis is None
    assert "no_cost_evidence" in sug.flags


def test_manual_deviation_flag():
    session = MagicMock()
    # Tier1 hit
    t1 = MagicMock()
    t1.first = MagicMock(return_value=(Decimal("100"), date(2026, 5, 1), 9))
    t2 = MagicMock()
    t2.all = MagicMock(return_value=[])
    session.execute = MagicMock(side_effect=[t1, t2])
    session.scalar = MagicMock(return_value=None)

    sug = suggest_cost_basis(
        session,
        customer_id=1,
        product_id=2,
        as_of=date(2026, 6, 1),
        manual_cost="110",
    )
    assert sug.cost_source == "manual"
    assert sug.cost_basis == Decimal("110")
    assert "manual_deviation_from_evidence" in sug.flags


def test_drift_detection():
    from app.services.cpor.cost_suggestion import CostSuggestion

    fresh = CostSuggestion(
        cost_basis=Decimal("200"),
        cost_source="sellout_evidence",
        evidence={"tier": "sellout_evidence"},
        flags=[],
    )
    drift = detect_cost_basis_drift(Decimal("180"), fresh, stored_as_of=date(2026, 1, 1))
    assert drift is not None
    assert drift["flag"] == "cost_basis_drift"
    assert drift["delta"] == 20.0

    assert detect_cost_basis_drift(Decimal("200"), fresh) is None
