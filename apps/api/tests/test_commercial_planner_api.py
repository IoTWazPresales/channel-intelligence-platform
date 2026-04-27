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
    assert ext["product_spec_ram"] == "16GB"
    assert ext["effective_fx_rate_to_usd"] == 2.0
    assert ext["calc_sell_in_price_local"] == 20.0
    assert ext["calc_distributor_net_local"] == 16.0


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
        cat_result = MagicMock()
        cat_result.one = MagicMock(return_value=cat_row)
        spec_result = MagicMock()
        spec_result.all = MagicMock(return_value=[])

        async def _execute(stmt, *args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return total_result
            if call_count["n"] == 2:
                return cat_result
            return spec_result

        sess.execute = AsyncMock(side_effect=_execute)
        yield sess

    app.dependency_overrides[get_db] = fake_db
    r = client.get("/api/v1/commercial-planner/plans/10/column-metadata")
    assert r.status_code == 200
    body = r.json()
    assert body["total_products"] == 10
    assert body["catalogue"]["category"] == 8
    assert body["catalogue"]["lifecycle_status"] == 10
    assert body["catalogue"]["business_unit"] == 10
    assert isinstance(body["spec_keys"], dict)


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
    spec_row_cpu = SimpleNamespace(key="cpu", cnt=2)
    spec_row_ram = SimpleNamespace(key="ram", cnt=2)

    call_count = {"n": 0}

    async def fake_db():
        sess = MagicMock()
        sess.get = AsyncMock(return_value=plan)

        total_result = MagicMock()
        total_result.scalar_one = MagicMock(return_value=2)
        cat_result = MagicMock()
        cat_result.one = MagicMock(return_value=cat_row)
        spec_result = MagicMock()
        spec_result.all = MagicMock(return_value=[spec_row_cpu, spec_row_ram])

        async def _execute(stmt, *args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return total_result
            if call_count["n"] == 2:
                return cat_result
            return spec_result

        sess.execute = AsyncMock(side_effect=_execute)
        yield sess

    app.dependency_overrides[get_db] = fake_db
    r = client.get("/api/v1/commercial-planner/plans/11/column-metadata")
    assert r.status_code == 200
    body = r.json()
    assert body["spec_keys"]["cpu"] == 2
    assert body["spec_keys"]["ram"] == 2
