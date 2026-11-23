"""Generic listing reader: schema.org structured data via extruct + price-parser first."""

from __future__ import annotations

import json

from app.services.listing_capture.observation import PARSED_PRICE_CURRENCY, parse_snapshot_text


def _page(offer: dict) -> str:
    data = {"@context": "https://schema.org", "@type": "Product", "name": "P", "offers": offer}
    return f'<html><script type="application/ld+json">{json.dumps(data)}</script><p>x</p></html>'


def test_structured_offer_gives_price_and_schema_availability() -> None:
    html = _page({"@type": "Offer", "price": "1 299.00", "priceCurrency": PARSED_PRICE_CURRENCY,
                  "availability": "https://schema.org/OutOfStock"})
    parsed = parse_snapshot_text(html, marketplace="m")
    assert parsed.parse_status == "ok"
    assert parsed.price == 1299.0
    assert parsed.availability == "out_of_stock"
    assert parsed.flags["method"] == "structured_data"


def test_other_currency_falls_back_to_the_existing_readers() -> None:
    html = _page({"@type": "Offer", "price": "99.00", "priceCurrency": "XTS"})
    parsed = parse_snapshot_text(html, marketplace="m")
    assert parsed.flags.get("method") != "structured_data"
