"""Unit tests for DSI customer region evidence (hints only — no channel→region FK)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.reference.iso3166_countries import resolve_alpha2_from_token
from app.services.imports.dsi_customer_region_evidence import (
    build_customer_region_evidence,
    build_region_evidence_batch_context,
)
from app.services.imports.dsi_region_catalog import suggest_region_id_for_iso_code


def test_resolve_alpha2_from_token_country_names() -> None:
    assert resolve_alpha2_from_token("ZA") == "ZA"
    assert resolve_alpha2_from_token("south africa") == "ZA"
    assert resolve_alpha2_from_token("BB_Open Channel") is None


def test_suggest_region_id_for_iso_code_matches_dim_code() -> None:
    region_code_lower = {"za": 42, "us": 7}
    assert suggest_region_id_for_iso_code(region_code_lower, "ZA") == 42
    assert suggest_region_id_for_iso_code(region_code_lower, "XX") is None


@patch("app.services.imports.dsi_customer_region_evidence.resolve_source_geo_from_ctx_cached")
@patch("app.services.imports.dsi_customer_region_evidence.derive_effective_provisional_customer_geo_sync")
@patch("app.services.imports.dsi_customer_region_evidence.build_region_evidence_batch_context")
def test_build_customer_region_evidence_uses_channel_hint_not_mapping(
    mock_batch_ctx: MagicMock,
    mock_geo: MagicMock,
    mock_raw_geo: MagicMock,
) -> None:
    session = MagicMock()
    job = MagicMock()
    cand = MagicMock()
    cand.entity_type = "customer_dealer_token"
    cand.id = 99
    cand.dealer_group_token = None
    cand.context = {"source_channel_raw_samples": ["ZA"], "dominant_distributor_id": None}

    batch = MagicMock()
    batch.region_code_lower = {"za": 42}
    batch.distributor_primary_country = {}
    batch.peer_region_by_dealer_group = {}
    batch.peer_region_job_plurality = None
    batch.geo_cache = MagicMock()
    mock_batch_ctx.return_value = batch

    mock_geo.return_value = {"used_global_fallback_region": False}
    mock_raw_geo.return_value = {
        "source_region_resolved_id": None,
        "source_region_raw_token": None,
        "source_region_resolution_detail": "missing",
    }

    out = build_customer_region_evidence(session, cand, job, batch=batch)

    assert out["suggested_region_id"] == 42
    assert out["confidence"] >= 0.78
    assert any(f.get("source") == "channel_geographic_hint" for f in out["explanation_factors"])
    assert out["channel_geographic_hints"][0]["guessed_region_code"] == "ZA"


def test_build_customer_region_evidence_wrong_entity_type() -> None:
    session = MagicMock()
    job = MagicMock()
    cand = MagicMock()
    cand.entity_type = "distributor_token"
    cand.context = {}

    out = build_customer_region_evidence(session, cand, job)

    assert out["suggested_region_id"] is None
    assert "customer candidates only" in out["explanation_summary"].lower()
