"""U6 scaffold reader migration tests (spec §7) — no DB writes."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.imports.dsi_import_state_awareness import _has_cpor_data
from app.services.product_usage import _SPECS
from app.services.imports.template_definitions import IMPORT_TEMPLATE_ROWS


def test_has_cpor_true_when_cases_exist() -> None:
    session = MagicMock()
    session.scalar.return_value = 3
    assert _has_cpor_data(session, 1) is True


def test_has_cpor_false_when_empty() -> None:
    session = MagicMock()
    session.scalar.return_value = 0
    assert _has_cpor_data(session, None) is False


def test_product_usage_includes_cpor_case_line() -> None:
    labels = [label for label, _ in _SPECS]
    assert "CPOR case lines" in labels
    assert "Promotion plans" in labels  # legacy check retained until table drop


def test_promotion_plan_template_disabled() -> None:
    by_slug = {r["slug"]: r for r in IMPORT_TEMPLATE_ROWS}
    assert by_slug["promotion_plan"]["enabled"] is False
    assert by_slug["promotion_plan"]["hidden"] is True
    assert "cpor_claim_evidence" in by_slug
    assert by_slug["cpor_claim_evidence"]["enabled"] is True


def test_promo_product_ids_uses_cpor_case_line() -> None:
    import asyncio
    from app.services.commercial_planner.intelligence import product_rankings as pr

    db = AsyncMock()

    async def _run() -> set[int]:
        result = MagicMock()
        result.scalars.return_value.all.return_value = [10, 20]
        db.execute.return_value = result
        return await pr._promo_product_ids(db, [10, 20, 30])

    ids = asyncio.run(_run())
    assert ids == {10, 20}
    stmt = db.execute.call_args[0][0]
    assert "cpor_case_line" in str(stmt).lower() or "CporCaseLine" in str(stmt)


def test_promotions_plans_parked(monkeypatch) -> None:
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    res = client.get("/api/v1/promotions/plans")
    assert res.status_code == 200
    assert res.json() == []
    meta = client.get("/api/v1/promotions/meta")
    assert meta.status_code == 200
    assert meta.json().get("parked") is True
