"""Price matrix read model shape."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.services.listing_capture.price_matrix import build_price_matrix


def test_price_matrix_empty_customers() -> None:
    session = MagicMock()
    session.scalars.return_value.all.return_value = []
    out = build_price_matrix(session, tenant_id="t-a", customer_ids=[])
    assert out["products"] == []
    assert out["summary"]["product_count"] == 0