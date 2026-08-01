"""Governed semantic layer (P3-1) — registry + grain validity. No SQL (P3-2)."""

from app.semantics.registry import (
    SemanticCatalog,
    ValidationResult,
    default_catalog,
    load_catalog,
    validate_metric_grain,
)

__all__ = [
    "SemanticCatalog",
    "ValidationResult",
    "default_catalog",
    "load_catalog",
    "validate_metric_grain",
]
