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


# --- N-0039: URL write-back, dead_link, verification --------------------------------


def _tkl_listing(**over):
    base = dict(
        id=55,
        url="https://www.takealot.com/PLID233951759",
        marketplace="takealot",
        status="active",
        status_observed_at=None,
        external_id="233951759",
        product_id=1,
        customer_id=20,
        meta_json=None,
    )
    base.update(over)
    return SimpleNamespace(**base)


def _session_with_ean(ean):
    session = MagicMock()
    session.execute.return_value.all.return_value = []
    session.get.return_value = SimpleNamespace(ean=ean, upc=None)
    session.scalar.return_value = None  # no other listing holds the resolved URL
    return session


def _no_http(url: str):
    raise AssertionError(f"unexpected GET {url}")


def _search_one(plid: int) -> str:
    return json.dumps({"sections": {"products": {"results": [{"product_views": {"core": {"id": plid}}}]}}})


def test_record_observation_writes_back_canonical_url_and_keeps_original() -> None:
    session = _session_with_ean("4711387767535")
    listing = _tkl_listing(id=52, url="https://www.takealot.com/PLID222547542", external_id="222547542")

    def http_get(url: str):
        if "product-details/PLID222547542" in url:
            return 404, "{}"
        if "qsearch=" in url:
            return 200, _search_one(98174082)
        if "product-details/PLID98174082" in url:
            return 200, json.dumps(_details())
        raise AssertionError(url)

    obs = record_observation(session, listing, http_get=http_get)
    assert obs.parse_status == "ok"
    assert listing.url == "https://www.takealot.com/asus-zenscreen/PLID98174082"
    assert listing.meta_json["original_url"] == "https://www.takealot.com/PLID222547542"
    assert listing.meta_json["takealot_plid"] == "98174082"
    assert listing.meta_json["url_verified_at"]
    assert listing.status == "active"


def test_record_observation_known_plid_rewrites_sku_url_without_canonical() -> None:
    session = _session_with_ean(None)
    listing = _tkl_listing(
        id=53,
        url="https://www.takealot.com/PLID225185639",
        external_id="225185639",
        meta_json={"takealot_plid": "99667176"},
    )
    details = _details()
    details.pop("desktop_href")
    details.pop("seo")

    def http_get(url: str):
        if "product-details/PLID99667176" in url:
            return 200, json.dumps(details)
        raise AssertionError(url)

    record_observation(session, listing, http_get=http_get)
    assert listing.url == "https://www.takealot.com/x/PLID99667176"
    assert listing.meta_json["original_url"] == "https://www.takealot.com/PLID225185639"
    assert listing.meta_json["url_verified_at"]


def test_record_observation_original_url_preserved_across_rewrites() -> None:
    session = _session_with_ean(None)
    listing = _tkl_listing(
        url="https://www.takealot.com/x/PLID98174082",
        meta_json={"takealot_plid": "98174082", "original_url": "https://www.takealot.com/PLID222547542"},
    )
    record_observation(session, listing, http_get=lambda _u: (200, json.dumps(_details())))
    assert listing.url == "https://www.takealot.com/asus-zenscreen/PLID98174082"
    assert listing.meta_json["original_url"] == "https://www.takealot.com/PLID222547542"


def test_record_observation_uncorroborated_ean_hit_does_not_rewrite() -> None:
    session = _session_with_ean("4711387767535")
    listing = _tkl_listing(url="https://www.takealot.com/PLID222547542", external_id="999")

    def http_get(url: str):
        if "product-details/PLID222547542" in url:
            return 404, "{}"
        if "qsearch=" in url:
            return 200, _search_one(98174082)
        return 200, json.dumps(_details(ean="0000000000000"))

    record_observation(session, listing, http_get=http_get)
    assert listing.url == "https://www.takealot.com/PLID222547542"
    assert "url_verified_at" not in listing.meta_json


def test_record_observation_url_conflict_does_not_rewrite_or_verify() -> None:
    # Two report SKUs of one customer resolving to one PLID (cip ids 69/73): the
    # unique (customer_id, url) key means only one can hold the product URL.
    session = _session_with_ean(None)
    session.scalar.return_value = 69
    listing = _tkl_listing(
        id=73,
        url="https://www.takealot.com/PLID234153078",
        external_id="234153078",
        meta_json={"takealot_plid": "98174082"},
    )
    obs = record_observation(session, listing, http_get=lambda _u: (200, json.dumps(_details())))
    assert obs.parse_status == "ok"
    assert listing.url == "https://www.takealot.com/PLID234153078"
    assert listing.meta_json["url_conflict_listing_id"] == 69
    assert "url_verified_at" not in listing.meta_json
    assert "original_url" not in listing.meta_json


def test_record_observation_rest_404_no_ean_marks_dead_link() -> None:
    session = _session_with_ean(None)
    listing = _tkl_listing()

    def http_get(url: str):
        if "product-details/PLID233951759" in url:
            return 404, json.dumps({"status_code": 404, "message": "Not Found"})
        raise AssertionError(url)

    obs = record_observation(session, listing, http_get=http_get)
    assert obs.parse_status != "ok"
    assert obs.parse_flags["details_status"] == 404
    assert obs.parse_flags["fetch_reason"] == "plid_not_found"
    assert listing.status == "dead_link"
    assert listing.url == "https://www.takealot.com/PLID233951759"  # observed, never deleted/rewritten


def test_record_observation_rest_404_ean_search_miss_marks_dead_link() -> None:
    session = _session_with_ean("4711387767535")
    listing = _tkl_listing()

    def http_get(url: str):
        if "product-details" in url:
            return 404, "{}"
        if "qsearch=" in url:
            return 200, json.dumps({"sections": {"products": {"results": []}}})
        raise AssertionError(url)

    record_observation(session, listing, http_get=http_get)
    assert listing.status == "dead_link"


def test_record_observation_rest_404_but_ean_resolves_stays_active() -> None:
    session = _session_with_ean("4711387767535")
    listing = _tkl_listing(url="https://www.takealot.com/PLID222547542", external_id="222547542")

    def http_get(url: str):
        if "product-details/PLID222547542" in url:
            return 404, "{}"
        if "qsearch=" in url:
            return 200, _search_one(98174082)
        return 200, json.dumps(_details())

    record_observation(session, listing, http_get=http_get)
    assert listing.status == "active"


def test_record_observation_no_plid_no_ean_is_not_dead() -> None:
    # No REST call was made, so there is no evidence the link is dead.
    session = _session_with_ean(None)
    listing = _tkl_listing(url="https://www.takealot.com/some-product", external_id="233951759")
    record_observation(session, listing, http_get=_no_http)
    assert listing.status == "active"
    assert not (listing.meta_json or {}).get("url_verified_at")


def test_record_observation_dead_link_backoff_unchanged() -> None:
    from datetime import datetime, timezone

    session = _session_with_ean(None)
    listing = _tkl_listing(status="dead_link", status_observed_at=datetime.now(timezone.utc))
    obs = record_observation(session, listing, http_get=_no_http, consecutive_dead=3)
    assert obs.parse_status == "skipped"
    assert obs.parse_flags["reason"] == "dead_link_backoff"


def test_record_observation_non_takealot_ok_stamps_verified_without_rewrite() -> None:
    session = MagicMock()
    listing = SimpleNamespace(
        id=1,
        url="https://www.amazon.co.za/dp/B0B21JLCZC",
        marketplace="amazon",
        status="active",
        status_observed_at=None,
        meta_json=None,
    )
    record_observation(session, listing, http_get=lambda _u: (200, '{"price": 55.0}'))
    assert listing.url == "https://www.amazon.co.za/dp/B0B21JLCZC"
    assert listing.meta_json["url_verified_at"]
    assert "original_url" not in listing.meta_json


def test_listing_url_verified_at_definition() -> None:
    from datetime import datetime, timezone

    from app.services.listing_capture.registry import listing_to_dict, listing_url_verified_at

    ok_at = datetime(2026, 8, 10, tzinfo=timezone.utc)
    tkl = _tkl_listing(meta_json={"takealot_plid": "98174082"})
    # A Takealot price observation does not verify the stored URL.
    assert listing_url_verified_at(tkl, last_ok_fetch_at=ok_at) is None
    tkl.meta_json = {"url_verified_at": "2026-09-24T00:00:00+00:00", "original_url": "u0"}
    assert listing_url_verified_at(tkl) == "2026-09-24T00:00:00+00:00"
    amz = SimpleNamespace(marketplace="amazon", meta_json=None)
    assert listing_url_verified_at(amz) is None
    assert listing_url_verified_at(amz, last_ok_fetch_at=ok_at) == ok_at.isoformat()

    row = SimpleNamespace(
        id=55,
        customer_id=20,
        product_id=None,
        url="u1",
        marketplace="takealot",
        status="active",
        source="feed_proposal",
        registered_by=None,
        registered_at=None,
        status_observed_at=None,
        external_id="1",
        notes=None,
        meta_json=tkl.meta_json,
    )
    d = listing_to_dict(row)
    assert d["url_verified_at"] == "2026-09-24T00:00:00+00:00"
    assert d["original_url"] == "u0"
