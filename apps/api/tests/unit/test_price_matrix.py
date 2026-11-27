"""Price matrix read model shape."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.listing_capture.price_matrix import _product_labels, build_price_matrix


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
        patch("app.services.listing_capture.price_matrix._srp_by_cell", return_value={}),
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


def test_product_labels_keep_specs_that_are_present() -> None:
    """Spec columns come from specs_json values that exist. Empty and blank values do not."""
    product = MagicMock()
    product.id = 7
    product.sales_model_name = "MODEL-1"
    product.sku = "SKU-1"
    product.name = "Name"
    product.specs_json = {"cpu": "i7", "blank": "  ", "import_staging": {"ram": "16 GB", "cpu": "other"}}
    session = MagicMock()
    session.execute.return_value.scalars.return_value.all.return_value = [product]
    rows = _product_labels(session, "t-a", [7])
    assert rows == [
        {
            "id": 7,
            "sales_model_name": "MODEL-1",
            "sku": "SKU-1",
            "name": "Name",
            "specs": {"cpu": "i7", "ram": "16 GB"},
        }
    ]
