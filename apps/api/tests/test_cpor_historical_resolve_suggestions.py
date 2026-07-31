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


def test_product_ready_via_shared_channel_suffix_strip():
    """CPOR reuses DSI product_identity_lookup_keys (-CM/-E), not a forked heuristic."""
    rows = {9: _product_row(9, sales_model="GU605MV-OI91610G0W")}
    index = _empty_product_index(
        sales_model_name_to_ids={"gu605mv-oi91610g0w": (9,)},
        products_by_id=rows,
    )
    out = suggest_product_token("GU605MV-OI91610G0W-CM", product_index=index)
    assert out["plan_class"] == "ready_to_map"
    assert out["suggestions"][0]["dim_id"] == 9
    assert out["confidence"] == 1.0
    assert str(out["match_reason"]).startswith("exact_key")
    assert "trailer_stripped" in str(out["match_reason"])


def test_product_ready_via_underscore_deal_trailer():
    rows = {11: _product_row(11, sales_model="E1504FA-O58512B0W")}
    index = _empty_product_index(
        sales_model_name_to_ids={"e1504fa-o58512b0w": (11,)},
        products_by_id=rows,
    )
    out = suggest_product_token("E1504FA-O58512B0W_Deal", product_index=index)
    assert out["plan_class"] == "ready_to_map"
    assert out["suggestions"][0]["dim_id"] == 11
    assert "trailer_stripped" in str(out["match_reason"])


def test_product_ready_via_hyphen_dg_trailer():
    rows = {12: _product_row(12, sales_model="RC72LA-Z12410B0W")}
    index = _empty_product_index(
        sales_model_name_to_ids={"rc72la-z12410b0w": (12,)},
        products_by_id=rows,
    )
    out = suggest_product_token("RC72LA-Z12410B0W-DG", product_index=index)
    assert out["plan_class"] == "ready_to_map"
    assert out["suggestions"][0]["dim_id"] == 12
    assert "trailer_stripped" in str(out["match_reason"])


def test_oem_hyphen_full_hit_not_false_peeled():
    """Full OEM code hit wins before one-level peel to a shorter base."""
    rows = {
        20: _product_row(20, sales_model="FA506NF-58512B0W"),
        21: _product_row(21, sales_model="FA506NF"),
    }
    index = _empty_product_index(
        sales_model_name_to_ids={
            "fa506nf-58512b0w": (20,),
            "fa506nf": (21,),
        },
        products_by_id=rows,
    )
    out = suggest_product_token("FA506NF-58512B0W", product_index=index)
    assert out["plan_class"] == "ready_to_map"
    assert out["suggestions"][0]["dim_id"] == 20
    assert "trailer_stripped" not in str(out["match_reason"])


def test_product_absolute_no_match_stays_no_match():
    index = _empty_product_index(
        sales_model_name_to_ids={"x515": (1,)},
        products_by_id={1: _product_row(1, sales_model="X515")},
    )
    out = suggest_product_token("90XB05WN-BSO010", product_index=index)
    assert out["plan_class"] == "no_match"
    assert out["suggestions"] == []


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


def test_demote_cpor_line_ignore_no_catalogue_unblocks_product():
    from types import SimpleNamespace

    from app.services.cpor.historical_import.resolve import (
        case_apply_blockers,
        demote_cpor_staging_line_for_product_ignore,
    )
    from app.services.imports.dsi_product_running_change import IGNORE_REASON_NO_CATALOGUE

    row = SimpleNamespace(
        resolved_product_id=None,
        resolved_customer_id=1,
        distributor_token=None,
        resolved_distributor_id=None,
        window_start="2026-01-01",
        window_end="2026-01-31",
        flags_json={"flags": []},
        skip_apply=False,
    )
    assert "unresolved_product" in case_apply_blockers(row)  # type: ignore[arg-type]
    demote_cpor_staging_line_for_product_ignore(row, IGNORE_REASON_NO_CATALOGUE)  # type: ignore[arg-type]
    assert row.skip_apply is True
    assert row.flags_json["steward_ignore_reason_code"] == IGNORE_REASON_NO_CATALOGUE
    assert any(
        str(d).startswith("steward_ignored_line:") for d in row.flags_json["diagnostics"]
    )
    assert "unresolved_product" not in case_apply_blockers(row)  # type: ignore[arg-type]
