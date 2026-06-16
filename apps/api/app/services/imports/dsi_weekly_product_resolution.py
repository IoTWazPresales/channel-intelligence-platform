"""Weekly DSI product resolution helpers (BACKLOG-036)."""

from __future__ import annotations

from typing import Any

_WEEKLY_MODEL_GRAIN_DIAG = "weekly_dsi_model_grain_without_sku"
_WEEKLY_MODEL_RESOLVED_DIAG = "weekly_dsi_resolved_at_sales_model_grain"


def product_identifier_source_looks_like_model_grain(source_column: str | None) -> bool:
    """True when the mapped source column name is model/sales-model grain, not SKU/item."""
    if not source_column or not str(source_column).strip():
        return False
    n = str(source_column).lower().replace(" ", "").replace("_", "")
    if any(tok in n for tok in ("sku", "itemcode", "item", "partnumber", "partno", "ean", "upc")):
        return False
    return any(tok in n for tok in ("model", "modelname", "salesmodel"))


def weekly_dsi_product_resolution_warnings(
    *,
    weekly_workflow: bool,
    product_source_column: str | None,
    presolve_tag: str | None,
    product_error: str | None,
    ambiguous_eligible: dict[str, Any] | None,
) -> list[str]:
    """Return validate-time warning codes for weekly imports mapped at model grain."""
    if not weekly_workflow:
        return []
    if not product_identifier_source_looks_like_model_grain(product_source_column):
        return []

    warnings: list[str] = [_WEEKLY_MODEL_GRAIN_DIAG]
    tag = (presolve_tag or "").strip().lower()
    if tag.startswith("product_resolved_sales_model_name"):
        warnings.append(_WEEKLY_MODEL_RESOLVED_DIAG)
    if product_error == "ambiguous_product_match" and isinstance(ambiguous_eligible, dict):
        if str(ambiguous_eligible.get("tier") or "").strip() == "sales_model_name":
            warnings.append(_WEEKLY_MODEL_RESOLVED_DIAG)
    return warnings
