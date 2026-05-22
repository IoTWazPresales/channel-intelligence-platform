"""DSI geo resolution cache (no database)."""

from __future__ import annotations

from app.services.imports.dsi_geo_resolution_cache import (
    DSIGeoResolutionCache,
    resolve_source_geo_from_ctx_cached,
)


class _FakeCache(DSIGeoResolutionCache):
    def __init__(self) -> None:
        self._session = None  # type: ignore[assignment]
        self._channels_by_code = {"retail": 10}
        self._channels_by_name_norm = {}
        self._regions_by_code = {"anz": 20}
        self._regions_by_name_norm = {}
        self._channel_alias_rows = {}
        self._region_alias_rows = {}


def test_resolve_channel_catalog_match() -> None:
    cache = _FakeCache()
    geo = resolve_source_geo_from_ctx_cached(
        cache,
        {
            "source_channel_evidence_norms": ["retail"],
            "source_channel_raw_samples": ["Retail"],
        },
    )
    assert geo["source_channel_resolved_id"] == 10
    assert geo["source_channel_resolution_detail"] == "catalog_match"


def test_unresolved_geo_token_when_no_catalog_match() -> None:
    cache = _FakeCache()
    geo = resolve_source_geo_from_ctx_cached(
        cache,
        {
            "source_region_evidence_norms": ["unknown_region"],
            "source_region_raw_samples": ["Unknown Region"],
        },
    )
    assert geo["source_region_resolved_id"] is None
    assert geo["source_region_resolution_detail"] == "no_catalog_match"
