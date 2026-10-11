"""Unknown price SKUs must not create a product."""

import inspect

from app.api.v1.endpoints import pricing as pricing_endpoint
from app.services.pricing_unknown_sku import UNKNOWN_PRICING_SKU_MESSAGE


def test_price_entry_does_not_create_a_product():
    source = inspect.getsource(pricing_endpoint)
    assert "get_or_create_product" not in source
    assert "queue_unknown_pricing_sku" in source
    assert "No product was created" in UNKNOWN_PRICING_SKU_MESSAGE
