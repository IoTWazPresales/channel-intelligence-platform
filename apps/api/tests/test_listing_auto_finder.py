"""Listing URL auto-finder — report ID → retailer URL (human confirms)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.listing_capture.auto_finder import (
    enrich_proposal_with_suggested_url,
    suggest_listing_url,
)
from app.services.listing_capture.registry import confirm_suggested_proposals


@pytest.mark.parametrize(
    "marketplace,external_id,expected",
    [
        ("amazon", "B0B21JLCZC", "https://www.amazon.co.za/dp/B0B21JLCZC"),
        ("Amazon", "b0b21jlcZC", "https://www.amazon.co.za/dp/B0B21JLCZC"),
        ("takealot", "12345678", "https://www.takealot.com/PLID12345678"),
        ("takealot", "PLID987654", "https://www.takealot.com/PLID987654"),
        ("takealot", "222 547 542", "https://www.takealot.com/PLID222547542"),
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


def test_confirm_suggested_proposals_skips_without_url(monkeypatch) -> None:
    seed_ok = MagicMock(id=1, marketplace="amazon", external_id="B0B21JLCZC", status="proposed")
    seed_skip = MagicMock(id=2, marketplace="evetech", external_id="X", status="proposed")
    session = MagicMock()
    session.scalars.return_value.all.return_value = [seed_ok, seed_skip]

    confirmed: list[int] = []

    def fake_confirm(_session, *, seed_id, url, registered_by=None):
        confirmed.append(seed_id)
        return MagicMock()

    monkeypatch.setattr("app.services.listing_capture.registry.confirm_proposal", fake_confirm)
    out = confirm_suggested_proposals(session, registered_by="t", limit=10)
    assert out["confirmed"] == 1
    assert confirmed == [1]
    assert len(out["skipped"]) == 1
    assert out["skipped"][0]["id"] == 2
