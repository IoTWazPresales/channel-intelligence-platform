"""Optional, future-safe identifier resolution — not used for default mapping.

Trusted internal catalog / reference lookup can plug in here later.
Public web search is intentionally not the default.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class IdentifierResolutionHint:
    """Optional structured hint when an internal resolver could disambiguate a column."""

    kind: str  # e.g. "catalog_sku", "internal_part"
    note: str
    confidence: float


class IdentifierResolutionBackend(Protocol):
    """Register a trusted resolver (catalog DB, MDM, etc.) — default is no-op."""

    def maybe_resolve(
        self,
        *,
        normalized_header: str,
        sample_values: list[str],
        context: dict[str, Any],
    ) -> IdentifierResolutionHint | None: ...


_default_backend: IdentifierResolutionBackend | None = None


def set_identifier_resolution_backend(backend: IdentifierResolutionBackend | None) -> None:
    global _default_backend
    _default_backend = backend


def maybe_identifier_resolution_hint(
    *,
    normalized_header: str,
    sample_values: list[str],
    context: dict[str, Any],
) -> IdentifierResolutionHint | None:
    """Called by the mapper only for ambiguous identifier-like columns; usually returns None."""
    if _default_backend is None:
        return None
    return _default_backend.maybe_resolve(
        normalized_header=normalized_header,
        sample_values=sample_values,
        context=context,
    )
