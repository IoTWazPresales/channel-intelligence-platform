"""Governed semantic layer (P3-1) — registry + grain validity. No SQL (P3-2)."""

from app.semantics.registry import (
    SemanticCatalog,
    ValidationResult,
    catalog_for_tenant,
    catalog_for_tenant_cached,
    clear_catalog_cache,
    default_catalog,
    load_catalog,
    validate_metric_grain,
)

__all__ = [
    "SemanticCatalog",
    "ValidationResult",
    "catalog_for_tenant",
    "catalog_for_tenant_cached",
    "clear_catalog_cache",
    "default_catalog",
    "load_catalog",
    "validate_metric_grain",
]
