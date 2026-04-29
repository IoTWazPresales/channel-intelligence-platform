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
    join_res.one_or_none = MagicMock(
        return_value=(
            "C1",
            "Cust One",
            "D1",
            "Dist One",
            "SKU-1",
            "Widget",
            "PN-1",
            "Model A",
            "Sales A",
            "Laptops",
            "Clamshell",
            "active",
            "ThinkPad",
            "T14",
            "PCSD",
            {"cpu": "i7-1360P"},
            0.12,
            0.03,
            0.08,
            0.15,
            18.5,
            0.10,
            0.50,
            420.0,
        )
    )

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
    assert body["product_part_number"] == "PN-1"
    assert body["product_model_name"] == "Model A"
    assert body["product_sales_model_name"] == "Sales A"
    assert body["product_category"] == "Laptops"
    assert body["product_form_factor"] == "Clamshell"
    assert body["product_lifecycle_status"] == "active"
    assert body["product_line"] == "ThinkPad"
    assert body["product_series_name"] == "T14"
    assert body["product_business_unit"] == "PCSD"
    assert body["product_spec_cpu"] == "i7-1360P"
    assert body["effective_customer_margin_pct"] == 0.12
    assert body["effective_fx_rate_to_usd"] == 18.5
    assert body["effective_controlled_cost_usd_per_unit"] == 420.0


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
        month_split_json=None,
        dap_local=None,
        actual_dap_local=None,
        disti_cost_local=None,
        rebate_pct=None,
        dealer_margin_pct=None,
        vat_pct=None,
        disti_margin_pct=Decimal("0.0724"),
        diagnostic_codes=["unknown_customer"],
        raw_row_payload={"customer_token": "UNKNOWN-CUST"},
    )
    fake_coverage_result = MagicMock()
    fake_coverage_result.all = MagicMock(
        return_value=[(fake_line, "2026-Q2", "ZA", "USD", "SKU-X1", "Notebook X1", None, None, None, None, None, None)]
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


def test_lineup_coverage_includes_extended_commercial_fields():
    """GET /commercial-planner/lineup-coverage includes new economic evidence fields."""
    from decimal import Decimal
    from types import SimpleNamespace

    fake_header = SimpleNamespace(id=1, import_job_id=20)
    fake_line = SimpleNamespace(
        id=5,
        header_id=1,
        source_row_number=3,
        product_id=10,
        part_number_raw="PN-X",
        model_raw="Model Z",
        base_unit_raw="UNT",
        quantity_units=Decimal("8.0"),
        msrp_local=Decimal("1200.0"),
        promo_price_local=Decimal("1100.0"),
        month_split_json={"Apr": 2.0, "May": 3.0, "Jun": 3.0},
        dap_local=Decimal("900.0"),
        actual_dap_local=Decimal("880.0"),
        disti_cost_local=Decimal("750.0"),
        rebate_pct=Decimal("0.03"),
        dealer_margin_pct=Decimal("0.12"),
        vat_pct=Decimal("0.15"),
        disti_margin_pct=Decimal("0.08"),
        diagnostic_codes=[],
        raw_row_payload={"customer_token": "KNOWN-ACCT"},
    )
    fake_result = MagicMock()
    # Tuple now includes (header_customer_id, header_customer_code, header_customer_name)
    fake_result.all = MagicMock(
        return_value=[
            (fake_line, "2026-Q2", "ZA", "USD", "SKU-Z1", "Widget Z", 7, "CUST-A", "Customer A", 3, "DIST-1", "Distributor One")
        ]
    )

    async def fake_db():
        sess = MagicMock()
        sess.scalar = AsyncMock(return_value=fake_header)
        sess.execute = AsyncMock(return_value=fake_result)
        yield sess

    app.dependency_overrides[get_db] = fake_db
    r = client.get("/api/v1/commercial-planner/lineup-coverage?job_id=20")
    assert r.status_code == 200
    ln = r.json()[0]
    # Extended economic fields must be present and numeric (not Decimal strings).
    assert isinstance(ln["actual_dap_local"], float)
    assert abs(ln["actual_dap_local"] - 880.0) < 1e-6
    assert isinstance(ln["disti_cost_local"], float)
    assert abs(ln["disti_cost_local"] - 750.0) < 1e-6
    assert isinstance(ln["rebate_pct"], float)
    assert abs(ln["rebate_pct"] - 0.03) < 1e-6
    assert isinstance(ln["dealer_margin_pct"], float)
    assert abs(ln["dealer_margin_pct"] - 0.12) < 1e-6
    assert isinstance(ln["vat_pct"], float)
    assert abs(ln["vat_pct"] - 0.15) < 1e-6
    # Header customer info from the aliased DimCustomer join.
    assert ln["header_customer_id"] == 7
    assert ln["header_customer_code"] == "CUST-A"
    assert ln["header_customer_name"] == "Customer A"
    assert ln["header_distributor_id"] == 3
    assert ln["header_distributor_code"] == "DIST-1"
    assert ln["header_distributor_name"] == "Distributor One"
    # month_split_json is passed through as-is (dict or null).
    assert ln["month_split_json"] == {"Apr": 2.0, "May": 3.0, "Jun": 3.0}


def test_lineup_product_gaps_returns_per_product_gap_status():
    """GET /commercial-planner/lineup-product-gaps aggregates evidence and surfaces gaps."""
    from decimal import Decimal
    from types import SimpleNamespace

    fake_header = SimpleNamespace(id=1, import_job_id=30)
    fake_row = MagicMock()
    fake_row.product_id = 42
    fake_row.product_sku = "NB-X1"
    fake_row.product_name = "Notebook X1"
    fake_row.dap_local = Decimal("850.0")
    fake_row.actual_dap_local = None
    fake_row.disti_cost_local = None
    fake_row.vat_pct = Decimal("0.15")
    fake_row.disti_margin_pct = Decimal("0.0724")
    fake_row.rebate_pct = None
    fake_row.dealer_margin_pct = None
    fake_row.total_quantity_units = Decimal("12.0")
    fake_row.msrp_local = Decimal("999.0")
    fake_row.promo_price_local = Decimal("899.0")
    fake_row.period_label = "2026-Q2"
    fake_row.sku_assumption_id = None  # no assumption exists

    fake_result = MagicMock()
    fake_result.all = MagicMock(return_value=[fake_row])

    async def fake_db():
        sess = MagicMock()
        sess.scalar = AsyncMock(return_value=fake_header)
        sess.execute = AsyncMock(return_value=fake_result)
        yield sess

    app.dependency_overrides[get_db] = fake_db
    r = client.get("/api/v1/commercial-planner/lineup-product-gaps?job_id=30")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    item = items[0]
    assert item["product_id"] == 42
    assert item["product_sku"] == "NB-X1"
    assert item["has_sku_assumption"] is False
    # Gap flags must be present.
    assert "missing_sku_assumption" in item["assumption_gaps"]
    # dap_local is present so no_cost_evidence_in_lineup should NOT appear.
    assert "no_cost_evidence_in_lineup" not in item["assumption_gaps"]
    # vat_pct is present so no_vat_pct_in_lineup should NOT appear.
    assert "no_vat_pct_in_lineup" not in item["assumption_gaps"]
    # rebate_pct is null → no dealer_margin gap flag (rebate is not part of gap rules).
    # Lineup evidence nested dict.
    ev = item["lineup_evidence"]
    assert isinstance(ev["dap_local"], float)
    assert abs(ev["dap_local"] - 850.0) < 1e-6
    assert isinstance(ev["total_quantity_units"], float)
    assert abs(ev["total_quantity_units"] - 12.0) < 1e-6
    assert ev["actual_dap_local"] is None
    # Cost semantics note must be present and mention DAP.
    assert "DAP" in item["cost_semantics_note"]
    assert "landed_cost_usd" in item["cost_semantics_note"]


def test_lineup_product_gaps_returns_400_for_invalid_job():
    """GET /commercial-planner/lineup-product-gaps returns 400 when job is not a valid apply job."""

    async def fake_db():
        sess = MagicMock()
        sess.scalar = AsyncMock(return_value=None)
        yield sess

    app.dependency_overrides[get_db] = fake_db
    r = client.get("/api/v1/commercial-planner/lineup-product-gaps?job_id=999")
    assert r.status_code == 400
    assert "job_id=999" in r.json().get("detail", "")


def test_lineup_evidence_endpoint_returns_aggregated_evidence():
    """GET /commercial-planner/lineup-evidence returns evidence from the latest apply job."""
    from decimal import Decimal

    fake_row = SimpleNamespace(
        msrp_local=Decimal("999"),
        promo_price_local=Decimal("899"),
        dap_local=Decimal("750"),
        actual_dap_local=None,
        disti_margin_pct=Decimal("0.08"),
        vat_pct=Decimal("0.15"),
        rebate_pct=Decimal("0.03"),
        total_quantity_units=Decimal("216"),
        line_count=2,
        period_label="2026-Q2",
    )
    fake_execute_result = MagicMock()
    fake_execute_result.one = MagicMock(return_value=fake_row)

    async def fake_db():
        sess = MagicMock()
        sess.scalar = AsyncMock(return_value=10)  # latest_job_id = 10
        sess.execute = AsyncMock(return_value=fake_execute_result)
        yield sess

    app.dependency_overrides[get_db] = fake_db
    r = client.get("/api/v1/commercial-planner/lineup-evidence?product_id=1")
    assert r.status_code == 200
    body = r.json()
    assert body["product_id"] == 1
    assert body["lineup_job_id"] == 10
    assert body["evidence"] is not None
    ev = body["evidence"]
    assert ev["msrp_local"] == pytest.approx(999.0)
    assert ev["promo_price_local"] == pytest.approx(899.0)
    assert ev["dap_local"] == pytest.approx(750.0)
    assert ev["actual_dap_local"] is None
    assert ev["line_count"] == 2
    assert ev["period_label"] == "2026-Q2"
    # Cost semantics note must mention DAP and landed_cost_usd
    assert "DAP" in body["cost_semantics_note"]
    assert "landed_cost_usd" in body["cost_semantics_note"]


def test_lineup_evidence_endpoint_returns_null_evidence_when_no_lineup_data():
    """GET /commercial-planner/lineup-evidence returns evidence=null when no apply job exists for that product."""

    async def fake_db():
        sess = MagicMock()
        sess.scalar = AsyncMock(return_value=None)
        yield sess

    app.dependency_overrides[get_db] = fake_db
    r = client.get("/api/v1/commercial-planner/lineup-evidence?product_id=999")
    assert r.status_code == 200
    body = r.json()
    assert body["product_id"] == 999
    assert body["lineup_job_id"] is None
    assert body["evidence"] is None
    assert "DAP" in body["cost_semantics_note"]


def test_plan_readiness_reports_missing_defaults():
    """GET /commercial-planner/plans/{plan_id}/readiness counts lines with missing terms and SKU assumptions."""
    from app.models.commercial_planner import CommercialCustomerTerm, CommercialDistributorTerm, CommercialPlanLine, CommercialSkuAssumption

    fake_plan = SimpleNamespace(id=1)
    fake_line = SimpleNamespace(
        id=11,
        commercial_plan_id=1,
        customer_id=7,
        distributor_id=8,
        product_id=9,
        calc_flags=[],
    )

    call_count = 0

    async def fake_db():
        sess = MagicMock()
        sess.get = AsyncMock(return_value=fake_plan)

        nonlocal call_count
        call_count = 0

        async def execute_side(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                # CommercialPlanLine query
                result.scalars.return_value.all.return_value = [fake_line]
            else:
                # customer_term / distributor_term / sku_assumption queries — all empty
                result.scalars.return_value.all.return_value = []
            return result

        sess.execute = AsyncMock(side_effect=execute_side)
        yield sess

    app.dependency_overrides[get_db] = fake_db
    r = client.get("/api/v1/commercial-planner/plans/1/readiness")
    assert r.status_code == 200
    body = r.json()
    assert body["plan_id"] == 1
    assert body["line_count"] == 1
    assert body["missing_customer_term"] == 1
    assert body["missing_distributor_term"] == 1
    assert body["missing_sku_assumption"] == 1
    assert body["ready"] is False
    assert "missing" in body["readiness_summary"].lower()


def test_suggestions_batched_endpoint_returns_meta_structure():
    """GET /plans/{plan_id}/suggestions returns _meta.data_sources for each line (batched queries)."""
    from decimal import Decimal

    fake_line = SimpleNamespace(
        id=11,
        commercial_plan_id=1,
        customer_id=1,
        product_id=1,
        target_srp_local=Decimal("1000"),
        promo_mix_pct=Decimal("0.5"),
    )

    execute_count = 0

    async def fake_db():
        sess = MagicMock()
        nonlocal execute_count
        execute_count = 0

        async def execute_side(stmt):
            nonlocal execute_count
            execute_count += 1
            result = MagicMock()
            if execute_count == 1:
                # CommercialPlanLine batch
                result.scalars.return_value.all.return_value = [fake_line]
            else:
                result.all.return_value = []
                result.scalars.return_value.all.return_value = []
            return result

        sess.execute = AsyncMock(side_effect=execute_side)
        sess.scalar = AsyncMock(return_value=None)  # no lineup job
        yield sess

    app.dependency_overrides[get_db] = fake_db
    r = client.get("/api/v1/commercial-planner/plans/1/suggestions")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["line_id"] == 11
    assert "_meta" in data[0]
    meta = data[0]["_meta"]
    assert "data_sources" in meta
    assert meta["lineup_job_id"] is None
    assert meta["data_sources"]["lineup"] is False
    # Pricing suggestion should be low-confidence with no anchors
    pricing = next(s for s in data[0]["suggestions"] if s["type"] == "pricing_band")
    assert pricing["confidence"] == "low"


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
        join_res.one_or_none = MagicMock(
            return_value=(
                "C",
                "N",
                "D",
                "DN",
                "S",
                "P",
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
            )
        )
        sess.execute = AsyncMock(return_value=join_res)
        yield sess

    app.dependency_overrides[get_db] = fake_db
    r = client.patch("/api/v1/commercial-planner/lines/1", json={"customer_id": 99999})
    assert r.status_code == 400
    assert "Unknown customer_id" in (r.json().get("detail") or "")


def test_product_specs_from_json_extracts_whitelisted_keys():
    from app.services.commercial_planner.read_model import product_specs_from_json

    out = product_specs_from_json({"CPU": "i9", "RAM": "32GB", "import_staging": {"storage": "1TB"}})
    assert out["product_spec_cpu"] == "i9"
    assert out["product_spec_ram"] == "32GB"
    assert out["product_spec_storage"] == "1TB"
    assert out["product_spec_warranty"] is None


def test_product_specs_from_json_returns_nulls_without_invention():
    from app.services.commercial_planner.read_model import product_specs_from_json

    out = product_specs_from_json({"unrelated": "x"})
    assert all(out[k] is None for k in out)


def test_local_prices_from_usd_requires_positive_fx():
    from app.services.commercial_planner.read_model import local_prices_from_usd

    assert local_prices_from_usd(10.0, 8.0, None) == (None, None)
    assert local_prices_from_usd(10.0, 8.0, 0.0) == (None, None)
    a, b = local_prices_from_usd(10.0, 8.0, 18.5)
    assert a is not None and abs(a - 185.0) < 1e-6
    assert b is not None and abs(b - 148.0) < 1e-6


def test_effective_commercial_fields_flat_prefers_line_overrides():
    from types import SimpleNamespace

    from app.services.commercial_planner.read_model import effective_commercial_fields_flat

    line = SimpleNamespace(
        override_customer_margin_pct=0.2,
        override_customer_rebate_pct=None,
        override_distributor_margin_pct=None,
        override_vat_rate_pct=None,
        override_fx_rate_to_usd=None,
        override_reserve_total_pct=None,
        override_promo_reserve_split_pct=None,
        override_landed_cost_usd=None,
    )
    out = effective_commercial_fields_flat(
        line,
        customer_margin_pct=0.1,
        customer_rebate_pct=0.02,
        distributor_margin_pct=0.08,
        sku_vat_rate_pct=0.15,
        sku_fx_rate_to_usd=18.0,
        sku_reserve_total_pct=0.1,
        sku_promo_reserve_split_pct=0.5,
        sku_landed_cost_usd=400.0,
    )
    assert out["effective_customer_margin_pct"] == 0.2
    assert out["effective_customer_rebate_pct"] == 0.02
    assert out["effective_fx_rate_to_usd"] == 18.0
    assert out["effective_controlled_cost_usd_per_unit"] == 400.0


def test_plan_line_read_model_extensions_merges_specs_and_local_prices():
    from types import SimpleNamespace

    from app.services.commercial_planner.read_model import plan_line_read_model_extensions

    line = SimpleNamespace(
        calc_sell_in_price_usd=10.0,
        calc_buy_price_usd=8.0,
        override_customer_margin_pct=None,
        override_customer_rebate_pct=None,
        override_distributor_margin_pct=None,
        override_vat_rate_pct=None,
        override_fx_rate_to_usd=None,
        override_reserve_total_pct=None,
        override_promo_reserve_split_pct=None,
        override_landed_cost_usd=None,
    )
    ext = plan_line_read_model_extensions(
        line,
        {"cpu": "i5", "RAM": "16GB"},
        customer_margin_pct=0.1,
        customer_rebate_pct=0.02,
        distributor_margin_pct=0.08,
        sku_vat_rate_pct=0.15,
        sku_fx_rate_to_usd=2.0,
        sku_reserve_total_pct=0.1,
        sku_promo_reserve_split_pct=0.5,
        sku_landed_cost_usd=100.0,
    )
    assert ext["product_spec_cpu"] == "i5"
    assert ext.get("product_spec_processor") is None
    assert ext["product_spec_ram"] == "16GB"
    assert ext["effective_fx_rate_to_usd"] == 2.0
    assert ext["calc_sell_in_price_local"] == 20.0
    assert ext["calc_distributor_net_local"] == 16.0


def test_plan_line_read_model_extensions_splits_processor_and_cpu_specs():
    from types import SimpleNamespace

    from app.services.commercial_planner.read_model import plan_line_read_model_extensions

    line = SimpleNamespace(
        calc_sell_in_price_usd=None,
        calc_buy_price_usd=None,
        override_customer_margin_pct=None,
        override_customer_rebate_pct=None,
        override_distributor_margin_pct=None,
        override_vat_rate_pct=None,
        override_fx_rate_to_usd=None,
        override_reserve_total_pct=None,
        override_promo_reserve_split_pct=None,
        override_landed_cost_usd=None,
    )
    ext = plan_line_read_model_extensions(
        line,
        {"Processor": "Intel Core Ultra 7", "cpu": "Snapdragon X"},
        customer_margin_pct=0.1,
        customer_rebate_pct=0.02,
        distributor_margin_pct=0.08,
        sku_vat_rate_pct=0.15,
        sku_fx_rate_to_usd=1.0,
        sku_reserve_total_pct=0.1,
        sku_promo_reserve_split_pct=0.5,
        sku_landed_cost_usd=100.0,
    )
    assert ext["product_spec_processor"] == "Intel Core Ultra 7"
    assert ext["product_spec_cpu"] == "Snapdragon X"


# ─── Commercial Lineup Case tests ────────────────────────────────────────────


def _make_case(
    id=1,
    commercial_plan_id=None,
    commercial_status="draft_imported",
    period_label="Q2 2026",
    currency_code="USD",
    country_code="US",
    file_name=None,
    notes=None,
    accepted_at=None,
    accepted_by=None,
    created_at=None,
):
    from types import SimpleNamespace
    return SimpleNamespace(
        id=id,
        import_job_id=None,
        commercial_plan_id=commercial_plan_id,
        file_name=file_name,
        period_label=period_label,
        country_code=country_code,
        currency_code=currency_code,
        import_intent="current_working_lineup",
        source_context="commercial_planner",
        commercial_status=commercial_status,
        notes=notes,
        accepted_at=accepted_at,
        accepted_by=accepted_by,
        created_at=created_at,
    )


def test_commercial_lineup_case_create():
    """POST /lineup-cases creates a case and returns id."""
    created_case = _make_case(id=42)

    async def fake_db():
        sess = MagicMock()
        sess.add = MagicMock()
        sess.commit = AsyncMock()
        sess.refresh = AsyncMock(side_effect=lambda x: setattr(x, "id", 42))
        sess.get = AsyncMock(return_value=None)
        count_result = MagicMock()
        count_result.scalar_one = MagicMock(return_value=0)
        sess.execute = AsyncMock(return_value=count_result)
        yield sess

    app.dependency_overrides[get_db] = fake_db
    r = client.post(
        "/api/v1/commercial-planner/lineup-cases",
        json={"period_label": "Q2 2026", "currency_code": "USD", "country_code": "US"},
    )
    assert r.status_code == 201
    body = r.json()
    assert "id" in body
    assert body["commercial_status"] == "draft_imported"
    assert body["line_count"] == 0


def test_commercial_lineup_case_list_by_plan():
    """GET /lineup-cases?plan_id= returns cases for a plan."""
    case1 = _make_case(id=1, commercial_plan_id=5, period_label="Q1 2026")
    case2 = _make_case(id=2, commercial_plan_id=5, period_label="Q2 2026")

    # First call: list of cases; subsequent calls: line count queries (scalar_one=0)
    call_count = {"n": 0}

    async def fake_db():
        sess = MagicMock()
        cases_result = MagicMock()
        cases_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[case1, case2])))
        count_result = MagicMock()
        count_result.scalar_one = MagicMock(return_value=0)

        async def _execute(stmt):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return cases_result
            return count_result

        sess.execute = _execute
        yield sess

    app.dependency_overrides[get_db] = fake_db
    r = client.get("/api/v1/commercial-planner/lineup-cases?plan_id=5")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert len(body) == 2
    assert body[0]["period_label"] == "Q1 2026"
    assert body[1]["period_label"] == "Q2 2026"


def test_commercial_lineup_case_status_transition_valid():
    """PATCH /lineup-cases/{id}/status from pending_review→accepted sets accepted_at."""
    case = _make_case(id=10, commercial_status="pending_review")

    async def fake_db():
        sess = MagicMock()
        sess.get = AsyncMock(return_value=case)
        sess.commit = AsyncMock()
        sess.refresh = AsyncMock()
        count_result = MagicMock()
        count_result.scalar_one = MagicMock(return_value=0)
        sess.execute = AsyncMock(return_value=count_result)
        yield sess

    app.dependency_overrides[get_db] = fake_db
    r = client.patch(
        "/api/v1/commercial-planner/lineup-cases/10/status",
        json={"status": "accepted", "accepted_by": "manager@example.com"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["commercial_status"] == "accepted"
    assert body["accepted_by"] == "manager@example.com"
    assert body["accepted_at"] is not None


def test_commercial_lineup_case_status_transition_invalid():
    """PATCH /lineup-cases/{id}/status returns 400 for forbidden transition."""
    case = _make_case(id=11, commercial_status="received_closed")

    async def fake_db():
        sess = MagicMock()
        sess.get = AsyncMock(return_value=case)
        yield sess

    app.dependency_overrides[get_db] = fake_db
    r = client.patch(
        "/api/v1/commercial-planner/lineup-cases/11/status",
        json={"status": "validated"},
    )
    assert r.status_code == 400
    assert "Cannot transition" in r.json()["detail"]


def test_commercial_lineup_case_delete_draft_only():
    """DELETE /lineup-cases/{id} works for draft_imported, 409 for accepted."""
    draft_case = _make_case(id=20, commercial_status="draft_imported")

    async def fake_db_draft():
        sess = MagicMock()
        sess.get = AsyncMock(return_value=draft_case)
        sess.delete = AsyncMock()
        sess.commit = AsyncMock()
        yield sess

    app.dependency_overrides[get_db] = fake_db_draft
    r = client.delete("/api/v1/commercial-planner/lineup-cases/20")
    assert r.status_code == 204

    accepted_case = _make_case(id=21, commercial_status="accepted")

    async def fake_db_accepted():
        sess = MagicMock()
        sess.get = AsyncMock(return_value=accepted_case)
        yield sess

    app.dependency_overrides[get_db] = fake_db_accepted
    r = client.delete("/api/v1/commercial-planner/lineup-cases/21")
    assert r.status_code == 409
    assert "draft_imported" in r.json()["detail"]


def test_current_lineup_template_exists():
    """The current_lineup template slug is present in template definitions."""
    from app.services.imports.template_definitions import IMPORT_TEMPLATE_ROWS

    slugs = [t["slug"] for t in IMPORT_TEMPLATE_ROWS]
    assert "current_lineup" in slugs
    template = next(t for t in IMPORT_TEMPLATE_ROWS if t["slug"] == "current_lineup")
    assert template["enabled"] is True
    assert template["pipeline_handler"] == "stub_noop"
    assert "sku_raw" in template["expected_columns"]
    assert "promo_price_evidence_local" in template["expected_columns"]


def test_current_lineup_template_hidden():
    """current_lineup template is hidden from generic imports UI."""
    from app.services.imports.template_definitions import IMPORT_TEMPLATE_ROWS

    template = next(t for t in IMPORT_TEMPLATE_ROWS if t["slug"] == "current_lineup")
    assert template["hidden"] is True, "current_lineup must be hidden from generic imports UI"
    assert template["enabled"] is True  # Still enabled for parse-upload path
    assert template["pipeline_handler"] == "stub_noop"


def test_current_lineup_source_in_default_sources():
    """current_lineup_system is present in DEFAULT_SOURCES with correct template slug."""
    from app.services.imports.template_definitions import DEFAULT_SOURCES

    codes = [s[0] for s in DEFAULT_SOURCES]
    assert "current_lineup_system" in codes, "current_lineup_system must be in DEFAULT_SOURCES"
    source = next(s for s in DEFAULT_SOURCES if s[0] == "current_lineup_system")
    assert source[2] == "current_lineup", f"Expected template_slug 'current_lineup', got '{source[2]}'"
    assert source[3] == "planning_extract", f"Expected source_kind 'planning_extract', got '{source[3]}'"


# ─── parse-upload endpoint tests ─────────────────────────────────────────────


def _make_parse_result(**kwargs):
    from app.services.commercial_planner.lineup_case_parser import ParseResult

    defaults = {
        "case_id": 1,
        "import_job_id": 99,
        "total_rows": 3,
        "resolved_products": 2,
        "unresolved_products": 1,
        "line_count": 3,
        "warnings": [],
    }
    defaults.update(kwargs)
    return ParseResult(**defaults)


def test_parse_upload_creates_lineup_lines():
    """POST multipart to parse-upload returns line_count and job audit fields."""
    import io
    from unittest.mock import patch

    case = _make_case(id=1, commercial_status="draft_imported")

    async def fake_db():
        sess = MagicMock()
        sess.get = AsyncMock(return_value=case)
        count_result = MagicMock()
        count_result.scalar_one = MagicMock(return_value=0)
        sess.execute = AsyncMock(return_value=count_result)
        yield sess

    app.dependency_overrides[get_db] = fake_db

    with patch(
        "app.api.v1.endpoints.commercial_planner.parse_current_lineup_file",
        new=AsyncMock(return_value=_make_parse_result(line_count=3, resolved_products=2, unresolved_products=1)),
    ):
        csv_bytes = b"sku,qty,msrp\nSKU-A,10,999\nSKU-B,5,799\nSKU-C,20,1299\n"
        r = client.post(
            "/api/v1/commercial-planner/lineup-cases/1/parse-upload",
            files={"file": ("lineup.csv", io.BytesIO(csv_bytes), "text/csv")},
        )

    assert r.status_code == 200
    body = r.json()
    assert body["line_count"] == 3
    assert body["import_job_id"] == 99
    assert body["case_id"] == 1
    assert body["total_rows"] == 3


def test_parse_upload_resolves_products():
    """Resolved products count is reflected in the response."""
    import io
    from unittest.mock import patch

    case = _make_case(id=2, commercial_status="draft_imported")

    async def fake_db():
        sess = MagicMock()
        sess.get = AsyncMock(return_value=case)
        count_result = MagicMock()
        count_result.scalar_one = MagicMock(return_value=0)
        sess.execute = AsyncMock(return_value=count_result)
        yield sess

    app.dependency_overrides[get_db] = fake_db

    with patch(
        "app.api.v1.endpoints.commercial_planner.parse_current_lineup_file",
        new=AsyncMock(return_value=_make_parse_result(case_id=2, resolved_products=5, unresolved_products=0, total_rows=5, line_count=5)),
    ):
        csv_bytes = b"sku,qty\nSKU-1,10\n"
        r = client.post(
            "/api/v1/commercial-planner/lineup-cases/2/parse-upload",
            files={"file": ("lineup.csv", io.BytesIO(csv_bytes), "text/csv")},
        )

    assert r.status_code == 200
    body = r.json()
    assert body["resolved_products"] == 5
    assert body["unresolved_products"] == 0


def test_parse_upload_dap_stored_as_evidence_not_cost():
    """Response contains dap field name as evidence, no landed_cost_usd in parse result."""
    import io
    from unittest.mock import patch

    case = _make_case(id=3, commercial_status="draft_imported")

    async def fake_db():
        sess = MagicMock()
        sess.get = AsyncMock(return_value=case)
        count_result = MagicMock()
        count_result.scalar_one = MagicMock(return_value=0)
        sess.execute = AsyncMock(return_value=count_result)
        yield sess

    app.dependency_overrides[get_db] = fake_db

    result = _make_parse_result(case_id=3)
    with patch(
        "app.api.v1.endpoints.commercial_planner.parse_current_lineup_file",
        new=AsyncMock(return_value=result),
    ):
        csv_bytes = b"sku,dap,qty\nSKU-A,50.0,10\n"
        r = client.post(
            "/api/v1/commercial-planner/lineup-cases/3/parse-upload",
            files={"file": ("lineup.csv", io.BytesIO(csv_bytes), "text/csv")},
        )

    assert r.status_code == 200
    body = r.json()
    # Response must not include landed_cost_usd — DAP is evidence only
    assert "landed_cost_usd" not in body


def test_parse_upload_unresolved_customer_stored_as_token():
    """Unresolved customers are counted in unresolved; parse still succeeds."""
    import io
    from unittest.mock import patch

    case = _make_case(id=4, commercial_status="draft_imported")

    async def fake_db():
        sess = MagicMock()
        sess.get = AsyncMock(return_value=case)
        count_result = MagicMock()
        count_result.scalar_one = MagicMock(return_value=0)
        sess.execute = AsyncMock(return_value=count_result)
        yield sess

    app.dependency_overrides[get_db] = fake_db

    result = _make_parse_result(case_id=4, warnings=["unknown_customer for row 1"])
    with patch(
        "app.api.v1.endpoints.commercial_planner.parse_current_lineup_file",
        new=AsyncMock(return_value=result),
    ):
        csv_bytes = b"sku,customer,qty\nSKU-A,UNKNOWN-CUST,10\n"
        r = client.post(
            "/api/v1/commercial-planner/lineup-cases/4/parse-upload",
            files={"file": ("lineup.csv", io.BytesIO(csv_bytes), "text/csv")},
        )

    assert r.status_code == 200
    body = r.json()
    assert "unknown_customer for row 1" in body["warnings"]


def test_parse_upload_empty_file_returns_400():
    """Empty file upload returns 400 before parse is attempted."""
    import io

    case = _make_case(id=5, commercial_status="draft_imported")

    async def fake_db():
        sess = MagicMock()
        sess.get = AsyncMock(return_value=case)
        count_result = MagicMock()
        count_result.scalar_one = MagicMock(return_value=0)
        sess.execute = AsyncMock(return_value=count_result)
        yield sess

    app.dependency_overrides[get_db] = fake_db
    r = client.post(
        "/api/v1/commercial-planner/lineup-cases/5/parse-upload",
        files={"file": ("empty.csv", io.BytesIO(b""), "text/csv")},
    )
    assert r.status_code == 400
    assert "empty" in r.json()["detail"].lower()


def test_parse_upload_rejects_non_draft_case():
    """409 returned when case is not in draft_imported status."""
    import io

    case = _make_case(id=6, commercial_status="accepted")

    async def fake_db():
        sess = MagicMock()
        sess.get = AsyncMock(return_value=case)
        yield sess

    app.dependency_overrides[get_db] = fake_db
    r = client.post(
        "/api/v1/commercial-planner/lineup-cases/6/parse-upload",
        files={"file": ("lineup.csv", io.BytesIO(b"sku\nSKU-A"), "text/csv")},
    )
    assert r.status_code == 409
    assert "draft_imported" in r.json()["detail"]


# ─── column-metadata endpoint tests ──────────────────────────────────────────


def test_column_metadata_catalogue_coverage():
    """GET /plans/{id}/column-metadata returns catalogue counts for plan's products."""
    from types import SimpleNamespace

    plan = SimpleNamespace(id=10)

    cat_row = SimpleNamespace(
        category=8,
        form_factor=5,
        lifecycle_status=10,
        product_line=9,
        series_name=4,
        business_unit=10,
        part_number=10,
        sales_model_name=7,
        model_name=10,
    )

    call_count = {"n": 0}

    async def fake_db():
        sess = MagicMock()
        sess.get = AsyncMock(return_value=plan)

        total_result = MagicMock()
        total_result.scalar_one = MagicMock(return_value=10)
        line_count_result = MagicMock()
        line_count_result.scalar_one = MagicMock(return_value=42)
        cat_result = MagicMock()
        cat_result.one = MagicMock(return_value=cat_row)
        spec_scalars = MagicMock()
        spec_scalars.all.return_value = []
        spec_wrap = MagicMock()
        spec_wrap.scalars.return_value = spec_scalars

        async def _execute(stmt, *args, **kwargs):
            call_count["n"] += 1
            # Endpoint order: plan_line_count, distinct product_id count, catalogue agg, specs rows
            if call_count["n"] == 1:
                return line_count_result
            if call_count["n"] == 2:
                return total_result
            if call_count["n"] == 3:
                return cat_result
            return spec_wrap

        sess.execute = AsyncMock(side_effect=_execute)
        yield sess

    app.dependency_overrides[get_db] = fake_db
    r = client.get("/api/v1/commercial-planner/plans/10/column-metadata")
    assert r.status_code == 200
    body = r.json()
    assert body["total_products"] == 10
    assert body.get("plan_line_count") == 42
    assert body["catalogue"]["category"] == 8
    assert body["catalogue"]["lifecycle_status"] == 10
    assert body["catalogue"]["business_unit"] == 10
    assert isinstance(body["spec_keys"], dict)


# ─── Phase 1 parser hardening tests ─────────────────────────────────────────


def test_parse_upload_creates_import_job_with_correct_source():
    """Parser uses SourceDefinition.id for ImportJob.source_id; never falls back to 1."""
    import asyncio

    from app.services.commercial_planner.lineup_case_parser import parse_current_lineup_file

    fake_source = SimpleNamespace(id=77)
    fake_case = SimpleNamespace(id=10, import_job_id=None, file_name=None)
    added: list[object] = []

    async def run():
        db = MagicMock()
        db.get = AsyncMock(return_value=fake_case)
        db.scalar = AsyncMock(return_value=fake_source)

        flush_n = {"n": 0}

        async def _flush():
            flush_n["n"] += 1
            if flush_n["n"] == 1 and added:
                added[0].id = 200  # type: ignore[attr-defined]

        db.flush = AsyncMock(side_effect=_flush)
        db.add = MagicMock(side_effect=added.append)

        empty = MagicMock()
        empty.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=empty)
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        return await parse_current_lineup_file(db, 10, "test.csv", b"sku,qty\nSKU-A,10\n")

    asyncio.run(run())
    # First added object is the ImportJob
    import_job = added[0]
    assert hasattr(import_job, "source_id"), "First added object should be the ImportJob"
    assert import_job.source_id == 77  # type: ignore[attr-defined]
    assert import_job.source_id != 1  # type: ignore[attr-defined]


def test_parse_upload_fails_clearly_without_current_lineup_source():
    """Parser raises CurrentLineupSourceNotConfiguredError when source cannot be resolved."""
    import asyncio

    from app.services.commercial_planner.current_lineup_seed import CurrentLineupSourceNotConfiguredError
    from app.services.commercial_planner.lineup_case_parser import parse_current_lineup_file

    fake_case = SimpleNamespace(id=11, import_job_id=None, file_name=None)

    async def run():
        db = MagicMock()
        db.get = AsyncMock(return_value=fake_case)
        db.scalar = AsyncMock(return_value=None)  # no SourceDefinition after seed attempt
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        empty = MagicMock()
        empty.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=empty)
        return await parse_current_lineup_file(db, 11, "test.csv", b"sku,qty\nSKU-A,10\n")

    with pytest.raises(CurrentLineupSourceNotConfiguredError, match="current_lineup"):
        asyncio.run(run())


def test_ensure_current_lineup_import_seed_idempotent():
    """ensure_current_lineup_import_seed runs two INSERT statements each call; safe twice."""
    import asyncio

    from app.services.commercial_planner.current_lineup_seed import ensure_current_lineup_import_seed

    async def run():
        db = MagicMock()
        db.execute = AsyncMock()
        db.flush = AsyncMock()
        await ensure_current_lineup_import_seed(db)
        await ensure_current_lineup_import_seed(db)
        return db

    db = asyncio.run(run())
    assert db.execute.call_count == 4


def test_parse_upload_returns_structured_422_when_seed_not_configured(monkeypatch):
    """parse-upload maps CurrentLineupSourceNotConfiguredError to structured 422 JSON."""
    import io

    from app.services.commercial_planner.current_lineup_seed import CurrentLineupSourceNotConfiguredError

    case = _make_case(id=99, commercial_plan_id=1, commercial_status="draft_imported")

    async def fake_db():
        sess = MagicMock()
        sess.get = AsyncMock(return_value=case)
        count = MagicMock()
        count.scalar_one = MagicMock(return_value=0)
        sess.execute = AsyncMock(return_value=count)
        yield sess

    async def boom(*args, **kwargs):
        raise CurrentLineupSourceNotConfiguredError(
            "test message",
            remediation="run alembic upgrade head",
        )

    monkeypatch.setattr(
        "app.api.v1.endpoints.commercial_planner.parse_current_lineup_file",
        boom,
    )

    app.dependency_overrides[get_db] = fake_db
    r = client.post(
        "/api/v1/commercial-planner/lineup-cases/99/parse-upload",
        files={"file": ("lineup.csv", io.BytesIO(b"sku\nSKU-A"), "text/csv")},
    )
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert isinstance(detail, dict)
    assert detail["error"] == "current_lineup_import_not_seeded"
    assert detail["message"] == "test message"
    assert detail["remediation"] == "run alembic upgrade head"


def test_parse_upload_unknown_distributor_diagnostic():
    """Unresolved distributor token appends 'unknown_distributor' to diagnostic_codes."""
    import asyncio

    from app.services.commercial_planner.lineup_case_parser import parse_current_lineup_file
    from app.models.commercial_lineup import CommercialLineupLine

    fake_source = SimpleNamespace(id=5)
    fake_case = SimpleNamespace(id=12, import_job_id=None, file_name=None)
    added: list[object] = []

    async def run():
        db = MagicMock()
        db.get = AsyncMock(return_value=fake_case)
        db.scalar = AsyncMock(return_value=fake_source)

        flush_n = {"n": 0}

        async def _flush():
            flush_n["n"] += 1
            if flush_n["n"] == 1 and added:
                added[0].id = 300  # type: ignore[attr-defined]

        db.flush = AsyncMock(side_effect=_flush)
        db.add = MagicMock(side_effect=added.append)

        empty = MagicMock()
        empty.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=empty)
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        # CSV has a distributor column with a value not in the empty distributor map
        csv = b"sku,distributor,qty\nSKU-A,UNKNOWN-DISTI,10\n"
        return await parse_current_lineup_file(db, 12, "test.csv", csv)

    asyncio.run(run())
    # Find the CommercialLineupLine among added objects
    lineup_lines = [x for x in added if isinstance(x, CommercialLineupLine)]
    assert len(lineup_lines) == 1
    assert "unknown_distributor" in (lineup_lines[0].diagnostic_codes or [])


def test_column_metadata_spec_keys_from_jsonb():
    """GET /plans/{id}/column-metadata returns spec_keys aggregated from JSONB."""
    from types import SimpleNamespace

    plan = SimpleNamespace(id=11)

    cat_row = SimpleNamespace(
        category=2,
        form_factor=2,
        lifecycle_status=2,
        product_line=2,
        series_name=2,
        business_unit=2,
        part_number=2,
        sales_model_name=2,
        model_name=2,
    )

    call_count = {"n": 0}

    async def fake_db():
        sess = MagicMock()
        sess.get = AsyncMock(return_value=plan)

        total_result = MagicMock()
        total_result.scalar_one = MagicMock(return_value=2)
        line_count_result = MagicMock()
        line_count_result.scalar_one = MagicMock(return_value=5)
        cat_result = MagicMock()
        cat_result.one = MagicMock(return_value=cat_row)

        async def _execute(stmt, *args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return line_count_result
            if call_count["n"] == 2:
                return total_result
            if call_count["n"] == 3:
                return cat_result
            spec_scalars = MagicMock()
            spec_scalars.all.return_value = [{"cpu": "i5", "RAM": "8GB"}, {"Processor": "i7", "ram": "16GB"}]
            spec_wrap = MagicMock()
            spec_wrap.scalars.return_value = spec_scalars
            return spec_wrap

        sess.execute = AsyncMock(side_effect=_execute)
        yield sess

    app.dependency_overrides[get_db] = fake_db
    r = client.get("/api/v1/commercial-planner/plans/11/column-metadata")
    assert r.status_code == 200
    body = r.json()
    # One distinct product row per specs_json blob; counts are per flattened key name (case-sensitive).
    assert body["spec_keys"]["cpu"] == 1
    assert body["spec_keys"]["RAM"] == 1
    assert body["spec_keys"]["ram"] == 1
    assert body["spec_keys"]["Processor"] == 1
    assert body.get("plan_line_count") == 5


# ─── Phase 2 sync-to-plan tests ───────────────────────────────────────────────


def _make_lineup_line(
    id=1,
    case_id=1,
    source_row_number=1,
    product_id=10,
    customer_id=7,
    distributor_id=3,
    quantity_units=50.0,
    msrp_local=999.0,
    promo_price_evidence_local=None,
    dap_evidence_local=None,
    diagnostic_codes=None,
    customer_token=None,
    raw_row_payload=None,
    sku_raw=None,
    part_number_raw=None,
    model_raw=None,
    base_unit_raw=None,
    rebate_pct_evidence=None,
    distributor_margin_pct_evidence=None,
    vat_pct_evidence=None,
    row_status="imported",
    mapping_confidence=None,
):
    from types import SimpleNamespace
    return SimpleNamespace(
        id=id,
        case_id=case_id,
        source_row_number=source_row_number,
        product_id=product_id,
        customer_id=customer_id,
        distributor_id=distributor_id,
        quantity_units=quantity_units,
        msrp_local=msrp_local,
        promo_price_evidence_local=promo_price_evidence_local,
        dap_evidence_local=dap_evidence_local,
        diagnostic_codes=diagnostic_codes,
        customer_token=customer_token,
        raw_row_payload=raw_row_payload,
        sku_raw=sku_raw,
        part_number_raw=part_number_raw,
        model_raw=model_raw,
        base_unit_raw=base_unit_raw,
        rebate_pct_evidence=rebate_pct_evidence,
        distributor_margin_pct_evidence=distributor_margin_pct_evidence,
        vat_pct_evidence=vat_pct_evidence,
        row_status=row_status,
        mapping_confidence=mapping_confidence,
    )


def test_sync_to_plan_rejects_non_accepted_case():
    """POST sync-to-plan returns 409 when case is not accepted."""
    case = _make_case(id=30, commercial_status="draft_imported", commercial_plan_id=5)

    async def fake_db():
        sess = MagicMock()
        sess.get = AsyncMock(return_value=case)
        yield sess

    app.dependency_overrides[get_db] = fake_db
    r = client.post(
        "/api/v1/commercial-planner/lineup-cases/30/sync-to-plan",
        json={"commercial_plan_id": 5},
    )
    assert r.status_code == 409
    assert "accepted" in r.json()["detail"]


def test_sync_to_plan_creates_plan_lines_for_eligible():
    """POST sync-to-plan creates CommercialPlanLine for eligible lines."""
    from app.models.commercial_planner import CommercialPlan, CommercialPlanLine

    case = _make_case(id=31, commercial_status="accepted", commercial_plan_id=5)
    fake_plan = SimpleNamespace(id=5)
    lineup_line = _make_lineup_line(id=1, case_id=31, product_id=10, customer_id=7, distributor_id=3, raw_row_payload={})
    added = []

    async def fake_db():
        sess = MagicMock()

        async def _get(model, pk):
            if model.__name__ == "CommercialLineupCase":
                return case
            if model.__name__ == "CommercialPlan":
                return fake_plan
            return None

        sess.get = AsyncMock(side_effect=_get)

        call_n = {"n": 0}

        async def _execute(stmt):
            call_n["n"] += 1
            result = MagicMock()
            if call_n["n"] == 1:
                # CommercialLineupLine query
                result.scalars.return_value.all.return_value = [lineup_line]
            else:
                # existing CommercialPlanLine query — none
                result.all.return_value = []
            return result

        sess.execute = AsyncMock(side_effect=_execute)

        flush_n = {"n": 0}

        async def _flush():
            flush_n["n"] += 1
            if added:
                added[-1].id = 500 + flush_n["n"]

        sess.flush = AsyncMock(side_effect=_flush)
        sess.add = MagicMock(side_effect=added.append)
        sess.commit = AsyncMock()
        sess.rollback = AsyncMock()
        yield sess

    app.dependency_overrides[get_db] = fake_db
    r = client.post(
        "/api/v1/commercial-planner/lineup-cases/31/sync-to-plan",
        json={"commercial_plan_id": 5},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["created"] == 1
    assert body["skipped_duplicates"] == 0
    assert body["skipped_unresolved"] == 0
    assert len(body["created_line_ids"]) == 1
    cap = lineup_line.raw_row_payload.get("_cip_commercial_plan_sync")
    assert isinstance(cap, dict)
    assert cap["commercial_plan_line_id"] == body["created_line_ids"][0]
    assert cap["commercial_plan_id"] == 5


def test_sync_to_plan_skips_duplicates():
    """POST sync-to-plan skips lines already in the plan (same customer+distributor+product)."""
    from app.models.commercial_planner import CommercialPlan

    case = _make_case(id=32, commercial_status="accepted", commercial_plan_id=5)
    fake_plan = SimpleNamespace(id=5)
    lineup_line = _make_lineup_line(id=2, case_id=32, product_id=10, customer_id=7, distributor_id=3)

    # Existing plan line for same key
    existing_row = SimpleNamespace(customer_id=7, distributor_id=3, product_id=10)

    async def fake_db():
        sess = MagicMock()

        async def _get(model, pk):
            if model.__name__ == "CommercialLineupCase":
                return case
            if model.__name__ == "CommercialPlan":
                return fake_plan
            return None

        sess.get = AsyncMock(side_effect=_get)

        call_n = {"n": 0}

        async def _execute(stmt):
            call_n["n"] += 1
            result = MagicMock()
            if call_n["n"] == 1:
                result.scalars.return_value.all.return_value = [lineup_line]
            else:
                result.all.return_value = [existing_row]
            return result

        sess.execute = AsyncMock(side_effect=_execute)
        sess.add = MagicMock()
        sess.flush = AsyncMock()
        sess.commit = AsyncMock()
        sess.rollback = AsyncMock()
        yield sess

    app.dependency_overrides[get_db] = fake_db
    r = client.post(
        "/api/v1/commercial-planner/lineup-cases/32/sync-to-plan",
        json={"commercial_plan_id": 5},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["created"] == 0
    assert body["skipped_duplicates"] == 1


def test_sync_to_plan_skips_unresolved():
    """POST sync-to-plan increments skipped_unresolved when product_id is None."""
    from app.models.commercial_planner import CommercialPlan

    case = _make_case(id=33, commercial_status="accepted", commercial_plan_id=5)
    fake_plan = SimpleNamespace(id=5)
    unresolved_line = _make_lineup_line(id=3, case_id=33, product_id=None, customer_id=7, distributor_id=3)

    async def fake_db():
        sess = MagicMock()

        async def _get(model, pk):
            if model.__name__ == "CommercialLineupCase":
                return case
            if model.__name__ == "CommercialPlan":
                return fake_plan
            return None

        sess.get = AsyncMock(side_effect=_get)

        call_n = {"n": 0}

        async def _execute(stmt):
            call_n["n"] += 1
            result = MagicMock()
            if call_n["n"] == 1:
                result.scalars.return_value.all.return_value = [unresolved_line]
            else:
                result.all.return_value = []
            return result

        sess.execute = AsyncMock(side_effect=_execute)
        sess.add = MagicMock()
        sess.flush = AsyncMock()
        sess.commit = AsyncMock()
        sess.rollback = AsyncMock()
        yield sess

    app.dependency_overrides[get_db] = fake_db
    r = client.post(
        "/api/v1/commercial-planner/lineup-cases/33/sync-to-plan",
        json={"commercial_plan_id": 5},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["created"] == 0
    assert body["skipped_unresolved"] == 1
    assert body["skipped_unresolved_product"] == 1


def test_sync_to_plan_does_not_write_dap_as_cost():
    """POST sync-to-plan creates plan line without writing dap_evidence_local to any cost field."""
    from app.models.commercial_planner import CommercialPlan, CommercialPlanLine

    case = _make_case(id=34, commercial_status="accepted", commercial_plan_id=5)
    fake_plan = SimpleNamespace(id=5)
    # Line has DAP evidence — must NOT appear in any cost field of the created plan line
    lineup_line = _make_lineup_line(
        id=4, case_id=34, product_id=10, customer_id=7, distributor_id=3, dap_evidence_local=850.0
    )
    added = []

    async def fake_db():
        sess = MagicMock()

        async def _get(model, pk):
            if model.__name__ == "CommercialLineupCase":
                return case
            if model.__name__ == "CommercialPlan":
                return fake_plan
            return None

        sess.get = AsyncMock(side_effect=_get)

        call_n = {"n": 0}

        async def _execute(stmt):
            call_n["n"] += 1
            result = MagicMock()
            if call_n["n"] == 1:
                result.scalars.return_value.all.return_value = [lineup_line]
            else:
                result.all.return_value = []
            return result

        sess.execute = AsyncMock(side_effect=_execute)

        flush_n = {"n": 0}

        async def _flush():
            flush_n["n"] += 1
            if added:
                added[-1].id = 600 + flush_n["n"]

        sess.flush = AsyncMock(side_effect=_flush)
        sess.add = MagicMock(side_effect=added.append)
        sess.commit = AsyncMock()
        sess.rollback = AsyncMock()
        yield sess

    app.dependency_overrides[get_db] = fake_db
    r = client.post(
        "/api/v1/commercial-planner/lineup-cases/34/sync-to-plan",
        json={"commercial_plan_id": 5},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["created"] == 1

    # Inspect the created CommercialPlanLine — DAP must not appear in cost fields
    created_plan_line = next(x for x in added if isinstance(x, CommercialPlanLine))
    # DAP evidence value (850.0) must NOT be in target_srp_local or any cost field
    assert created_plan_line.target_srp_local != 850.0
    # override_landed_cost_usd must not be set to DAP
    assert getattr(created_plan_line, "override_landed_cost_usd", None) is None


def test_sync_preview_returns_counts():
    """GET sync-to-plan/preview returns counts without creating rows."""
    from app.models.commercial_planner import CommercialPlan

    case = _make_case(id=35, commercial_status="accepted", commercial_plan_id=5)
    fake_plan = SimpleNamespace(id=5)
    lineup_line = _make_lineup_line(id=5, case_id=35, product_id=10, customer_id=7, distributor_id=3)

    async def fake_db():
        sess = MagicMock()

        async def _get(model, pk):
            if model.__name__ == "CommercialLineupCase":
                return case
            if model.__name__ == "CommercialPlan":
                return fake_plan
            return None

        sess.get = AsyncMock(side_effect=_get)

        call_n = {"n": 0}

        async def _execute(stmt):
            call_n["n"] += 1
            result = MagicMock()
            if call_n["n"] == 1:
                result.scalars.return_value.all.return_value = [lineup_line]
            else:
                result.all.return_value = []
            return result

        sess.execute = AsyncMock(side_effect=_execute)
        sess.add = MagicMock()
        sess.flush = AsyncMock()
        sess.commit = AsyncMock()
        yield sess

    app.dependency_overrides[get_db] = fake_db
    r = client.get(
        "/api/v1/commercial-planner/lineup-cases/35/sync-to-plan/preview?commercial_plan_id=5"
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total_lines"] == 1
    assert body["will_create"] == 1
    assert body["skipped_duplicates"] == 0
    assert body["created"] == 0  # preview only — no rows created
    assert body["created_line_ids"] == []
    # Verify no commit was called (preview must not persist)
    # (The mock's commit is not called because the preview endpoint doesn't commit)


# ─── Entity resolution + lineup lines sync eligibility ─────────────────────────


def test_entity_resolution_candidates_404():
    async def fake_db():
        sess = MagicMock()
        sess.get = AsyncMock(return_value=None)
        yield sess

    app.dependency_overrides[get_db] = fake_db
    r = client.get("/api/v1/commercial-planner/lineup-cases/99999/entity-resolution-candidates")
    assert r.status_code == 404


def test_entity_resolution_candidates_409_cancelled():
    case = _make_case(id=51, commercial_status="cancelled")

    async def fake_db():
        sess = MagicMock()
        sess.get = AsyncMock(return_value=case)
        yield sess

    app.dependency_overrides[get_db] = fake_db
    r = client.get("/api/v1/commercial-planner/lineup-cases/51/entity-resolution-candidates")
    assert r.status_code == 409


def test_entity_resolution_candidates_returns_tokens():
    case = _make_case(id=52, commercial_status="validated", commercial_plan_id=5)
    line1 = _make_lineup_line(
        id=1,
        case_id=52,
        customer_id=None,
        customer_token="Acme Retail",
        distributor_id=None,
        raw_row_payload={"distributor_token": "Summit Supply"},
        product_id=10,
    )
    line2 = _make_lineup_line(
        id=2,
        case_id=52,
        customer_id=None,
        customer_token="Acme Retail",
        distributor_id=3,
        product_id=10,
    )

    async def fake_db():
        sess = MagicMock()
        sess.get = AsyncMock(return_value=case)
        exec_result = MagicMock()
        exec_result.scalars.return_value.all.return_value = [line1, line2]
        sess.execute = AsyncMock(return_value=exec_result)
        yield sess

    app.dependency_overrides[get_db] = fake_db
    r = client.get("/api/v1/commercial-planner/lineup-cases/52/entity-resolution-candidates")
    assert r.status_code == 200
    body = r.json()
    assert body["case_id"] == 52
    cust = body["customer_tokens"]
    assert len(cust) == 1
    assert cust[0]["token_display"] == "Acme Retail"
    assert cust[0]["line_count"] == 2
    dist = body["distributor_tokens"]
    assert len(dist) == 1
    assert dist[0]["token_display"] == "Summit Supply"


def test_entity_resolution_candidates_lists_abbreviation_token_until_explicit_resolution():
    """Ambiguous tokens (e.g. IC) appear as candidates only; nothing is auto-mapped at list time."""
    case = _make_case(id=74, commercial_status="draft_imported", commercial_plan_id=5)
    line = _make_lineup_line(
        id=1,
        case_id=74,
        customer_id=None,
        customer_token="IC",
        distributor_id=3,
        product_id=10,
    )

    async def fake_db():
        sess = MagicMock()
        sess.get = AsyncMock(return_value=case)
        exec_result = MagicMock()
        exec_result.scalars.return_value.all.return_value = [line]
        sess.execute = AsyncMock(return_value=exec_result)
        yield sess

    app.dependency_overrides[get_db] = fake_db
    r = client.get("/api/v1/commercial-planner/lineup-cases/74/entity-resolution-candidates")
    assert r.status_code == 200
    cust = r.json()["customer_tokens"]
    assert len(cust) == 1
    assert cust[0]["token_display"] == "IC"
    assert line.customer_id is None


def test_entity_resolution_apply_409_when_accepted():
    case = _make_case(id=53, commercial_status="accepted", commercial_plan_id=5)

    async def fake_db():
        sess = MagicMock()
        sess.get = AsyncMock(return_value=case)
        yield sess

    app.dependency_overrides[get_db] = fake_db
    r = client.post(
        "/api/v1/commercial-planner/lineup-cases/53/entity-resolutions/apply",
        json={"resolutions": [{"kind": "customer", "token": "x", "dim_id": 1}]},
    )
    assert r.status_code == 409


def test_entity_resolution_apply_400_unknown_dim_customer():
    case = _make_case(id=54, commercial_status="validated", commercial_plan_id=5)

    async def _get(model, pk):
        if model.__name__ == "CommercialLineupCase":
            return case
        return None

    async def fake_db():
        sess = MagicMock()
        sess.get = AsyncMock(side_effect=_get)
        yield sess

    app.dependency_overrides[get_db] = fake_db
    r = client.post(
        "/api/v1/commercial-planner/lineup-cases/54/entity-resolutions/apply",
        json={"resolutions": [{"kind": "customer", "token": "Acme", "dim_id": 999}]},
    )
    assert r.status_code == 400
    assert "Unknown customer_id" in r.json()["detail"]


def test_entity_resolution_apply_updates_customer_preserves_dap():
    case = _make_case(id=55, commercial_status="validated", commercial_plan_id=5)
    line = _make_lineup_line(
        id=10,
        case_id=55,
        customer_id=None,
        customer_token="Acme Retail",
        distributor_id=3,
        product_id=10,
        dap_evidence_local=12.34,
        diagnostic_codes=["unknown_customer"],
    )
    dim_cust = SimpleNamespace(id=7)

    async def _get(model, pk):
        if model.__name__ == "CommercialLineupCase":
            return case
        if model.__name__ == "DimCustomer" and pk == 7:
            return dim_cust
        return None

    async def fake_db():
        sess = MagicMock()
        sess.get = AsyncMock(side_effect=_get)
        exec_result = MagicMock()
        exec_result.scalars.return_value.all.return_value = [line]
        sess.execute = AsyncMock(return_value=exec_result)
        sess.commit = AsyncMock()
        yield sess

    app.dependency_overrides[get_db] = fake_db
    r = client.post(
        "/api/v1/commercial-planner/lineup-cases/55/entity-resolutions/apply",
        json={"resolutions": [{"kind": "customer", "token": "Acme Retail", "dim_id": 7}]},
    )
    assert r.status_code == 200
    out = r.json()
    assert out["updated_lines"] == 1
    assert line.customer_id == 7
    assert line.dap_evidence_local == 12.34
    assert "unknown_customer" not in (line.diagnostic_codes or [])
    assert any(x.startswith("manual_case_resolution_") for x in (line.diagnostic_codes or []))


def test_entity_resolution_mark_open_channel_staging_preserves_dap():
    case = _make_case(id=71, commercial_status="validated", commercial_plan_id=5)
    line = _make_lineup_line(
        id=11,
        case_id=71,
        customer_id=None,
        customer_token="Retail Route A",
        distributor_id=3,
        product_id=10,
        dap_evidence_local=44.4,
        diagnostic_codes=["unknown_customer"],
        raw_row_payload={},
    )

    async def _get(model, pk):
        if model.__name__ == "CommercialLineupCase":
            return case
        return None

    async def fake_db():
        sess = MagicMock()
        sess.get = AsyncMock(side_effect=_get)
        exec_result = MagicMock()
        exec_result.scalars.return_value.all.return_value = [line]
        sess.execute = AsyncMock(return_value=exec_result)
        sess.commit = AsyncMock()
        yield sess

    app.dependency_overrides[get_db] = fake_db
    r = client.post(
        "/api/v1/commercial-planner/lineup-cases/71/entity-resolutions/apply",
        json={
            "resolutions": [
                {"kind": "customer", "token": "Retail Route A", "action": "mark_open_channel_staging"},
            ],
        },
    )
    assert r.status_code == 200
    assert line.dap_evidence_local == 44.4
    assert isinstance(line.raw_row_payload, dict)
    assert line.raw_row_payload.get("staging_open_channel") is True
    assert line.customer_token is None


def test_entity_resolution_customer_token_as_distributor_preserves_dap():
    case = _make_case(id=72, commercial_status="draft_imported", commercial_plan_id=5)
    line = _make_lineup_line(
        id=12,
        case_id=72,
        customer_id=None,
        customer_token="MITSUMI",
        distributor_id=None,
        product_id=10,
        dap_evidence_local=55.5,
        diagnostic_codes=["unknown_customer"],
        raw_row_payload={},
    )
    dim_dist = SimpleNamespace(id=9)

    async def _get(model, pk):
        if model.__name__ == "CommercialLineupCase":
            return case
        if model.__name__ == "DimDistributor" and pk == 9:
            return dim_dist
        return None

    async def fake_db():
        sess = MagicMock()
        sess.get = AsyncMock(side_effect=_get)
        exec_result = MagicMock()
        exec_result.scalars.return_value.all.return_value = [line]
        sess.execute = AsyncMock(return_value=exec_result)
        sess.commit = AsyncMock()
        yield sess

    app.dependency_overrides[get_db] = fake_db
    r = client.post(
        "/api/v1/commercial-planner/lineup-cases/72/entity-resolutions/apply",
        json={
            "resolutions": [
                {
                    "kind": "customer_token_as_distributor",
                    "token": "MITSUMI",
                    "action": "map_existing",
                    "dim_id": 9,
                },
            ],
        },
    )
    assert r.status_code == 200
    assert line.distributor_id == 9
    assert line.dap_evidence_local == 55.5
    assert line.customer_token is None


def test_list_lineup_lines_sync_eligibility_requires_plan():
    case = _make_case(id=56, commercial_plan_id=None, commercial_status="draft_imported")

    async def fake_db():
        sess = MagicMock()
        sess.get = AsyncMock(return_value=case)
        exec_res = MagicMock()
        exec_res.all.return_value = []
        sess.execute = AsyncMock(return_value=exec_res)
        yield sess

    app.dependency_overrides[get_db] = fake_db
    r = client.get(
        "/api/v1/commercial-planner/lineup-cases/56/lines?include_sync_eligibility=true",
    )
    assert r.status_code == 400
    assert "commercial_plan_id" in r.json()["detail"].lower()


def test_list_lineup_lines_includes_sync_eligibility_when_plan_linked():
    case = _make_case(id=57, commercial_plan_id=5, commercial_status="validated")
    ln = _make_lineup_line(
        id=20,
        case_id=57,
        product_id=10,
        customer_id=7,
        distributor_id=3,
        quantity_units=1.0,
        msrp_local=100.0,
    )
    row_tuple = (
        ln,
        "SKU1",
        "Name",
        "PN1",
        "M1",
        "SM1",
        {},
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        "C1",
        "Cust",
        "D1",
        "Dist",
    )

    exec_n = {"n": 0}

    async def _execute(stmt):
        exec_n["n"] += 1
        res = MagicMock()
        if exec_n["n"] == 1:
            res.all.return_value = [row_tuple]
        else:
            res.all.return_value = []
        return res

    async def fake_db():
        sess = MagicMock()
        sess.get = AsyncMock(return_value=case)
        sess.execute = AsyncMock(side_effect=_execute)
        yield sess

    app.dependency_overrides[get_db] = fake_db
    r = client.get(
        "/api/v1/commercial-planner/lineup-cases/57/lines?include_sync_eligibility=true",
    )
    assert r.status_code == 200
    lines = r.json()["lines"]
    assert len(lines) == 1
    assert lines[0]["sync_eligible"] is True
    assert lines[0]["sync_skip_reason"] is None


def test_list_lineup_lines_include_line_uploaded():
    case = _make_case(id=58, commercial_plan_id=None, commercial_status="draft_imported")
    ln = _make_lineup_line(
        id=1,
        case_id=58,
        product_id=None,
        customer_id=None,
        distributor_id=None,
        raw_row_payload={"uploaded": {"Dealer buy": "99"}},
    )
    row_tuple = (ln, None, None, None, None, None, {},) + (None,) * 9 + (None, None, None, None)

    async def _execute(stmt):
        res = MagicMock()
        res.all.return_value = [row_tuple]
        return res

    async def fake_db():
        sess = MagicMock()
        sess.get = AsyncMock(return_value=case)
        sess.execute = AsyncMock(side_effect=_execute)
        yield sess

    app.dependency_overrides[get_db] = fake_db
    r = client.get(
        "/api/v1/commercial-planner/lineup-cases/58/lines?include_line_uploaded=true",
    )
    assert r.status_code == 200
    assert r.json()["lines"][0]["uploaded"]["Dealer buy"] == "99"


def test_workbench_column_metadata_includes_raw_upload_headers():
    case = _make_case(id=60, commercial_plan_id=5, commercial_status="draft_imported")
    ln = _make_lineup_line(
        id=1,
        case_id=60,
        raw_row_payload={"uploaded": {"VAT %": "15"}},
    )
    mr = MagicMock()
    mr.scalars.return_value.all.return_value = [ln]

    async def fake_db():
        sess = MagicMock()
        sess.get = AsyncMock(return_value=case)
        sess.execute = AsyncMock(return_value=mr)
        yield sess

    app.dependency_overrides[get_db] = fake_db
    r = client.get("/api/v1/commercial-planner/lineup-cases/60/workbench-column-metadata")
    assert r.status_code == 200
    body = r.json()
    assert "VAT %" in body["raw_columns"]
    assert any(p["field"] == "dap_evidence_local" for p in body["parsed_fields"])
    assert any(x["id"].startswith("cat:") for x in body["catalogue_product_fields"])


def test_sync_preview_open_channel_missing_controlled_account_bucket():
    from unittest.mock import AsyncMock, patch

    from app.models.commercial_lineup import CommercialLineupCase
    from app.models.commercial_planner import CommercialPlan

    case = _make_case(id=61, commercial_plan_id=5, commercial_status="accepted")
    open_ln = _make_lineup_line(
        id=1,
        case_id=61,
        product_id=10,
        customer_id=None,
        distributor_id=3,
        msrp_local=50.0,
        quantity_units=1.0,
        raw_row_payload={"staging_open_channel": True},
    )

    async def _get(model, pk):
        if model is CommercialLineupCase and pk == 61:
            return case
        if model is CommercialPlan and pk == 5:
            return SimpleNamespace(id=5)
        return None

    async def _exec(stmt):
        res = MagicMock()
        s = str(stmt)
        if "commercial_lineup_line" in s.lower():
            res.scalars.return_value.all.return_value = [open_ln]
        else:
            res.all.return_value = []
        return res

    async def fake_db():
        sess = MagicMock()
        sess.get = AsyncMock(side_effect=_get)
        sess.execute = AsyncMock(side_effect=_exec)
        yield sess

    app.dependency_overrides[get_db] = fake_db
    with patch(
        "app.api.v1.endpoints.commercial_planner.get_open_channel_customer_id",
        new_callable=AsyncMock,
        return_value=None,
    ):
        r = client.get(
            "/api/v1/commercial-planner/lineup-cases/61/sync-to-plan/preview?commercial_plan_id=5",
        )
    assert r.status_code == 200
    assert r.json().get("skipped_open_channel_account_missing") == 1


def test_sync_preview_open_channel_eligible_when_controlled_account_present():
    from unittest.mock import AsyncMock, patch

    from app.models.commercial_lineup import CommercialLineupCase
    from app.models.commercial_planner import CommercialPlan

    case = _make_case(id=62, commercial_plan_id=5, commercial_status="accepted")
    open_ln = _make_lineup_line(
        id=1,
        case_id=62,
        product_id=10,
        customer_id=None,
        distributor_id=3,
        msrp_local=50.0,
        quantity_units=1.0,
        raw_row_payload={"staging_open_channel": True},
    )

    async def _get(model, pk):
        if model is CommercialLineupCase and pk == 62:
            return case
        if model is CommercialPlan and pk == 5:
            return SimpleNamespace(id=5)
        return None

    async def _exec(stmt):
        res = MagicMock()
        s = str(stmt)
        if "commercial_lineup_line" in s.lower():
            res.scalars.return_value.all.return_value = [open_ln]
        else:
            res.all.return_value = []
        return res

    async def fake_db():
        sess = MagicMock()
        sess.get = AsyncMock(side_effect=_get)
        sess.execute = AsyncMock(side_effect=_exec)
        yield sess

    app.dependency_overrides[get_db] = fake_db
    with patch(
        "app.api.v1.endpoints.commercial_planner.get_open_channel_customer_id",
        new_callable=AsyncMock,
        return_value=9001,
    ):
        r = client.get(
            "/api/v1/commercial-planner/lineup-cases/62/sync-to-plan/preview?commercial_plan_id=5",
        )
    assert r.status_code == 200
    body = r.json()
    assert body.get("will_create") == 1
    assert body.get("skipped_open_channel_account_missing") == 0


# ── product_specs_flat on lineup lines ────────────────────────────────────────

def test_list_lineup_lines_product_specs_flat_populated():
    """product_specs_flat must appear on line payloads when include_product_specs=true."""
    case = _make_case(id=70, commercial_plan_id=None, commercial_status="draft_imported")
    ln = _make_lineup_line(id=1, case_id=70, product_id=10, customer_id=7, distributor_id=3)
    specs = {"cpu": "Intel i7", "RAM": "16 GB", "import_staging": {"storage": "512 GB SSD"}}
    row_tuple = (
        ln,
        "SKU-10",
        "Laptop Pro",
        "PN-10",
        "Model X",
        "SM-X",
        specs,   # product_specs_json
        "Notebook",    # catalogue_category
        None, None, None, None, None, None, None, None,
        "CUST-01", "Cust One",
        "DIST-01", "Dist One",
    )

    async def _execute(stmt):
        res = MagicMock()
        res.all.return_value = [row_tuple]
        return res

    async def fake_db():
        sess = MagicMock()
        sess.get = AsyncMock(return_value=case)
        sess.execute = AsyncMock(side_effect=_execute)
        yield sess

    app.dependency_overrides[get_db] = fake_db
    r = client.get(
        "/api/v1/commercial-planner/lineup-cases/70/lines"
        "?include_product_specs=true&workbench_scope=all",
    )
    assert r.status_code == 200
    lines = r.json()["lines"]
    assert len(lines) == 1
    flat = lines[0].get("product_specs_flat")
    assert isinstance(flat, dict), "product_specs_flat must be a dict"
    # Top-level keys present in flat map
    assert flat.get("cpu") == "Intel i7"
    assert flat.get("RAM") == "16 GB"
    # Nested import_staging key promoted to flat map
    assert flat.get("storage") == "512 GB SSD"
    # product_specs_flat must not contain import_staging itself
    assert "import_staging" not in flat


def test_list_lineup_lines_product_specs_flat_empty_when_no_specs():
    """product_specs_flat must be an empty dict when product has no specs_json."""
    case = _make_case(id=71, commercial_plan_id=None, commercial_status="draft_imported")
    ln = _make_lineup_line(id=2, case_id=71, product_id=None, customer_id=None, distributor_id=None)
    row_tuple = (ln, None, None, None, None, None, None,) + (None,) * 9 + (None, None, None, None)

    async def _execute(stmt):
        res = MagicMock()
        res.all.return_value = [row_tuple]
        return res

    async def fake_db():
        sess = MagicMock()
        sess.get = AsyncMock(return_value=case)
        sess.execute = AsyncMock(side_effect=_execute)
        yield sess

    app.dependency_overrides[get_db] = fake_db
    r = client.get(
        "/api/v1/commercial-planner/lineup-cases/71/lines"
        "?include_product_specs=true&workbench_scope=all",
    )
    assert r.status_code == 200
    lines = r.json()["lines"]
    flat = lines[0].get("product_specs_flat")
    assert isinstance(flat, dict)
    assert flat == {}


# ── Safe plan deletion ─────────────────────────────────────────────────────────

def test_delete_plan_blocks_non_draft():
    """DELETE /plans/{id} must return 409 for non-draft plans."""
    plan = SimpleNamespace(id=99, plan_name="Approved Plan", status="approved", line_count=0)

    async def fake_db():
        sess = MagicMock()
        sess.get = AsyncMock(return_value=plan)
        yield sess

    app.dependency_overrides[get_db] = fake_db
    r = client.delete("/api/v1/commercial-planner/plans/99")
    assert r.status_code == 409
    assert "approved" in r.json()["detail"].lower()


def test_delete_plan_blocks_without_force_when_has_lines():
    """DELETE /plans/{id} must return 409 if plan has lines and force is not set."""
    plan = SimpleNamespace(id=100, plan_name="Draft With Lines", status="draft", line_count=3)
    fake_line = SimpleNamespace(id=1, commercial_plan_id=100)

    exec_call = {"n": 0}

    async def _execute(stmt):
        exec_call["n"] += 1
        res = MagicMock()
        # First execute: CommercialPlanLine select
        res.scalars.return_value.all.return_value = [fake_line]
        return res

    async def fake_db():
        sess = MagicMock()
        sess.get = AsyncMock(return_value=plan)
        sess.execute = AsyncMock(side_effect=_execute)
        yield sess

    app.dependency_overrides[get_db] = fake_db
    r = client.delete("/api/v1/commercial-planner/plans/100")
    assert r.status_code == 409
    assert "force=true" in r.json()["detail"].lower()


def test_delete_plan_draft_empty_succeeds():
    """DELETE /plans/{id} must succeed (204) for an empty draft plan."""
    plan = SimpleNamespace(id=101, plan_name="Empty Draft", status="draft", line_count=0)

    exec_call = {"n": 0}

    async def _execute(stmt):
        exec_call["n"] += 1
        res = MagicMock()
        # No plan lines, no linked lineup lines
        res.scalars.return_value.all.return_value = []
        return res

    async def fake_db():
        sess = MagicMock()
        sess.get = AsyncMock(return_value=plan)
        sess.execute = AsyncMock(side_effect=_execute)
        sess.delete = AsyncMock()
        sess.flush = AsyncMock()
        sess.commit = AsyncMock()
        yield sess

    app.dependency_overrides[get_db] = fake_db
    r = client.delete("/api/v1/commercial-planner/plans/101")
    assert r.status_code == 204


def test_delete_plan_not_found():
    """DELETE /plans/{id} must return 404 for unknown plan id."""
    async def fake_db():
        sess = MagicMock()
        sess.get = AsyncMock(return_value=None)
        yield sess

    app.dependency_overrides[get_db] = fake_db
    r = client.delete("/api/v1/commercial-planner/plans/9999")
    assert r.status_code == 404
