"""Listing URL auto-finder — report ID → retailer URL (human confirms)."""

from __future__ import annotations

import pytest

from app.services.listing_capture.auto_finder import (
    enrich_proposal_with_suggested_url,
    suggest_listing_url,
)


@pytest.mark.parametrize(
    "marketplace,external_id,expected",
    [
        ("amazon", "B0B21JLCZC", "https://www.amazon.co.za/dp/B0B21JLCZC"),
        ("Amazon", "b0b21jlcZC", "https://www.amazon.co.za/dp/B0B21JLCZC"),
        ("takealot", "12345678", "https://www.takealot.com/PLID12345678"),
        ("takealot", "PLID987654", "https://www.takealot.com/PLID987654"),
        ("evetech", "ABC123", None),
        ("amazon", "not-an-asin", None),
        ("takealot", "nope", None),
        ("", "B0B21JLCZC", None),
    ],
)
def test_suggest_listing_url(marketplace: str, external_id: str, expected: str | None) -> None:
    assert suggest_listing_url(marketplace, external_id) == expected


def test_enrich_proposal_attaches_suggested_url() -> None:
    out = enrich_proposal_with_suggested_url(
        {
            "id": 1,
            "marketplace": "amazon",
            "external_id": "B0974XGW9X",
            "status": "proposed",
        }
    )
    assert out["suggested_url"] == "https://www.amazon.co.za/dp/B0974XGW9X"
