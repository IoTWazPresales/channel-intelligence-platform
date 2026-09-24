"""Listing URL auto-finder — report ID → retailer URL (human confirms)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.listing_capture.auto_finder import (
    enrich_proposal_with_suggested_url,
    suggest_listing_url,
    takealot_product_url,
)
from app.services.listing_capture.registry import confirm_suggested_proposals


@pytest.mark.parametrize(
    "marketplace,external_id,expected",
    [
        ("amazon", "B0B21JLCZC", "https://www.amazon.co.za/dp/B0B21JLCZC"),
        ("Amazon", "b0b21jlcZC", "https://www.amazon.co.za/dp/B0B21JLCZC"),
        # Takealot report "Product ID" is a SKU: never a URL from bare digits (N-0039).
        ("takealot", "12345678", None),
        ("takealot", "222 547 542", None),
        ("takealot", "PLID987654", "https://www.takealot.com/x/PLID987654"),
        ("takealot", "plid 98174082", "https://www.takealot.com/x/PLID98174082"),
        (
            "evetech",
            "123456",
            "https://www.evetech.co.za/asus-laptops/laptops-for-sale/123456",
        ),
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


@pytest.mark.parametrize("sku", ["222547542", "225185639", "12345", "203 053 235"])
def test_takealot_sku_never_yields_plid_sku_url(sku: str) -> None:
    url = suggest_listing_url("takealot", sku)
    assert url is None
    digits = sku.replace(" ", "")
    assert f"/PLID{digits}" not in str(url)


def test_takealot_known_plid_yields_product_page_shape() -> None:
    assert takealot_product_url("98174082") == "https://www.takealot.com/x/PLID98174082"
    canon = "https://www.takealot.com/asus-zenscreen-mb169ck/PLID98174082"
    assert takealot_product_url("98174082", canonical_url=canon) == canon
    # Canonical for a different PLID, or the bare /PLID<n> shape, is not trusted.
    assert (
        takealot_product_url("98174082", canonical_url="https://www.takealot.com/other/PLID1")
        == "https://www.takealot.com/x/PLID98174082"
    )
    assert (
        takealot_product_url("98174082", canonical_url="https://www.takealot.com/PLID98174082")
        == "https://www.takealot.com/x/PLID98174082"
    )


def test_confirm_suggested_proposals_skips_takealot_sku_seeds(monkeypatch) -> None:
    sku_seed = MagicMock(id=3, marketplace="takealot", external_id="222547542", status="proposed")
    plid_seed = MagicMock(id=4, marketplace="takealot", external_id="PLID98174082", status="proposed")
    session = MagicMock()
    session.scalars.return_value.all.return_value = [sku_seed, plid_seed]
    confirmed: list[tuple[int, str]] = []

    def fake_confirm(_session, *, seed_id, url, registered_by=None):
        confirmed.append((seed_id, url))
        return MagicMock()

    monkeypatch.setattr("app.services.listing_capture.registry.confirm_proposal", fake_confirm)
    out = confirm_suggested_proposals(session, registered_by="t")
    assert confirmed == [(4, "https://www.takealot.com/x/PLID98174082")]
    assert [s["id"] for s in out["skipped"]] == [3]


def test_confirm_suggested_proposals_guards_takealot_without_plid(monkeypatch) -> None:
    seed = MagicMock(id=5, marketplace="takealot", external_id="whatever", status="proposed")
    session = MagicMock()
    session.scalars.return_value.all.return_value = [seed]
    monkeypatch.setattr(
        "app.services.listing_capture.auto_finder.suggest_listing_url",
        lambda _m, _e: "https://www.takealot.com/some-page",
    )
    monkeypatch.setattr(
        "app.services.listing_capture.registry.confirm_proposal",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("must not confirm")),
    )
    out = confirm_suggested_proposals(session, registered_by="t")
    assert out["confirmed"] == 0
    assert out["skipped"][0]["reason"] == "takealot_plid_unresolved"
