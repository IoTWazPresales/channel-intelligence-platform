"""DSI customer name normalisation (no database)."""

from __future__ import annotations

from app.services.imports.dsi_customer_intelligence import annotate_dsi_customer_candidate_duplicates
from app.services.imports.dsi_customer_name_normalization import normalize_customer_name_for_similarity


def test_normalize_strips_pty_ltd_and_whitespace() -> None:
    assert normalize_customer_name_for_similarity("  Acme Trading Pty Ltd.  ") == "acme trading"
    assert normalize_customer_name_for_similarity("Foo Bar t/a Baz Inc") == "foo bar baz"


def test_duplicate_annotation_within_job() -> None:
    agg = {
        ("customer_dealer_token", "acme"): {
            "dealer_group_raw": "Acme Pty Ltd",
            "source_customer_raw_samples": [],
            "customer_evidence_norms": [],
            "row_count": 1,
            "total_units": 0,
            "total_value": 0,
            "samples": [],
        },
        ("customer_dealer_token", "acme2"): {
            "dealer_group_raw": "ACME PTY LTD",
            "source_customer_raw_samples": [],
            "customer_evidence_norms": [],
            "row_count": 1,
            "total_units": 0,
            "total_value": 0,
            "samples": [],
        },
    }
    annotate_dsi_customer_candidate_duplicates(agg)
    hints_a = agg[("customer_dealer_token", "acme")].get("possible_duplicate_of")
    assert isinstance(hints_a, list) and len(hints_a) >= 1
    assert hints_a[0]["normalized_key"] == "acme2"
    assert float(hints_a[0]["similarity_score"]) >= 0.82
