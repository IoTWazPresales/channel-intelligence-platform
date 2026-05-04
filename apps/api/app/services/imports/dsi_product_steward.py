"""DSI steward: link ``product_identifier`` candidates to Product Master via ``ProductAlias``.

Validation is synchronous and **shared** between the single-row HTTP handler and future bulk/preview
operations so rules cannot diverge.
"""

from __future__ import annotations

from typing import Any

from app.models.dimensions import DimProduct
from app.services.imports.distributor_sales_inventory import _product_eligible_for_dsi_auto


def raw_product_token_for_dsi_candidate(
    *,
    sample_raw_values: list[Any] | None,
    normalized_key: str,
    raw_override: str | None,
) -> str:
    """Best-effort raw distributor token string for ``ProductAlias.alias_value`` (not normalized key alone)."""
    o = (raw_override or "").strip()
    if o:
        return o[:256]
    if isinstance(sample_raw_values, list):
        for s in sample_raw_values:
            if isinstance(s, str) and s.strip():
                return s.strip()[:256]
    nk = (normalized_key or "").strip()
    if nk and nk != "__blank__":
        return nk[:256]
    return ""


def validate_dsi_product_resolve(
    *,
    context: dict[str, Any],
    selected_product_id: int,
    selected_product: DimProduct,
    confirm_ineligible_product: bool,
    audit_note: str | None,
) -> None:
    """Ensure steward selection satisfies ambiguity / inactivity rules.

    Raises ``ValueError`` with a user-facing message on violation.
    """
    amb = context.get("product_ambiguous_eligible") if isinstance(context.get("product_ambiguous_eligible"), dict) else None
    if amb and isinstance(amb.get("product_ids"), list):
        allowed = {int(x) for x in amb["product_ids"] if x is not None}
        if int(selected_product_id) not in allowed:
            raise ValueError(
                "product_id must be one of the eligible products listed for this ambiguous token; "
                "choose explicitly from the candidate context."
            )

    eligible_now = _product_eligible_for_dsi_auto(selected_product, None)
    if eligible_now:
        return

    if not confirm_ineligible_product:
        raise ValueError(
            "Selected product is inactive or ineligible for automatic DSI resolution; "
            "set confirm_ineligible_product=true and provide audit_note, or pick an active eligible product."
        )
    note = (audit_note or "").strip()
    if len(note) < 8:
        raise ValueError(
            "audit_note is required (minimum 8 characters) when confirming an inactive or ineligible product."
        )
