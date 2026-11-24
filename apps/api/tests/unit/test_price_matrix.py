"""Price matrix read model shape."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.listing_capture.price_matrix import build_price_matrix


def test_price_matrix_empty_customers() -> None:
    session = MagicMock()
    session.scalars.return_value.all.return_value = []
    out = build_price_matrix(session, tenant_id="t-a", customer_ids=[])
    assert out["products"] == []
    assert out["summary"]["product_count"] == 0


def test_price_matrix_with_listings_reaches_product_set_comprehension() -> None:
    """Regression: listed_products must not reference pid before the listing loop assigns it."""
    listing = MagicMock()
    listing.product_id = 101
    listing.customer_id = 1
    listing.id = 10
    listing.status = "active"
    listing.url = "https://example.com/p"

    session = MagicMock()
    session.scalars.return_value.all.return_value = [listing]

    patches = (
        patch("app.services.listing_capture.price_matrix.product_tiers", return_value=None),
        patch("app.services.listing_capture.price_matrix._latest_observations", return_value={}),
        patch("app.services.listing_capture.price_matrix._tenant_srp_by_product", return_value={}),
        patch("app.services.listing_capture.price_matrix._active_promos", return_value={}),
        patch(
            "app.services.listing_capture.price_matrix._customer_labels",
            return_value=[{"id": 1, "name": "C1", "code": "C1"}],
        ),
        patch(
            "app.services.listing_capture.price_matrix._product_labels",
            return_value=[{"id": 101, "sku": "S1", "name": "P1"}],
        ),
    )
    for p in patches:
        p.start()
    try:
        out = build_price_matrix(session, tenant_id="t-a", customer_ids=[1])
    finally:
        for p in reversed(patches):
            p.stop()

    assert out["summary"]["product_count"] == 1
    assert len(out["cells"]) == 1