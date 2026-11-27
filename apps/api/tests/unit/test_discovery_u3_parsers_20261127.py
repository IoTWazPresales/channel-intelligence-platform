"""U3 parser, timing and fetch behaviour. No database."""

from __future__ import annotations

import pytest
from app.services import tenant_settings
from app.services.listing_capture import discovery
from app.services.listing_capture.web_discovery.document_parse import (
    absolute_url,
    document_links,
    search_form,
)
from app.services.listing_capture.web_discovery.page_facts import page_facts_from_html
from app.services.listing_capture.web_discovery.sitemaps import sitemap_page_urls


def test_form_links_and_url_case() -> None:
    html = (
        '<nav><a href="/login">in</a></nav><a href="/p/GLIDE14">item</a>'
        '<form action="/find"><input name="search"></form>'
    )
    assert search_form(html) == ("/find", "search")
    assert ("/login", True) in document_links(html)
    assert ("/p/GLIDE14", False) in document_links(html)
    assert (
        absolute_url("https://maps.example.test/x", "/p/GLIDE14")
        == "https://maps.example.test/p/GLIDE14"
    )


# Requirement (Warren, 27 Nov 2026): sitemaps are read with ultimate-sitemap-parser,
# and every sitemap request still goes through the caller's paced fetch.
def test_sitemap_pages_come_only_through_the_given_fetch() -> None:
    seen: list[str] = []
    bodies = {
        "https://maps.example.test/sitemap.xml": (
            "<urlset><url><loc>https://maps.example.test/p/GLIDE14</loc></url></urlset>"
        ),
    }

    def fetch(url: str) -> tuple[int, str]:
        seen.append(url)
        return (200, bodies[url]) if url in bodies else (404, "")

    pages = sitemap_page_urls(
        ["https://maps.example.test/sitemap.xml", "https://maps.example.test/missing.xml"],
        fetch,
        max_children=2,
    )
    assert pages == ["https://maps.example.test/p/GLIDE14"]
    assert seen == [
        "https://maps.example.test/sitemap.xml",
        "https://maps.example.test/missing.xml",
    ]


def test_sitemap_index_follows_at_most_two_children_one_level_down() -> None:
    root = "https://maps.example.test/sitemap.xml"
    index = (
        "<sitemapindex>"
        + "".join(
            f"<sitemap><loc>https://maps.example.test/s{i}.xml</loc></sitemap>" for i in range(1, 4)
        )
        + "</sitemapindex>"
    )
    nested = (
        "<sitemapindex><sitemap><loc>https://maps.example.test/deep.xml</loc></sitemap>"
        "</sitemapindex>"
    )
    bodies = {
        root: index,
        "https://maps.example.test/s1.xml": (
            "<urlset><url><loc>https://maps.example.test/p/A1</loc></url></urlset>"
        ),
        "https://maps.example.test/s2.xml": nested,
        "https://maps.example.test/s3.xml": (
            "<urlset><url><loc>https://maps.example.test/p/A3</loc></url></urlset>"
        ),
    }
    seen: list[str] = []

    def fetch(url: str) -> tuple[int, str]:
        seen.append(url)
        return (200, bodies[url]) if url in bodies else (404, "")

    assert sitemap_page_urls([root], fetch, max_children=2) == ["https://maps.example.test/p/A1"]
    assert seen == [root, "https://maps.example.test/s1.xml", "https://maps.example.test/s2.xml"]


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
