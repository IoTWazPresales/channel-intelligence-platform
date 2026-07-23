"""CPOR historical resolve — suggestion / plan_class contract (no cip writes)."""

from __future__ import annotations

from app.services.cpor.historical_import.resolve import (
    enrich_unresolved_candidate,
    plan_class_counts,
    suggest_party_token,
    suggest_product_token,
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


def test_party_ambiguous_exact_collision():
    index = {"ACME RETAIL": [10, 20]}
    labels = {10: "Acme A", 20: "Acme B"}
    out = suggest_party_token("Acme Retail", index=index, labels=labels)
    assert out["plan_class"] == "ambiguous_eligible"
    assert out["confidence"] == 1.0
    assert out["match_reason"] == "exact_key_collision"
    assert len(out["suggestions"]) == 2
    assert {s["dim_id"] for s in out["suggestions"]} == {10, 20}
    assert all(s["score"] == 1.0 for s in out["suggestions"])


def test_party_ready_to_map_one_strong_prefix():
    index = {
        "COMPUTER MANIA JOHANNESBURG": [7],
        "OTHER STORE": [8],
    }
    labels = {7: "Computer Mania Johannesburg", 8: "Other Store"}
    out = suggest_party_token("Computer Mania", index=index, labels=labels)
    assert out["plan_class"] == "ready_to_map"
    assert out["confidence"] is not None and out["confidence"] >= 0.90
    assert len(out["suggestions"]) == 1
    assert out["suggestions"][0]["dim_id"] == 7
    assert out["suggestions"][0]["reason"] == "prefix_match"


def test_party_no_match_confidence_none():
    index = {"COMPLETELY DIFFERENT": [1]}
    labels = {1: "Completely Different"}
    out = suggest_party_token("ZZZ-UNKNOWN-TOKEN", index=index, labels=labels)
    assert out["plan_class"] == "no_match"
    assert out["confidence"] is None
    assert out["suggestions"] == []
    assert out["match_reason"] is None


def test_product_ambiguous_sales_model_collision():
    rows = {
        1: _product_row(1, sales_model="X515"),
        2: _product_row(2, sales_model="X515"),
    }
    index = _empty_product_index(
        sales_model_name_to_ids={"x515": (1, 2)},
        products_by_id=rows,
    )
    out = suggest_product_token("X515", product_index=index)
    assert out["plan_class"] == "ambiguous_eligible"
    assert len(out["suggestions"]) == 2
    assert out["confidence"] == 1.0
    assert str(out["match_reason"]).startswith("exact_key_collision")


def test_product_ready_to_map_prefix_fuzzy():
    rows = {3: _product_row(3, sales_model="Vivobook 15 X1504")}
    index = _empty_product_index(
        sales_model_name_to_ids={"vivobook 15 x1504": (3,)},
        products_by_id=rows,
    )
    out = suggest_product_token("Vivobook 15", product_index=index)
    assert out["plan_class"] == "ready_to_map"
    assert out["suggestions"][0]["dim_id"] == 3
    assert out["confidence"] is not None and out["confidence"] >= 0.90


def test_enrich_candidate_shape_and_plan_class_counts():
    index = {"ACME": [1, 2]}
    labels = {1: "A", 2: "B"}
    amb = enrich_unresolved_candidate(
        entity="customer",
        token="Acme",
        row_count=4,
        customer_index=index,
        customer_labels=labels,
    )
    assert amb["entity"] == "customer"
    assert amb["token"] == "Acme"
    assert amb["row_count"] == 4
    assert amb["status"] == "unresolved"
    assert amb["plan_class"] == "ambiguous_eligible"
    assert isinstance(amb["suggestions"], list) and len(amb["suggestions"]) == 2
    for s in amb["suggestions"]:
        assert set(s.keys()) == {"dim_id", "label", "score", "reason"}

    none = enrich_unresolved_candidate(
        entity="customer",
        token="NoSuch",
        row_count=1,
        customer_index={"OTHER": [9]},
        customer_labels={9: "Other"},
    )
    assert none["plan_class"] == "no_match"
    assert none["confidence"] is None

    counts = plan_class_counts({"customer": [amb, none]})
    assert counts["customer"]["ambiguous_eligible"] == 1
    assert counts["customer"]["no_match"] == 1
    assert counts["customer"]["ready_to_map"] == 0
    assert counts["customer"]["needs_review"] == 0


def test_suggest_helpers_do_not_mutate_index():
    """Guard: suggestion path is read-only over the index maps (no dim create)."""
    index = {"ACME RETAIL": [10, 20]}
    labels = {10: "Acme A", 20: "Acme B"}
    before_keys = set(index.keys())
    before_ids = {k: list(v) for k, v in index.items()}
    suggest_party_token("Acme Retail", index=index, labels=labels)
    suggest_party_token("ZZZ", index=index, labels=labels)
    assert set(index.keys()) == before_keys
    assert {k: list(v) for k, v in index.items()} == before_ids
