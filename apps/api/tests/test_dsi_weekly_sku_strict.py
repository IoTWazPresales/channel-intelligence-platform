"""BACKLOG-036 — weekly DSI SKU-strict / model-grain warnings."""

from __future__ import annotations

from app.services.imports.dsi_weekly_product_resolution import (
    product_identifier_source_looks_like_model_grain,
    weekly_dsi_product_resolution_warnings,
)


def test_model_grain_column_detection() -> None:
    assert product_identifier_source_looks_like_model_grain("ModelName") is True
    assert product_identifier_source_looks_like_model_grain("model name") is True
    assert product_identifier_source_looks_like_model_grain("SKU") is False
    assert product_identifier_source_looks_like_model_grain("item_code") is False
    assert product_identifier_source_looks_like_model_grain(None) is False


def test_weekly_warnings_only_for_weekly_model_mapping() -> None:
    assert (
        weekly_dsi_product_resolution_warnings(
            weekly_workflow=False,
            product_source_column="ModelName",
            presolve_tag="product_resolved_sales_model_name",
            product_error=None,
            ambiguous_eligible=None,
        )
        == []
    )
    assert (
        weekly_dsi_product_resolution_warnings(
            weekly_workflow=True,
            product_source_column="SKU",
            presolve_tag="product_resolved_sales_model_name",
            product_error=None,
            ambiguous_eligible=None,
        )
        == []
    )


def test_weekly_warnings_on_sales_model_resolve() -> None:
    codes = weekly_dsi_product_resolution_warnings(
        weekly_workflow=True,
        product_source_column="ModelName",
        presolve_tag="product_resolved_sales_model_name",
        product_error=None,
        ambiguous_eligible=None,
    )
    assert "weekly_dsi_model_grain_without_sku" in codes
    assert "weekly_dsi_resolved_at_sales_model_grain" in codes


def test_weekly_warnings_on_ambiguous_sales_model() -> None:
    codes = weekly_dsi_product_resolution_warnings(
        weekly_workflow=True,
        product_source_column="Model Name",
        presolve_tag=None,
        product_error="ambiguous_product_match",
        ambiguous_eligible={"tier": "sales_model_name", "product_ids": [1, 2]},
    )
    assert "weekly_dsi_model_grain_without_sku" in codes
    assert "weekly_dsi_resolved_at_sales_model_grain" in codes
