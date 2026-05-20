"""Unit tests for DSI import-candidate steward helpers (no DB)."""

from __future__ import annotations

from types import SimpleNamespace

from app.api.v1.endpoints import mappings as mappings_ep


def test_source_customer_alias_raw_prefers_context_samples() -> None:
    cand = SimpleNamespace(
        context={"source_customer_name_raw_samples": ["Alpha Retail"]},
        sample_raw_values=["customer=Alpha | dealer_group=Group A"],
        normalized_key="group a",
    )
    assert mappings_ep._source_customer_alias_raw_for_dsi_candidate(cand) == "Alpha Retail"


def test_source_customer_alias_raw_falls_back_to_first_sample() -> None:
    cand = SimpleNamespace(context={}, sample_raw_values=["  only composite  "], normalized_key="z")
    assert mappings_ep._source_customer_alias_raw_for_dsi_candidate(cand) == "only composite"


def test_source_customer_alias_raw_empty_context_uses_normalized_when_no_samples() -> None:
    cand = SimpleNamespace(context={"source_customer_name_raw_samples": []}, sample_raw_values=[], normalized_key="nk")
    assert mappings_ep._source_customer_alias_raw_for_dsi_candidate(cand) == "nk"
