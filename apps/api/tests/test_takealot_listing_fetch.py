"""Takealot REST fetch + buybox parse (SKU vs PLID, EAN corroboration)."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.listing_capture.observation import parse_snapshot_text
from app.services.listing_capture.registry import record_observation
from app.services.listing_capture.takealot_fetch import (
    extract_plid,
    fetch_takealot_listing,
    normalize_barcode,
    parse_takealot_product_json,
    product_details_url,
)


def _details(*, price: float = 1799, rrp: float = 2699, sku: int = 222547542, ean: str = "4711387767535") -> dict:
    return {
        "desktop_href": "https://www.takealot.com/asus-zenscreen/PLID98174082",
        "buybox": {
            "plid": 98174082,
            "tsin": 99510999,
            "items": [
                {
                    "is_selected": True,
                    "is_add_to_cart_available": True,
                    "sku": sku,
                    "price": price,
                    "pretty_price": f"R {price:,.0f}",
                    "listing_price": rrp,
                    "stock_availability": {"status": "In stock"},
                }
            ],
        },
        "badges": {"items": [{"type": "saving", "value": "33% off"}]},
        "flixmedia": {"ean": ean},
        "seo": {"canonical": "https://www.takealot.com/asus-zenscreen/PLID98174082"},
    }


def test_normalize_barcode_strips_excel_dot_zero() -> None:
    assert normalize_barcode("4711636154963.0") == "4711636154963"
    assert normalize_barcode("4711387767535") == "4711387767535"


def test_extract_plid_from_canonical_url_not_from_sku() -> None:
    assert extract_plid("https://www.takealot.com/asus-x/PLID98174082") == "98174082"
    assert extract_plid("https://www.takealot.com/PLID222547542", external_id="222547542") == "222547542"
    # Bare SKU must not be treated as a PLID (CST Product ID is a SKU).
    assert extract_plid("https://www.takealot.com/x", external_id="222547542") is None


def test_parse_buybox_uses_sell_price_not_rrp() -> None:
    parsed = parse_takealot_product_json(_details(), preferred_sku="222547542", parser_version="lc-v0.2")
    assert parsed.parse_status == "ok"
    assert parsed.price == 1799.0
    assert parsed.availability == "in_stock"
    assert parsed.promo_badge == "33% off"
    assert parsed.flags["rrp_listing_price"] == 2699
    assert parsed.flags["sku_matched"] is True
    assert parsed.flags["vat_basis"] == "inc_vat"


def test_json_error_body_is_not_a_price() -> None:
    bad = parse_snapshot_text('{"status_code":404,"message":"Not Found"}', marketplace="takealot")
    assert bad.parse_status == "parse_failed"
    assert bad.flags["reason"] == "json_no_price"
    assert bad.price is None
    ok = parse_snapshot_text(json.dumps(_details()), marketplace="takealot", preferred_sku="222547542")
    assert ok.parse_status == "ok" and ok.price == 1799.0
    spa = parse_snapshot_text(
        "<!DOCTYPE html><html><body>Next.js loader R2</body></html>",
        marketplace="takealot",
    )
    assert spa.parse_status == "parse_failed"


def test_fetch_ean_resolve_when_url_plid_404() -> None:
    details = _details()
    calls: list[str] = []

    def http_get(url: str):
        calls.append(url)
        if "product-details/PLID222547542" in url:
            return 404, json.dumps({"status_code": 404, "message": "Not Found"})
        if "qsearch=4711387767535" in url:
            return 200, json.dumps(
                {
                    "sections": {
                        "products": {
                            "results": [
                                {"type": "product_views", "product_views": {"core": {"id": 98174082}}}
                            ]
                        }
                    }
                }
            )
        if "product-details/PLID98174082" in url:
            return 200, json.dumps(details)
        raise AssertionError(url)

    status, body, flags = fetch_takealot_listing(
        url="https://www.takealot.com/PLID222547542",
        http_get=http_get,
        external_id="222547542",
        ean="4711387767535",
    )
    assert status == 200
    assert flags["plid_source"] == "ean_search"
    assert flags["resolved_plid"] == "98174082"
    assert flags["corroboration"] == "barcode"
    parsed = parse_snapshot_text(body, marketplace="takealot", preferred_sku="222547542")
    assert parsed.price == 1799.0
    assert product_details_url("98174082") in "".join(calls)


def test_fetch_rejects_ambiguous_ean_search() -> None:
    def http_get(url: str):
        if "product-details" in url:
            return 404, "{}"
        return 200, json.dumps(
            {
                "sections": {
                    "products": {
                        "results": [
                            {"product_views": {"core": {"id": 1}}},
                            {"product_views": {"core": {"id": 2}}},
                        ]
                    }
                }
            }
        )

    status, _body, flags = fetch_takealot_listing(
        url="https://www.takealot.com/PLID1",
        http_get=http_get,
        ean="1234567890123",
    )
    assert flags["reason"] == "ean_not_unique_or_missing"
    assert flags["ean_result_count"] == 2
    assert status == 200


def test_record_observation_takealot_uses_api_not_listing_html() -> None:
    session = MagicMock()
    session.execute.return_value.all.return_value = []
    session.get.return_value = SimpleNamespace(ean="4711387767535", upc=None)
    listing = SimpleNamespace(
        id=52,
        url="https://www.takealot.com/PLID222547542",
        marketplace="takealot",
        status="active",
        status_observed_at=None,
        external_id="222547542",
        product_id=70681,
        customer_id=20,
        meta_json=None,
    )
    details = json.dumps(_details())

    def http_get(url: str):
        if "PLID222547542" in url and "product-details" in url:
            return 404, "{}"
        if "qsearch=" in url:
            return 200, json.dumps(
                {"sections": {"products": {"results": [{"product_views": {"core": {"id": 98174082}}}]}}}
            )
        if "PLID98174082" in url:
            return 200, details
        return 200, "<html>shell</html>"

    obs = record_observation(session, listing, http_get=http_get)
    assert obs.parse_status == "ok"
    assert float(obs.extracted_price) == 1799.0
    assert obs.parse_flags.get("cpor_activation", {}).get("status") is not None
    assert listing.meta_json["takealot_plid"] == "98174082"
