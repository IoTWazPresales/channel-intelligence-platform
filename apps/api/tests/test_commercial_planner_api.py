from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


def test_create_commercial_plan_contract():
    created = SimpleNamespace(id=101)

    async def fake_db():
        sess = MagicMock()
        sess.add = MagicMock()
        sess.commit = AsyncMock()
        sess.refresh = AsyncMock(side_effect=lambda x: setattr(x, "id", created.id))
        yield sess

    app.dependency_overrides[get_db] = fake_db
    r = client.post(
        "/api/v1/commercial-planner/plans",
        json={
            "plan_name": "Q3 Retail Plan",
            "period_start": "2026-07-01",
            "owner": "planner",
            "currency_code": "USD",
        },
    )
    assert r.status_code == 201
    assert r.json()["id"] == 101


def test_patch_plan_rejects_invalid_status():
    plan = SimpleNamespace(id=1, status="draft")

    async def fake_db():
        sess = MagicMock()
        sess.get = AsyncMock(return_value=plan)
        yield sess

    app.dependency_overrides[get_db] = fake_db
    r = client.patch("/api/v1/commercial-planner/plans/1", json={"status": "bogus"})
    assert r.status_code == 400


def test_apply_suggestion_updates_line_units():
    line = SimpleNamespace(
        id=11,
        commercial_plan_id=1,
        customer_id=1,
        distributor_id=1,
        product_id=1,
        target_units=10.0,
        target_srp_local=100.0,
        promo_srp_local=90.0,
        promo_mix_pct=0.5,
        launch_date=None,
        promo_start_date=None,
        notes=None,
        calc_sell_in_price_usd=None,
        calc_buy_price_usd=None,
        calc_promo_reserve_usd=None,
        calc_non_promo_reserve_usd=None,
        calc_internal_gp_usd=None,
        calc_customer_gp_pct=None,
        calc_distributor_gp_pct=None,
        calc_flags=[],
        calc_explanation=None,
        override_customer_margin_pct=None,
        override_customer_rebate_pct=None,
        override_distributor_margin_pct=None,
        override_landed_cost_usd=None,
        override_vat_rate_pct=None,
        override_fx_rate_to_usd=None,
        override_reserve_total_pct=None,
        override_promo_reserve_split_pct=None,
    )

    join_res = MagicMock()
    join_res.one_or_none = MagicMock(return_value=("C1", "Cust One", "D1", "Dist One", "SKU-1", "Widget"))

    async def fake_db():
        sess = MagicMock()
        sess.get = AsyncMock(return_value=line)
        sess.commit = AsyncMock()
        sess.refresh = AsyncMock()
        sess.execute = AsyncMock(return_value=join_res)
        yield sess

    app.dependency_overrides[get_db] = fake_db
    r = client.post(
        "/api/v1/commercial-planner/apply-suggestion",
        json={"line_id": 11, "suggestion_type": "target_units", "value": 42.0},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["target_units"] == 42.0
    assert body["customer_code"] == "C1"
    assert body["product_sku"] == "SKU-1"


def test_customer_term_create_rejects_excessive_margin_stack():
    async def fake_db():
        yield MagicMock()

    app.dependency_overrides[get_db] = fake_db
    r = client.post(
        "/api/v1/commercial-planner/customer-terms",
        json={"customer_id": 1, "customer_margin_pct": 0.8, "customer_rebate_pct": 0.2},
    )
    assert r.status_code == 422


def test_patch_customer_term_rejects_margin_stack():
    from app.models.commercial_planner import CommercialCustomerTerm

    term = SimpleNamespace(
        id=5,
        customer_id=9,
        customer_margin_pct=0.1,
        customer_rebate_pct=0.05,
    )

    async def fake_db():
        sess = MagicMock()

        async def _get(model, pk):
            if model is CommercialCustomerTerm and pk == 5:
                return term
            return None

        sess.get = AsyncMock(side_effect=_get)
        sess.commit = AsyncMock()
        sess.refresh = AsyncMock()
        yield sess

    app.dependency_overrides[get_db] = fake_db
    r = client.patch(
        "/api/v1/commercial-planner/customer-terms/5",
        json={"customer_margin_pct": 0.9, "customer_rebate_pct": 0.05},
    )
    assert r.status_code == 400
    assert "below 0.92" in (r.json().get("detail") or "")


def test_lineup_jobs_endpoint_lists_apply_jobs():
    """GET /commercial-planner/lineup-jobs returns job list with line counts."""
    from types import SimpleNamespace

    fake_row = SimpleNamespace(
        id=99,
        file_name="q2_lineup.xlsx",
        status="completed",
        stage="validated",
        period_label="2026-Q2",
        country_code="ZA",
        currency_code="USD",
        line_count=12,
    )
    fake_result = MagicMock()
    fake_result.all = MagicMock(return_value=[fake_row])

    async def fake_db():
        sess = MagicMock()
        sess.execute = AsyncMock(return_value=fake_result)
        yield sess

    app.dependency_overrides[get_db] = fake_db
    r = client.get("/api/v1/commercial-planner/lineup-jobs")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["id"] == 99
    assert body[0]["line_count"] == 12
    assert body[0]["period_label"] == "2026-Q2"
    assert body[0]["file_name"] == "q2_lineup.xlsx"


def test_lineup_coverage_endpoint_returns_enriched_lines():
    """GET /commercial-planner/lineup-coverage returns enriched lines with pre-computed flags."""
    from decimal import Decimal
    from types import SimpleNamespace

    fake_header = SimpleNamespace(id=1, import_job_id=10)
    fake_line = SimpleNamespace(
        id=1,
        header_id=1,
        source_row_number=5,
        product_id=42,
        part_number_raw="PART-001",
        model_raw="Model X",
        base_unit_raw="NB",
        quantity_units=Decimal("12.0000"),
        msrp_local=Decimal("999.0000"),
        promo_price_local=None,
        dap_local=None,
        disti_margin_pct=Decimal("0.0724"),
        diagnostic_codes=["unknown_customer"],
        raw_row_payload={"customer_token": "UNKNOWN-CUST"},
    )
    fake_coverage_result = MagicMock()
    fake_coverage_result.all = MagicMock(
        return_value=[(fake_line, "2026-Q2", "ZA", "USD", "SKU-X1", "Notebook X1")]
    )

    async def fake_db():
        sess = MagicMock()
        sess.scalar = AsyncMock(return_value=fake_header)
        sess.execute = AsyncMock(return_value=fake_coverage_result)
        yield sess

    app.dependency_overrides[get_db] = fake_db
    r = client.get("/api/v1/commercial-planner/lineup-coverage?job_id=10")
    assert r.status_code == 200
    lines = r.json()
    assert len(lines) == 1
    ln = lines[0]
    # Pre-computed flags — frontend must not derive these from diagnostic_codes itself.
    assert ln["has_unknown_customer"] is True
    assert ln["has_warnings"] is True
    # Numeric fields are float, never Decimal strings.
    assert isinstance(ln["disti_margin_pct"], float)
    assert abs(ln["disti_margin_pct"] - 0.0724) < 1e-6
    # Product enrichment from DimProduct join.
    assert ln["product_sku"] == "SKU-X1"
    assert ln["product_name"] == "Notebook X1"
    # Customer token surfaced from raw_row_payload.
    assert ln["customer_token"] == "UNKNOWN-CUST"
    # diagnostic_codes is included for audit reference.
    assert "unknown_customer" in ln["diagnostic_codes"]


def test_lineup_coverage_returns_400_when_header_not_found():
    """GET /commercial-planner/lineup-coverage returns 400 when job is not a valid apply job."""

    async def fake_db():
        sess = MagicMock()
        sess.scalar = AsyncMock(return_value=None)  # header not found
        yield sess

    app.dependency_overrides[get_db] = fake_db
    r = client.get("/api/v1/commercial-planner/lineup-coverage?job_id=999")
    assert r.status_code == 400
    assert "job_id=999" in r.json().get("detail", "")


def test_patch_plan_line_rejects_unknown_customer_id():
    from app.models.commercial_planner import CommercialPlanLine
    from app.models.dimensions import DimCustomer

    line = SimpleNamespace(
        id=1,
        commercial_plan_id=1,
        customer_id=1,
        distributor_id=1,
        product_id=1,
        target_units=1.0,
        target_srp_local=100.0,
        promo_srp_local=None,
        promo_mix_pct=0.5,
        launch_date=None,
        promo_start_date=None,
        notes=None,
        override_customer_margin_pct=None,
        override_customer_rebate_pct=None,
        override_distributor_margin_pct=None,
        override_landed_cost_usd=None,
        override_vat_rate_pct=None,
        override_fx_rate_to_usd=None,
        override_reserve_total_pct=None,
        override_promo_reserve_split_pct=None,
        calc_sell_in_price_usd=None,
        calc_buy_price_usd=None,
        calc_promo_reserve_usd=None,
        calc_non_promo_reserve_usd=None,
        calc_internal_gp_usd=None,
        calc_customer_gp_pct=None,
        calc_distributor_gp_pct=None,
        calc_flags=[],
        calc_explanation=None,
    )

    async def fake_db():
        sess = MagicMock()

        async def _get(model, pk):
            if model is CommercialPlanLine and pk == 1:
                return line
            if model is DimCustomer and pk == 99999:
                return None
            return SimpleNamespace(id=pk)

        sess.get = AsyncMock(side_effect=_get)
        sess.commit = AsyncMock()
        sess.refresh = AsyncMock()
        join_res = MagicMock()
        join_res.one_or_none = MagicMock(return_value=("C", "N", "D", "DN", "S", "P"))
        sess.execute = AsyncMock(return_value=join_res)
        yield sess

    app.dependency_overrides[get_db] = fake_db
    r = client.patch("/api/v1/commercial-planner/lines/1", json={"customer_id": 99999})
    assert r.status_code == 400
    assert "Unknown customer_id" in (r.json().get("detail") or "")
