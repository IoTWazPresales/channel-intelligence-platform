"""Product Master: generic system field keys, legacy aliases, API field metadata."""

from __future__ import annotations

from typing import Any

# Exactly one identity target after normalization (maps to dim_product.sku / part_number).
PM_IDENTITY_TARGETS: frozenset[str] = frozenset({"technical_product_id"})
# Legacy keys that also denote identity until normalized (handled in technical_id_column).
PM_IDENTITY_LEGACY_ALIASES: frozenset[str] = frozenset({"part_number", "sku"})

PM_REQUIRED_NON_IDENTITY: frozenset[str] = frozenset({"display_name"})

# Map old UI/API targets → generic (for backward compatibility with saved jobs).
LEGACY_PM_TARGET_TO_GENERIC: dict[str, str] = {
    "part_number": "technical_product_id",
    "sku": "technical_product_id",
    "name": "display_name",
    "marketing_name": "display_name",
    "source_sku": "source_product_code",
    "sales_model_name": "market_sku",
    "model_name": "model_family",
    "series_name": "series",
    "ean": "barcode_ean",
    "upc": "barcode_upc",
}

# After normalization, only these are valid mapping targets.
PM_CANONICAL_GENERIC: frozenset[str] = frozenset(
    {
        "technical_product_id",
        "display_name",
        "market_sku",
        "model_family",
        "source_product_code",
        "barcode_ean",
        "barcode_upc",
        "category",
        "product_line",
        "series",
        "business_unit",
        "form_factor",
        "channel_code",
        "price_band",
        "country_code",
        "lifecycle_status",
        "launch_date",
        "end_of_life_date",
    }
)

# Union of generic + legacy strings accepted on incoming payloads before normalize.
PRODUCT_MASTER_CANONICAL: frozenset[str] = frozenset(PM_CANONICAL_GENERIC | set(LEGACY_PM_TARGET_TO_GENERIC.keys()))

# Semantic groups for automap scoring (penalize cross-group false positives when header/sample signals disagree).
PM_SEMANTIC_GROUP: dict[str, str] = {
    "technical_product_id": "identity",
    "display_name": "identity",
    "market_sku": "commercial",
    "model_family": "technical_platform",
    "source_product_code": "source_level",
    "barcode_ean": "barcode",
    "barcode_upc": "barcode",
    "category": "classification",
    "product_line": "classification",
    "series": "classification",
    "business_unit": "classification",
    "form_factor": "classification",
    "channel_code": "classification",
    "price_band": "classification",
    "country_code": "classification",
    "lifecycle_status": "lifecycle",
    "launch_date": "lifecycle",
    "end_of_life_date": "lifecycle",
}

# Full normalized-header → canonical target (industry-generic terms only). Vendor-specific strings belong in source memory.
PM_GLOBAL_HEADER_SYNONYMS: dict[str, str] = {
    "mpn": "technical_product_id",
    "manufacturer_part_number": "technical_product_id",
    "item_code": "technical_product_id",
    "product_code": "technical_product_id",
    "product_title": "display_name",
    "product_description": "display_name",
    "commercial_sku": "market_sku",
    "sales_model_code": "market_sku",
    "disti_sku": "market_sku",
    "channel_sku": "market_sku",
    "family_code": "model_family",
    "product_family": "model_family",
    "vendor_product_id": "source_product_code",
    "feed_id": "source_product_code",
    "external_product_key": "source_product_code",
    "product_class": "category",
    "merchandising_category": "category",
    "portfolio": "product_line",
    "subcategory": "category",
    "owning_bu": "business_unit",
    "profit_center": "business_unit",
    "country_of_sale": "country_code",
    "market_region": "country_code",
    "introduction_date": "launch_date",
    "retirement_date": "end_of_life_date",
    # Broad EU / global retail catalog terms (not vendor-specific SKUs).
    "artikelnummer": "technical_product_id",
    "code_article": "technical_product_id",
    "libelle_produit": "display_name",
    "product_label": "display_name",
}


def normalize_pm_mapping_target(raw: str | None) -> str | None:
    """Normalize a single mapping target to generic naming (or None)."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    return LEGACY_PM_TARGET_TO_GENERIC.get(s, s)


def normalize_mapping_decisions(decisions: dict[str, Any] | None) -> dict[str, Any]:
    """Return new dict with target strings normalized (dispositions unchanged)."""
    if not decisions:
        return {}
    out: dict[str, Any] = {}
    for h, meta in decisions.items():
        if not isinstance(meta, dict):
            out[h] = meta
            continue
        m = dict(meta)
        if m.get("target"):
            n = normalize_pm_mapping_target(str(m["target"]))
            if n:
                m["target"] = n
            else:
                m.pop("target", None)
        out[h] = m
    return out


def field_definitions_for_api() -> list[dict[str, Any]]:
    """Structured metadata for mapping UI (tooltips, grouping) — generic system semantics."""
    return [
        {
            "key": "technical_product_id",
            "group": "required_core",
            "label": "technical_product_id",
            "importance": "critical",
            "dim_persistence": "canonical",
            "role": "technical",
            "description": "Exact technical / manufacturer identifier. Primary key for matching and deduplication on the master product (stored as internal product code).",
        },
        {
            "key": "display_name",
            "group": "required_core",
            "label": "display_name",
            "importance": "critical",
            "dim_persistence": "canonical",
            "role": "commercial",
            "description": "Primary human-readable product title for listings, admin, and reports.",
        },
        {
            "key": "market_sku",
            "group": "commercial_identity",
            "label": "market_sku",
            "importance": "high",
            "dim_persistence": "canonical",
            "role": "commercial",
            "description": "Commercial or channel SKU used by customers, distributors, and commercial systems (distinct from the technical product id when both exist).",
        },
        {
            "key": "model_family",
            "group": "product_identity",
            "label": "model_family",
            "importance": "high",
            "dim_persistence": "canonical",
            "role": "product",
            "description": "Broader model or family code; may span multiple technical product ids.",
        },
        {
            "key": "source_product_code",
            "group": "catalog_identity",
            "label": "source_product_code",
            "importance": "high",
            "dim_persistence": "catalog_only",
            "role": "source",
            "description": "Source- or catalog-specific external code for this feed row (does not replace the canonical technical id).",
        },
        {
            "key": "barcode_ean",
            "group": "barcode",
            "label": "barcode_ean",
            "importance": "high",
            "dim_persistence": "canonical",
            "role": "barcode",
            "description": "Global EAN/GTIN barcode for retail matching and reconciliation.",
        },
        {
            "key": "barcode_upc",
            "group": "barcode",
            "label": "barcode_upc",
            "importance": "high",
            "dim_persistence": "canonical",
            "role": "barcode",
            "description": "North American UPC barcode for retail and catalog integrations.",
        },
        {
            "key": "category",
            "group": "classification",
            "label": "category",
            "importance": "medium",
            "dim_persistence": "canonical",
            "role": "classification",
            "description": "Broad product category for segmentation and analytics.",
        },
        {
            "key": "product_line",
            "group": "classification",
            "label": "product_line",
            "importance": "medium",
            "dim_persistence": "canonical",
            "role": "classification",
            "description": "Internal product-line or portfolio hierarchy.",
        },
        {
            "key": "series",
            "group": "classification",
            "label": "series",
            "importance": "medium",
            "dim_persistence": "canonical",
            "role": "classification",
            "description": "Series or range grouping within a line.",
        },
        {
            "key": "business_unit",
            "group": "classification",
            "label": "business_unit",
            "importance": "medium",
            "dim_persistence": "canonical",
            "role": "classification",
            "description": "Owning business unit or P&L scope.",
        },
        {
            "key": "form_factor",
            "group": "classification",
            "label": "form_factor",
            "importance": "medium",
            "dim_persistence": "canonical",
            "role": "classification",
            "description": "Physical product type (e.g. notebook, desktop, accessory).",
        },
        {
            "key": "channel_code",
            "group": "optional",
            "label": "channel_code",
            "importance": "medium",
            "dim_persistence": "canonical",
            "role": "classification",
            "description": "Selling-channel code when the file is channel-specific.",
        },
        {
            "key": "price_band",
            "group": "classification",
            "label": "price_band",
            "importance": "low",
            "dim_persistence": "canonical",
            "role": "classification",
            "description": "Broad price tier for analytics and planning.",
        },
        {
            "key": "country_code",
            "group": "optional",
            "label": "country_code",
            "importance": "low",
            "dim_persistence": "canonical",
            "role": "classification",
            "description": "Market or country scope when the file is country-specific (not per-transaction geography).",
        },
        {
            "key": "lifecycle_status",
            "group": "lifecycle",
            "label": "lifecycle_status",
            "importance": "medium",
            "dim_persistence": "canonical",
            "role": "lifecycle",
            "description": "Lifecycle state (e.g. active, standby, published, retired).",
        },
        {
            "key": "launch_date",
            "group": "lifecycle",
            "label": "launch_date",
            "importance": "medium",
            "dim_persistence": "canonical",
            "role": "lifecycle",
            "description": "Go-to-market or launch date for planning analytics.",
        },
        {
            "key": "end_of_life_date",
            "group": "lifecycle",
            "label": "end_of_life_date",
            "importance": "medium",
            "dim_persistence": "canonical",
            "role": "lifecycle",
            "description": "Planned or actual end-of-life (stored as retired date on master).",
        },
    ]
