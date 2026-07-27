"""CST candidate suggestion enrich (deterministic tiers, no DB)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services.imports.cst_candidate_suggestions import (
    suggest_cst_location_token,
    suggest_cst_product_token,
)
from app.services.imports.cst_mapping_candidates import (
    CST_PRODUCT_ENTITY,
    _apply_suggestions_to_candidate,
    enrich_cst_open_candidates,
)
from app.services.imports.distributor_sales_inventory import (
    ProductResolutionIndex,
    ProductResolutionProductRow,
)


def _product_row(pid: int, *, sales_model: str, sku: str | None = None) -> ProductResolutionProductRow:
    return ProductResolutionProductRow(
        id=pid,
        sku=sku or f"SKU-{pid}",
        part_number=None,
        sales_model_name=sales_model,
        model_name=None,
        marketing_name=None,
        ean=None,
        upc=None,
        is_active=True,
        lifecycle_status="active",
        launch_date=None,
        retired_date=None,
    )


def _empty_product_index(**overrides: object) -> ProductResolutionIndex:
    base = dict(
        sku_to_id={},
        part_number_to_ids={},
        sales_model_name_to_ids={},
        model_name_to_ids={},
        marketing_name_to_ids={},
        ean_to_ids={},
        upc_to_ids={},
        alias_value_to_ids={},
        products_by_id={},
        steward_alias_by_key={},
    )
    base.update(overrides)
    return ProductResolutionIndex(**base)  # type: ignore[arg-type]


def test_suggest_product_item_code_single_match():
    rows = {3: _product_row(3, sales_model="X515", sku="ABC-123")}
    index = _empty_product_index(sku_to_id={"abc-123": 3}, products_by_id=rows)
    out = suggest_cst_product_token("ABC-123", product_index=index)
    assert len(out) == 1
    assert out[0]["dim_id"] == 3
    assert out[0]["score"] == 1.0
    assert out[0]["reason"] == "item_code"


def test_suggest_product_part_number_collision():
    rows = {
        1: _product_row(1, sales_model="A"),
        2: _product_row(2, sales_model="B"),
    }
    index = _empty_product_index(
        part_number_to_ids={"pn-99": (1, 2)},
        products_by_id=rows,
    )
    out = suggest_cst_product_token("PN-99", product_index=index)
    assert len(out) == 2
    assert all(s["score"] == 1.0 for s in out)
    assert all(s["reason"] == "exact_key_collision:part_number" for s in out)


def test_suggest_product_article_alias_after_tiers_miss():
    rows = {9: _product_row(9, sales_model="Alias Model")}
    index = _empty_product_index(products_by_id=rows)
    session = MagicMock()
    with patch(
        "app.services.imports.cst_candidate_suggestions.resolve_customer_article_alias",
        return_value=9,
    ):
        out = suggest_cst_product_token(
            "cust-sku",
            product_index=index,
            session=session,
            customer_id=1,
        )
    assert len(out) == 1
    assert out[0]["dim_id"] == 9
    assert out[0]["reason"] == "customer_article_alias"


def test_suggest_location_code_exact():
    loc = SimpleNamespace(id=4, location_code="Store 01", location_name="Main")
    out = suggest_cst_location_token("store 01", locations=[loc])
    assert len(out) == 1
    assert out[0]["dim_id"] == 4
    assert out[0]["reason"] == "location_code_exact"


def test_suggest_location_name_exact_when_code_misses():
    loc = SimpleNamespace(id=8, location_code="S1", location_name="Downtown")
    out = suggest_cst_location_token("downtown", locations=[loc])
    assert len(out) == 1
    assert out[0]["reason"] == "location_name_exact"


def test_enrich_open_candidate_writes_suggestions_without_changing_status():
    cand = SimpleNamespace(
        entity_type=CST_PRODUCT_ENTITY,
        normalized_key="abc-123",
        status="needs_review",
        sample_raw_values=["ABC-123"],
        suggested_entity_id=None,
        match_reason=None,
        confidence_score=None,
        context=None,
    )
    job = SimpleNamespace(id=1, staged_metadata={"customer_id": 10}, source=None)
    session = MagicMock()
    session.get.return_value = job
    session.scalars.return_value.all.return_value = [cand]

    rows = {3: _product_row(3, sales_model="Widget", sku="ABC-123")}
    index = _empty_product_index(sku_to_id={"abc-123": 3}, products_by_id=rows)

    with patch(
        "app.services.imports.cst_mapping_candidates.load_product_index",
        return_value=index,
    ), patch(
        "app.services.imports.cst_mapping_candidates.resolve_customer_id_for_job",
        return_value=10,
    ):
        enrich_cst_open_candidates(session, job_id=1)

    assert cand.status == "needs_review"
    assert cand.suggested_entity_id == 3
    assert cand.match_reason == "item_code"
    assert cand.context["suggestions"][0]["dim_id"] == 3


def test_apply_suggestions_clears_when_empty():
    cand = SimpleNamespace(
        suggested_entity_id=1,
        match_reason="old",
        confidence_score=1.0,
        context={"suggestions": [{"dim_id": 1}]},
    )
    _apply_suggestions_to_candidate(cand, [])
    assert cand.suggested_entity_id is None
    assert cand.match_reason is None
    assert "suggestions" not in cand.context
