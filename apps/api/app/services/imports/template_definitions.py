"""Canonical import template specs (shared by Alembic migration and runtime seed)."""

from __future__ import annotations

from typing import Any

# Used by Alembic migration — keep JSON-serializable only.
IMPORT_TEMPLATE_ROWS: list[dict[str, Any]] = [
    {
        "slug": "product_master",
        "display_name": "Product Master / Catalog",
        "description": "SKU-level product specs (foundational master data). Upserts dim_product when applied.",
        "enabled": True,
        "hidden": False,
        "admin_only": False,
        "requires_provider": True,
        "pipeline_handler": "product_master_upsert",
        "destructive_apply_requires_confirm": True,
        "accepted_file_types": [".csv", ".xlsx"],
        "expected_columns": {
            "sku": {"aliases": ["item", "item_code", "product_sku"], "required": True},
            "name": {"aliases": ["product_name", "title", "description"], "required": True},
            "category": {"aliases": ["cat", "product_category"], "required": False},
            "channel_code": {"aliases": ["channel", "ch_code", "primary_channel"], "required": False},
        },
    },
    {
        "slug": "distributor_inventory",
        "display_name": "Distributor inventory",
        "description": "On-hand / snapshot files from a distributor feed; validates SKUs against the product catalog.",
        "enabled": True,
        "hidden": False,
        "admin_only": False,
        "requires_provider": True,
        "pipeline_handler": "inventory_sku_gate",
        "destructive_apply_requires_confirm": False,
        "accepted_file_types": [".csv", ".xlsx"],
        "expected_columns": {
            "sku": {"aliases": ["item", "item_code", "product_sku"], "required": True},
            "quantity": {"aliases": ["qty", "on_hand"], "required": True},
        },
    },
    {
        "slug": "customer_inventory_sales",
        "display_name": "Customer inventory & sales",
        "description": "Customer-side inventory and/or POS-style sales extracts (pipeline scaffold).",
        "enabled": True,
        "hidden": True,
        "admin_only": False,
        "requires_provider": True,
        "pipeline_handler": "stub_noop",
        "destructive_apply_requires_confirm": False,
        "accepted_file_types": [".csv", ".xlsx"],
        "expected_columns": {"sku": {"aliases": ["item"], "required": True}},
    },
    {
        "slug": "inbound_shipments",
        "display_name": "Inbound shipments",
        "description": "Inbound PO / shipment tracking files (pipeline scaffold).",
        "enabled": True,
        "hidden": True,
        "admin_only": False,
        "requires_provider": True,
        "pipeline_handler": "stub_noop",
        "destructive_apply_requires_confirm": False,
        "accepted_file_types": [".csv", ".xlsx"],
        "expected_columns": {"sku": {"aliases": ["item"], "required": True}},
    },
    {
        "slug": "pricing_support",
        "display_name": "Pricing & support (MDF)",
        "description": "List/net pricing and MDF / support rows (pipeline scaffold; admin).",
        "enabled": True,
        "hidden": True,
        "admin_only": True,
        "requires_provider": True,
        "pipeline_handler": "stub_noop",
        "destructive_apply_requires_confirm": False,
        "accepted_file_types": [".csv", ".xlsx"],
        "expected_columns": {"sku": {"aliases": ["item"], "required": True}},
    },
    {
        "slug": "lineup_plan",
        "display_name": "Line-up plan",
        "description": "Assortment / line-up planning rows (preview scaffold; use dedicated bulk flows for full upsert).",
        "enabled": True,
        "hidden": False,
        "admin_only": True,
        "requires_provider": True,
        "pipeline_handler": "stub_noop",
        "destructive_apply_requires_confirm": False,
        "accepted_file_types": [".csv", ".xlsx"],
        "expected_columns": {"sku": {"aliases": ["item"], "required": True}},
    },
    {
        "slug": "promotion_plan",
        "display_name": "Promotion plan",
        "description": "Promo plan rows by SKU (pipeline scaffold).",
        "enabled": True,
        "hidden": True,
        "admin_only": False,
        "requires_provider": True,
        "pipeline_handler": "stub_noop",
        "destructive_apply_requires_confirm": False,
        "accepted_file_types": [".csv", ".xlsx"],
        "expected_columns": {"sku": {"aliases": ["item"], "required": True}},
    },
]

DEFAULT_SOURCES: list[tuple[str, str, str, str]] = [
    ("product_catalog_default", "Default product catalog feed", "product_master", "catalog"),
    ("customer_inv_default", "Default customer inventory feed", "customer_inventory_sales", "pos_extract"),
    ("inbound_default", "Default inbound feed", "inbound_shipments", "carrier_extract"),
    ("pricing_support_default", "Default pricing / MDF feed", "pricing_support", "pricing_extract"),
    ("lineup_plan_default", "Default line-up feed", "lineup_plan", "planning_extract"),
    ("promotion_plan_default", "Default promotion plan feed", "promotion_plan", "promo_extract"),
]


def product_master_sample_csv() -> str:
    return (
        "sku,name,category,channel_code\n"
        "SKU-NEW-99,Example product,Audio,RET\n"
    )
