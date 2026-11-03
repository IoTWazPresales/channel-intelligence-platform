"""REST buy-box page reader: every URL from site data; barcode recovery; URL write-back; dead links.

Fictional site ``market-b`` (``tests/listing_site_fixtures.py``). No DB, no network.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.listing_capture.adapters import configured_adapter, missing_fields, rest_buybox
from app.services.listing_capture.registry import listing_to_dict, listing_url_verified_at, record_observation
from tests.listing_site_fixtures import REST_API, REST_HOST, html_site, rest_site

SITE = rest_site()
CANON = f"{REST_HOST}/northwind-glide-14/ID98174082"


def _details(*, price: float = 1799, rrp: float = 2699, sku: int = 222547542, ean: str = "4711387767535") -> dict:
    return {
        "desktop_href": CANON,
        "buybox": {
            "plid": 98174082,
            "tsin": 99510999,
            "items": [
                {
                    "is_selected": True,
                    "is_add_to_cart_available": True,
                    "sku": sku,
                    "price": price,
                    "listing_price": rrp,
                    "stock_availability": {"status": "In stock"},
                }
            ],
        },
        "badges": {"items": [{"type": "saving", "value": "33% off"}]},
        "flixmedia": {"ean": ean},
        "seo": {"canonical": CANON},
    }


def _search(*ids: int) -> str:
    return json.dumps({"sections": {"products": {"results": [{"product_views": {"core": {"id": i}}} for i in ids]}}})


def _details_url(page_id: str) -> str:
    return f"{REST_API}/rest/details/ID{page_id}?platform=desktop"


def _get(routes: dict[str, tuple[int, str]]):
    calls: list[str] = []

    def http_get(url: str, headers=None):
        calls.append(url)
        if url not in routes:
            raise AssertionError(f"unexpected GET {url}")
        return routes[url]

    http_get.calls = calls  # type: ignore[attr-defined]
    return http_get


def _listing(**over):
    base = dict(
        id=55,
        url=f"{REST_HOST}/ID233951759",
        marketplace="market-b",
        status="active",
        status_observed_at=None,
        external_id="233951759",
        product_id=1,
        customer_id=20,
        meta_json=None,
    )
    base.update(over)
    return SimpleNamespace(**base)


def _session(ean):
    session = MagicMock()
    session.execute.return_value.all.return_value = []
    session.get.return_value = SimpleNamespace(ean=ean, upc=None)
    session.scalar.return_value = None  # no other listing holds the resolved URL
    return session


def _no_http(url: str, headers=None):
    raise AssertionError(f"unexpected GET {url}")


# ---------------------------------------------------------------- site data drives the reader


def test_reader_needs_its_link_patterns_before_it_is_used() -> None:
    from dataclasses import replace

    assert missing_fields(SITE) == []
    assert configured_adapter(SITE) is rest_buybox
    bare = replace(SITE, details_url_pattern=None, page_id_pattern=None)
    assert missing_fields(bare) == ["details_url_pattern", "page_id_pattern"]
    assert configured_adapter(bare) is None
    assert configured_adapter(replace(SITE, is_active=False)) is None
    assert missing_fields(html_site()) == []


def test_urls_and_page_id_come_from_site_patterns() -> None:
    assert rest_buybox.page_id_from_url(SITE, f"{REST_HOST}/any-slug/ID98174082") == "98174082"
    # The report stock code is never a page id.
    assert rest_buybox.page_id_from_url(SITE, f"{REST_HOST}/x?sku=222547542") is None
    assert rest_buybox.details_url(SITE, "98174082") == _details_url("98174082")
    assert rest_buybox.search_url(SITE, "4711387767535") == f"{REST_API}/rest/search?q=4711387767535"
    assert rest_buybox.request_headers(SITE) == {"Accept": "application/json", "Referer": f"{REST_HOST}/"}
    assert rest_buybox.product_url(SITE, "98174082") == f"{REST_HOST}/x/ID98174082"
    assert rest_buybox.product_url(SITE, "98174082", canonical_url=CANON) == CANON
    # A canonical link on another host or for another page id is not used.
    assert rest_buybox.product_url(SITE, "98174082", canonical_url="https://elsewhere.test/ID98174082") == f"{REST_HOST}/x/ID98174082"
    assert rest_buybox.product_url(SITE, "1234567", canonical_url=CANON) == f"{REST_HOST}/x/ID1234567"


def test_normalize_barcode_strips_excel_dot_zero() -> None:
    assert rest_buybox.normalize_barcode("4711636154963.0") == "4711636154963"
    assert rest_buybox.normalize_barcode("4711387767535") == "4711387767535"


def test_parse_buybox_uses_sell_price_not_rrp() -> None:
    parsed = rest_buybox.parse(json.dumps(_details()), site=SITE, preferred_sku="222547542", parser_version="t")
    assert parsed.parse_status == "ok"
    assert parsed.price == 1799.0
    assert parsed.availability == "in_stock"
    assert parsed.promo_badge == "33% off"
    assert parsed.flags["rrp_listing_price"] == 2699
    assert parsed.flags["sku_matched"] is True
    assert parsed.flags["vat_basis"] == "inc_vat"
    assert parsed.flags["page_id"] == "98174082"
    assert parsed.flags["marketplace"] == "market-b"


def test_error_body_and_html_shell_are_not_a_price() -> None:
    bad = rest_buybox.parse('{"status_code":404,"message":"Not Found"}', site=SITE, parser_version="t")
    assert bad.parse_status == "parse_failed" and bad.price is None
    shell = rest_buybox.parse("<!DOCTYPE html><html><body>loader R2</body></html>", site=SITE, parser_version="t")
    assert shell.parse_status == "parse_failed"


def test_fetch_barcode_resolve_when_url_page_id_404() -> None:
    http_get = _get(
        {
            _details_url("222547542"): (404, json.dumps({"status_code": 404})),
            f"{REST_API}/rest/search?q=4711387767535": (200, _search(98174082)),
            _details_url("98174082"): (200, json.dumps(_details())),
        }
    )
    status, body, flags = rest_buybox.fetch(
        SITE, url=f"{REST_HOST}/ID222547542", http_get=http_get, external_id="222547542", ean="4711387767535"
    )
    assert status == 200
    assert flags["page_id_source"] == "barcode_search"
    assert flags["resolved_page_id"] == "98174082"
    assert flags["corroboration"] == "barcode"
    assert rest_buybox.parse(body, site=SITE, parser_version="t").price == 1799.0


def test_fetch_rejects_ambiguous_barcode_search() -> None:
    http_get = _get(
        {
            _details_url("1111111"): (404, "{}"),
            f"{REST_API}/rest/search?q=1234567890123": (200, _search(1, 2)),
        }
    )
    status, _body, flags = rest_buybox.fetch(SITE, url=f"{REST_HOST}/ID1111111", http_get=http_get, ean="1234567890123")
    assert flags["reason"] == "barcode_not_unique_or_missing"
    assert flags["barcode_result_count"] == 2
    assert status == 200


def test_fetch_without_search_pattern_does_not_search() -> None:
    site = rest_site(search=False)
    http_get = _get({_details_url("1111111"): (404, "{}")})
    _status, _body, flags = rest_buybox.fetch(site, url=f"{REST_HOST}/ID1111111", http_get=http_get, ean="1234567890123")
    assert flags["reason"] == "page_id_not_found"
    assert flags["barcode_resolve"] == "skipped_no_search"
    assert http_get.calls == [_details_url("1111111")]


# ---------------------------------------------------------------- record_observation with the reader


def test_record_observation_reads_the_data_endpoint_not_the_listing_html() -> None:
    session = _session("4711387767535")
    listing = _listing(id=52, url=f"{REST_HOST}/ID222547542", external_id="222547542")
    http_get = _get(
        {
            _details_url("222547542"): (404, "{}"),
            f"{REST_API}/rest/search?q=4711387767535": (200, _search(98174082)),
            _details_url("98174082"): (200, json.dumps(_details())),
        }
    )
    obs = record_observation(session, listing, http_get=http_get, site=SITE)
    assert obs.parse_status == "ok"
    assert float(obs.extracted_price) == 1799.0
    assert obs.parse_flags.get("cpor_activation", {}).get("status") is not None
    assert listing.meta_json["page_id"] == "98174082"
    assert listing.url == CANON
    assert listing.meta_json["original_url"] == f"{REST_HOST}/ID222547542"
    assert listing.meta_json["url_verified_at"]
    assert listing.status == "active"
    assert listing.url not in http_get.calls


def test_record_observation_known_page_id_rewrites_url_without_canonical() -> None:
    session = _session(None)
    listing = _listing(id=53, url=f"{REST_HOST}/ID225185639", meta_json={"page_id": "99667176"})
    details = _details()
    details.pop("desktop_href")
    details.pop("seo")
    record_observation(session, listing, http_get=_get({_details_url("99667176"): (200, json.dumps(details))}), site=SITE)
    assert listing.url == f"{REST_HOST}/x/ID99667176"
    assert listing.meta_json["original_url"] == f"{REST_HOST}/ID225185639"
    assert listing.meta_json["url_verified_at"]


def test_record_observation_original_url_preserved_across_rewrites() -> None:
    session = _session(None)
    listing = _listing(
        url=f"{REST_HOST}/x/ID98174082",
        meta_json={"page_id": "98174082", "original_url": f"{REST_HOST}/ID222547542"},
    )
    record_observation(session, listing, http_get=_get({_details_url("98174082"): (200, json.dumps(_details()))}), site=SITE)
    assert listing.url == CANON
    assert listing.meta_json["original_url"] == f"{REST_HOST}/ID222547542"


def test_record_observation_uncorroborated_barcode_hit_does_not_rewrite() -> None:
    session = _session("4711387767535")
    listing = _listing(url=f"{REST_HOST}/ID222547542", external_id="999")
    http_get = _get(
        {
            _details_url("222547542"): (404, "{}"),
            f"{REST_API}/rest/search?q=4711387767535": (200, _search(98174082)),
            _details_url("98174082"): (200, json.dumps(_details(ean="0000000000000"))),
        }
    )
    record_observation(session, listing, http_get=http_get, site=SITE)
    assert listing.url == f"{REST_HOST}/ID222547542"
    assert "url_verified_at" not in listing.meta_json


def test_record_observation_url_conflict_does_not_rewrite_or_verify() -> None:
    session = _session(None)
    session.scalar.return_value = 69
    listing = _listing(id=73, url=f"{REST_HOST}/ID234153078", meta_json={"page_id": "98174082"})
    obs = record_observation(session, listing, http_get=_get({_details_url("98174082"): (200, json.dumps(_details()))}), site=SITE)
    assert obs.parse_status == "ok"
    assert listing.url == f"{REST_HOST}/ID234153078"
    assert listing.meta_json["url_conflict_listing_id"] == 69
    assert "url_verified_at" not in listing.meta_json
    assert "original_url" not in listing.meta_json


def test_record_observation_404_no_barcode_marks_dead_link() -> None:
    session = _session(None)
    listing = _listing()
    obs = record_observation(session, listing, http_get=_get({_details_url("233951759"): (404, "{}")}), site=SITE)
    assert obs.parse_status != "ok"
    assert obs.parse_flags["details_status"] == 404
    assert obs.parse_flags["fetch_reason"] == "page_id_not_found"
    assert listing.status == "dead_link"
    assert listing.url == f"{REST_HOST}/ID233951759"


def test_record_observation_404_barcode_search_miss_marks_dead_link() -> None:
    session = _session("4711387767535")
    listing = _listing()
    http_get = _get(
        {
            _details_url("233951759"): (404, "{}"),
            f"{REST_API}/rest/search?q=4711387767535": (200, _search()),
        }
    )
    record_observation(session, listing, http_get=http_get, site=SITE)
    assert listing.status == "dead_link"


def test_record_observation_no_page_id_no_barcode_is_not_dead() -> None:
    session = _session(None)
    listing = _listing(url=f"{REST_HOST}/some-product")
    record_observation(session, listing, http_get=_no_http, site=SITE)
    assert listing.status == "active"
    assert not (listing.meta_json or {}).get("url_verified_at")


def test_record_observation_dead_link_backoff_unchanged() -> None:
    listing = _listing(status="dead_link", status_observed_at=datetime.now(timezone.utc))
    obs = record_observation(_session(None), listing, http_get=_no_http, consecutive_dead=3, site=SITE)
    assert obs.parse_status == "skipped"
    assert obs.parse_flags["reason"] == "dead_link_backoff"


def test_html_reader_ok_stamps_verified_without_rewrite() -> None:
    listing = SimpleNamespace(
        id=1, url="https://shop-a.example.test/p/1", marketplace="shop-a", status="active", status_observed_at=None, meta_json=None
    )
    record_observation(MagicMock(), listing, http_get=lambda _u: (200, '{"price": 55.0}'), site=html_site())
    assert listing.url == "https://shop-a.example.test/p/1"
    assert listing.meta_json["url_verified_at"]
    assert "original_url" not in listing.meta_json


def test_listing_url_verified_at_definition() -> None:
    ok_at = datetime(2026, 8, 10, tzinfo=timezone.utc)
    rest_listing = _listing(meta_json={"page_id": "98174082"})
    # A data-endpoint price observation does not verify the stored URL.
    assert listing_url_verified_at(rest_listing, last_ok_fetch_at=ok_at, site=SITE) is None
    rest_listing.meta_json = {"url_verified_at": "2026-09-24T00:00:00+00:00", "original_url": "u0"}
    assert listing_url_verified_at(rest_listing, site=SITE) == "2026-09-24T00:00:00+00:00"
    page = SimpleNamespace(marketplace="shop-a", meta_json=None)
    assert listing_url_verified_at(page, site=html_site()) is None
    assert listing_url_verified_at(page, last_ok_fetch_at=ok_at, site=html_site()) == ok_at.isoformat()
    # Unknown site: nothing verifies the URL but a stamp.
    assert listing_url_verified_at(page, last_ok_fetch_at=ok_at, site=None) is None

    row = SimpleNamespace(
        id=55,
        customer_id=20,
        product_id=None,
        url="u1",
        marketplace="market-b",
        status="active",
        source="feed_proposal",
        registered_by=None,
        registered_at=None,
        status_observed_at=None,
        external_id="1",
        notes=None,
        meta_json=rest_listing.meta_json,
    )
    d = listing_to_dict(row, site=SITE)
    assert d["url_verified_at"] == "2026-09-24T00:00:00+00:00"
    assert d["original_url"] == "u0"
    assert d["site_name"] == "Market B"
    assert d["site_configured"] is True
