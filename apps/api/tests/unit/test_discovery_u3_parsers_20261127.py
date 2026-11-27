"""U3 parser, timing and fetch behaviour. No database."""

from __future__ import annotations

import pytest

from app.services import tenant_settings
from app.services.listing_capture import discovery
from app.services.listing_capture.web_discovery.document_parse import (
    absolute_url,
    document_links,
    search_form,
    sitemap_locs,
)
from app.services.listing_capture.web_discovery.page_facts import page_facts_from_html


def test_form_links_sitemap_and_url_case() -> None:
    html = (
        '<nav><a href="/login">in</a></nav><a href="/p/GLIDE14">item</a>'
        '<form action="/find"><input name="search"></form>'
    )
    assert search_form(html) == ("/find", "search")
    assert ("/login", True) in document_links(html)
    assert ("/p/GLIDE14", False) in document_links(html)
    assert absolute_url("https://maps.example.test/x", "/p/GLIDE14") == "https://maps.example.test/p/GLIDE14"
    kind, locs = sitemap_locs(
        "<urlset><url><loc>https://maps.example.test/p/GLIDE14</loc></url></urlset>"
    )
    assert kind == "urlset" and locs == ["https://maps.example.test/p/GLIDE14"]


def test_babel_locale_replaces_the_price_and_a_bad_tag_is_no_price() -> None:
    page = (
        '<script type="application/ld+json">'
        '{"@type":"Product","offers":{"price":"1.299,50","priceCurrency":"EUR"}}'
        "</script>"
    )
    from decimal import Decimal

    assert page_facts_from_html(page, locale="de_DE").price_amount == Decimal("1299.50")
    assert page_facts_from_html(page, locale="de_DE").price_amount != Decimal("1.299")
    assert page_facts_from_html(page, locale="not_a_locale").price_amount is None


def test_unset_locale_still_uses_price_parser() -> None:
    page = (
        '<script type="application/ld+json">'
        '{"@type":"Product","offers":{"price":"199.00","priceCurrency":"USD"}}'
        "</script>"
    )
    from decimal import Decimal

    assert page_facts_from_html(page).price_amount == Decimal("199.00")


def test_timing_validators_have_no_fallback() -> None:
    assert tenant_settings._as_debounce_hours(6) == 6.0
    assert tenant_settings._as_coalesce_seconds(90) == 90
    assert tenant_settings._as_matrix_customer_ids([3, 3, 1]) == [3, 1]
    with pytest.raises(ValueError):
        tenant_settings._as_debounce_hours(0)
    with pytest.raises(ValueError):
        tenant_settings._as_coalesce_seconds(1.5)
    with pytest.raises(ValueError):
        tenant_settings._as_locale("not-a-real-language")


def test_schedule_on_requires_saved_timings(monkeypatch) -> None:
    monkeypatch.setattr(tenant_settings, "get_setting", lambda *_a, **_k: None)
    with pytest.raises(ValueError, match="scheduled_run_debounce_hours"):
        tenant_settings._check_schedule_timings(object(), "t", True)
    tenant_settings._check_schedule_timings(object(), "t", False)


def test_http_does_not_fetch_again_when_crawlee_returns_nothing(monkeypatch) -> None:
    calls: list[str] = []

    def http_get(url: str):
        calls.append(url)
        return 404, ""

    monkeypatch.setattr(
        "app.services.listing_capture.web_discovery.crawl.fetch_pages", lambda *_a, **_k: {}
    )
    token = discovery._ROBOTS.set({})
    try:
        assert discovery._http(http_get, "https://catalogue.example.test/p/1") == (0, "")
    finally:
        discovery._ROBOTS.reset(token)
    assert calls == ["https://catalogue.example.test/robots.txt"]
