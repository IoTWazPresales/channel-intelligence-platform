"""Grid field registry (N-0034): catalog ⊆ serialized keys, codes are default-hidden references (no DB)."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.api.v1.endpoints.buy_plans import buy_plan_row_dict
from app.api.v1.endpoints.forecasts import forecast_row_dict
from app.api.v1.endpoints.inventory import inventory_customer_row_dict
from app.api.v1.endpoints.pricing import pricing_fact_row_dict, pricing_recommendation_row_dict
from app.api.v1.endpoints.roadmap import roadmap_row_dict
from app.api.v1.endpoints.sellout import commercial_line_row_dict
from app.api.v1.endpoints.shipping import _fact_to_dict
from app.main import app
from app.models.derived import PricingRecommendation
from app.models.dimensions import DimCustomer, DimProduct
from app.models.fact_demand_forecast import FactDemandForecast
from app.models.facts import (
    FactBuyPlan,
    FactInboundShipment,
    FactInventoryCustomer,
    FactPricing,
    FactProductRoadmap,
    FactSalesSellout,
)
from app.services.grid_fields import (
    GRID_FIELDS,
    customer_labels,
    fact_row_dict,
    grid_field_items,
    model_field_keys,
)

NOW = datetime(2026, 9, 24, 8, 0, tzinfo=timezone.utc)
PROD = DimProduct(id=7, sku="SKU-7", sales_model_name="Model 7", name="Product 7")
CUSTOMERS = {3: ("CUST-3", "Customer Three")}
DISTRIBUTORS = {5: ("DIST-5", "Distributor Five")}


def _seeded_rows() -> dict[str, dict]:
    """grid_id -> one serialized row built by the endpoint's own serializer."""
    sellout = FactSalesSellout(
        id=1, source_key="k1", product_id=7, customer_id=3, distributor_id=5, period_start=date(2026, 9, 1),
        transaction_date=date(2026, 9, 2), invoice_no="INV-1", units=4, revenue=40, currency_code="ZAR",
        created_at=NOW, updated_at=NOW,
    )
    labels = SimpleNamespace(
        product_sku="SKU-7", product_sales_model_name="Model 7", product_name="Product 7",
        customer_code="CUST-3", customer_name="Customer Three", distributor_code="DIST-5",
        distributor_name="Distributor Five",
    )
    inv = FactInventoryCustomer(
        id=2, product_id=7, customer_id=3, as_of_date=date(2026, 9, 1), on_hand_units=5, on_order_units=1,
        created_at=NOW, updated_at=NOW,
    )
    price = FactPricing(
        id=3, product_id=7, customer_id=3, effective_date=date(2026, 9, 1), list_price=10, net_price=9,
        currency="ZAR", created_at=NOW, updated_at=NOW,
    )
    rec = PricingRecommendation(
        id=4, product_id=7, suggested_state="hold", recommendation_type="price", status="active",
        explanation_factors={"a": 1}, reviewed_by="someone", created_at=NOW, updated_at=NOW,
    )
    buy = FactBuyPlan(
        id=5, product_id=7, distributor_id=5, recommended_qty=10, recommended_window_start=date(2026, 9, 1),
        recommended_window_end=date(2026, 9, 30), rationale="r", created_at=NOW, updated_at=NOW,
    )
    road = FactProductRoadmap(
        id=6, product_id=7, lifecycle_phase="growth", whitespace_flag=False, overlap_flag=False,
        created_at=NOW, updated_at=NOW,
    )
    fc = FactDemandForecast(
        id=8, distributor_id=5, product_id=7, customer_id=3, period_start=date(2026, 9, 1), forecast_units=3,
        method="velocity", confidence_level="low", is_override=False, created_at=NOW, updated_at=NOW,
    )
    inbound = FactInboundShipment(id=9, source_key="s9", line_state="open", status="shipped", raw_source_row={})
    return {
        "sellout.commercial-lines": commercial_line_row_dict(sellout, labels),
        "inventory.customer": inventory_customer_row_dict(inv, PROD, DimCustomer(id=3, code="CUST-3", name="Customer Three")),
        "pricing.facts": pricing_fact_row_dict(price, PROD, CUSTOMERS),
        "pricing.recommendations": pricing_recommendation_row_dict(rec, PROD),
        "buy-plans": buy_plan_row_dict(buy, PROD, DISTRIBUTORS),
        "roadmap": roadmap_row_dict(road, PROD),
        "forecasts": forecast_row_dict(fc, PROD, CUSTOMERS, DISTRIBUTORS),
        "inbound-shipments": _fact_to_dict(
            inbound, product_name=None, product_sku=None, distributor_name="Distributor Five",
            distributor_code="DIST-5", customer_name="Customer Three", customer_code="CUST-3",
            include_raw_row=True,
        ),
    }


def test_every_registered_grid_has_a_seeded_serializer() -> None:
    assert set(_seeded_rows()) == set(GRID_FIELDS)


@pytest.mark.parametrize("grid_id", sorted(GRID_FIELDS))
def test_catalog_fields_are_subset_of_serialized_keys(grid_id: str) -> None:
    """Parity guard: a field the picker offers must be in the row payload, or it would show blank."""
    row = _seeded_rows()[grid_id]
    offered = {it["field"] for it in grid_field_items(GRID_FIELDS[grid_id])}
    missing = offered - set(row)
    assert not missing, f"{grid_id}: picker offers fields the serializer never emits: {sorted(missing)}"


@pytest.mark.parametrize("grid_id", sorted(GRID_FIELDS))
def test_every_item_is_default_hidden_and_grouped(grid_id: str) -> None:
    items = grid_field_items(GRID_FIELDS[grid_id])
    assert items, grid_id
    assert all(it["default_hidden"] is True for it in items)
    assert {it["group"] for it in items} <= {"fact", "reference"}
    fields = [it["field"] for it in items]
    assert len(fields) == len(set(fields)), f"{grid_id}: duplicate fields"
    assert not set(fields) & GRID_FIELDS[grid_id].default_keys


@pytest.mark.parametrize(
    "grid_id,codes",
    [
        ("sellout.commercial-lines", {"customer_code", "distributor_code"}),
        ("inventory.customer", {"customer_code"}),
        ("pricing.facts", {"customer_code"}),
        ("buy-plans", {"distributor_code"}),
        ("forecasts", {"customer_code", "distributor_code"}),
        ("inbound-shipments", {"customer_code", "distributor_code"}),
    ],
)
def test_codes_are_reference_fields(grid_id: str, codes: set[str]) -> None:
    items = {it["field"]: it for it in grid_field_items(GRID_FIELDS[grid_id])}
    for code in codes:
        assert items[code]["group"] == "reference"
        assert items[code]["default_hidden"] is True
    labels = {items[c]["label"] for c in codes}
    assert labels <= {"Customer code", "Distributor code"}
    row = _seeded_rows()[grid_id]
    assert row["customer_code" if "customer_code" in codes else "distributor_code"] in {"CUST-3", "DIST-5"}


@pytest.mark.parametrize("grid_id", sorted(set(GRID_FIELDS) - {"inbound-shipments"}))
def test_internal_columns_never_offered_or_merged(grid_id: str) -> None:
    spec = GRID_FIELDS[grid_id]
    keys = set(model_field_keys(spec))
    assert "tenant_id" not in keys
    assert "raw_source_row" not in keys
    assert not {k for k in keys if k.endswith("_token")}
    assert not keys & spec.hidden_internal


def test_json_and_pii_like_columns_hidden_on_recommendations() -> None:
    keys = set(model_field_keys(GRID_FIELDS["pricing.recommendations"]))
    assert "explanation_factors" not in keys  # JSONB blob
    assert "reviewed_by" not in keys  # names a person
    merged = fact_row_dict(
        PricingRecommendation(id=1, product_id=1, suggested_state="x", reviewed_by="p", explanation_factors={}),
        "pricing.recommendations",
    )
    assert "reviewed_by" not in merged


def test_fact_row_dict_values_are_json_safe() -> None:
    d = fact_row_dict(
        FactProductRoadmap(id=1, product_id=2, lifecycle_phase="x", retire_target=date(2027, 1, 1), created_at=NOW),
        "roadmap",
    )
    assert d["retire_target"] == "2027-01-01"
    assert d["created_at"] == NOW.isoformat()


def test_existing_keys_win_over_registry_fields() -> None:
    row = roadmap_row_dict(FactProductRoadmap(id=1, product_id=7, lifecycle_phase="x", launch_target=date(2026, 1, 2)), PROD)
    assert row["launch_target"] == "2026-01-02"
    assert row["sku"] == "SKU-7"


def test_inventory_row_carries_customer_name() -> None:
    row = _seeded_rows()["inventory.customer"]
    assert row["customer_name"] == "Customer Three"
    assert row["customer_code"] == "CUST-3"


def test_customer_labels_is_one_batched_query() -> None:
    db = MagicMock()
    result = MagicMock()
    result.all.return_value = [(3, "CUST-3", "Customer Three"), (4, "CUST-4", "Customer Four")]
    db.execute = AsyncMock(return_value=result)
    out = asyncio.run(customer_labels(db, [3, 4, 3, None, 4]))
    assert out == {3: ("CUST-3", "Customer Three"), 4: ("CUST-4", "Customer Four")}
    assert db.execute.await_count == 1
    assert asyncio.run(customer_labels(db, [None])) == {}
    assert db.execute.await_count == 1


@pytest.fixture()
def client():
    app.dependency_overrides[get_db] = lambda: MagicMock()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_grid_fields_route(client: TestClient) -> None:
    res = client.get("/api/v1/grid-fields/roadmap")
    assert res.status_code == 200
    body = res.json()
    assert body["grid_id"] == "roadmap"
    assert {it["field"] for it in body["items"]} >= {"retire_target", "replacement_candidate_id"}


def test_grid_fields_unknown_grid_404(client: TestClient) -> None:
    assert client.get("/api/v1/grid-fields/nope").status_code == 404


def test_inbound_alias_matches_registry_fact_group(client: TestClient) -> None:
    alias = client.get("/api/v1/shipping/inbound-optional-columns").json()["items"]
    generic = client.get("/api/v1/grid-fields/inbound-shipments").json()["items"]
    assert alias == [{"field": it["field"], "label": it["label"]} for it in generic if it["group"] == "fact"]
    fields = {it["field"] for it in alias}
    # Historic list kept: raw row, resolver tokens and the relabelled dealer token are still offered.
    assert {"raw_source_row", "product_resolution_token", "customer_dealer_token"} <= fields
    assert {"line_state", "eta_date", "tenant_id"}.isdisjoint(fields)
    labels = {it["field"]: it["label"] for it in alias}
    assert labels["customer_dealer_token"] == "Customer remarks (source)"
