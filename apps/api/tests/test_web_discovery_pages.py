"""Product-page finding (DISCOVERY_V2 §4.4) through Crawlee, with no network.

The fake getter stands in for the polite getter, so Crawlee's HTTP crawler, its queue and
its robots.txt handling run for real against in-memory pages.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from app.services.listing_capture.identity import page_facts_from_html
from app.services.listing_capture.web_discovery import pages
from app.services.listing_capture.web_discovery.candidates import ProductInfo
from app.services.listing_capture.web_discovery.linking import AUTO_LINK, QUEUE, CatalogueIndex
from app.services.listing_capture.web_discovery.polite import Fetched

HOST = "shop.example"
ORIGIN = f"https://{HOST}"
GTIN = "4006381333931"  # valid GS1 check digit
MODEL = "ZX9000-QT"


class FakeGetter:
    def __init__(self, routes: dict[str, str], prefixes: dict[str, str] | None = None) -> None:
        self.routes = routes
        self.prefixes = prefixes or {}
        self.calls: list[tuple[str, str]] = []
        self.policy = None

    def get(self, url: str, *, gate_key: str, spacing: float | None = None) -> Fetched:
        self.calls.append((url, gate_key))
        if url in self.routes:
            return Fetched(200, self.routes[url], url)
        for prefix, body in self.prefixes.items():
            if url.startswith(prefix):
                return Fetched(200, body, url)
        return Fetched(404, "", url)


def _product(pid: int = 1, **extra):
    base = dict(id=pid, tenant_id="t1", ean=GTIN, upc=None, sales_model_name=MODEL,
                part_number=None, model_name=None, name="Test product", sku=None)
    base.update(extra)
    return SimpleNamespace(**base)


def _product_page(gtin: str = GTIN, model: str = MODEL) -> str:
    data = {"@context": "https://schema.org", "@type": "Product", "name": "Test product",
            "gtin13": gtin, "mpn": model,
            "offers": {"@type": "Offer", "price": "1299.00", "priceCurrency": "XTS",
                       "availability": "https://schema.org/InStock"}}
    return (f'<html><head><script type="application/ld+json">{json.dumps(data)}</script>'
            f"</head><body><h1>Test product</h1>{'text ' * 200}</body></html>")


def _run(getter: FakeGetter, products, *, site=None, browser=False):
    index = CatalogueIndex.from_products(products, "t1")
    site = site or {"domain": HOST, "site_key": "shop", "search_pattern": {"value": None,
                                                                         "how": "none"}}
    found = pages.find_product_pages(
        None, SimpleNamespace(id=7, tenant_id="t1"), site, {}, getter,
        SimpleNamespace(browser_fallback_enabled=browser), index=index,
        products=[ProductInfo(id=p.id, sales_model_name=p.sales_model_name) for p in products],
    )
    return found, site


def test_opensearch_pattern_is_learned_and_the_page_auto_links_on_gtin() -> None:
    home = ('<html><head><link rel="search" type="application/opensearchdescription+xml" '
            'href="/os.xml"></head><body>home</body></html>')
    opensearch = ('<OpenSearchDescription><Url type="text/html" '
                  f'template="{ORIGIN}/find?term={{searchTerms}}"/></OpenSearchDescription>')
    results = f'<html><body><main><a href="/item/zx9000-qt">Test</a></main></body></html>'
    getter = FakeGetter(
        {f"{ORIGIN}/": home, f"{ORIGIN}/os.xml": opensearch,
         f"{ORIGIN}/item/zx9000-qt": _product_page(), f"{ORIGIN}/robots.txt": ""},
        {f"{ORIGIN}/find?term=": results},
    )
    found, site = _run(getter, [_product()])
    assert [page["outcome"] for page in found] == [AUTO_LINK]
    assert found[0]["how"] == "gtin" and found[0]["product_id"] == 1
    assert found[0]["url"] == f"{ORIGIN}/item/zx9000-qt"
    assert found[0]["found_by"] == "search:opensearch"
    assert site["search_pattern"] == {"value": f"{ORIGIN}/find?term={{query}}", "how": "opensearch"}
    assert site["learned"]["search_url_pattern"] == f"{ORIGIN}/find?term={{query}}"
    # Every request went through the polite getter under the site's host gate.
    assert {key for _url, key in getter.calls} == {f"host:{HOST}"}


def test_sitemap_from_robots_finds_the_page_when_the_site_has_no_search() -> None:
    getter = FakeGetter({
        f"{ORIGIN}/": "<html><body>no search here</body></html>",
        f"{ORIGIN}/robots.txt": f"User-agent: *\nAllow: /\nSitemap: {ORIGIN}/map.xml\n",
        f"{ORIGIN}/map.xml": (f"<urlset><url><loc>{ORIGIN}/p/other</loc></url>"
                              f"<url><loc>{ORIGIN}/p/zx9000-qt</loc></url></urlset>"),
        f"{ORIGIN}/p/zx9000-qt": _product_page(),
    })
    found, _site = _run(getter, [_product()])
    assert [(page["outcome"], page["found_by"]) for page in found] == [(AUTO_LINK, "sitemap")]


def test_robots_disallow_means_the_page_is_never_requested() -> None:
    getter = FakeGetter({
        f"{ORIGIN}/": "<html><body>x</body></html>",
        f"{ORIGIN}/robots.txt": (f"User-agent: *\nDisallow: /p/\nSitemap: {ORIGIN}/map.xml\n"),
        f"{ORIGIN}/map.xml": f"<urlset><url><loc>{ORIGIN}/p/zx9000-qt</loc></url></urlset>",
        f"{ORIGIN}/p/zx9000-qt": _product_page(),
    })
    found, _site = _run(getter, [_product()])
    assert found == []
    assert f"{ORIGIN}/p/zx9000-qt" not in [url for url, _key in getter.calls]


def test_identity_of_another_product_goes_to_the_steward_queue() -> None:
    getter = FakeGetter({
        f"{ORIGIN}/": "<html><body>x</body></html>",
        f"{ORIGIN}/robots.txt": f"Sitemap: {ORIGIN}/map.xml\n",
        f"{ORIGIN}/map.xml": f"<urlset><url><loc>{ORIGIN}/p/zx9000-qt</loc></url></urlset>",
        f"{ORIGIN}/p/zx9000-qt": _product_page(gtin="96385074", model="OTHER-77"),
    })
    products = [_product(), _product(2, ean="96385074", sales_model_name="OTHER-77")]
    found, _site = _run(getter, products[:1] + products[1:])
    first = [page for page in found if page["product_id"] == 1]
    assert first and first[0]["outcome"] == QUEUE and first[0]["reason"] == "identity_mismatch"


def test_script_built_page_without_browser_is_reported_needs_browser() -> None:
    shell = "<html><body><div id=app></div>" + "<script src=a.js></script>" * 4 + "</body></html>"
    getter = FakeGetter({
        f"{ORIGIN}/": "<html><body>x</body></html>",
        f"{ORIGIN}/robots.txt": f"Sitemap: {ORIGIN}/map.xml\n",
        f"{ORIGIN}/map.xml": f"<urlset><url><loc>{ORIGIN}/p/zx9000-qt</loc></url></urlset>",
        f"{ORIGIN}/p/zx9000-qt": shell,
    })
    found, _site = _run(getter, [_product()], browser=False)
    assert [page["outcome"] for page in found] == [pages.OUTCOME_NEEDS_BROWSER]


def test_embedded_page_data_supplies_identity_for_script_built_pages() -> None:
    data = {"props": {"pageProps": {"product": {"ean": GTIN, "manufacturerPartNumber": MODEL}}}}
    html = (f'<html><body><script id="__NEXT_DATA__" type="application/json">'
            f"{json.dumps(data)}</script></body></html>")
    facts = page_facts_from_html(html)
    assert facts["barcodes"] == [GTIN]
    assert facts["models"] == [MODEL]


def test_opensearch_parsing_drops_optional_parameters() -> None:
    xml = ('<Url type="text/html" template="https://s.example/q?x={searchTerms}&amp;p={startPage?}"/>')
    assert pages.opensearch_pattern(xml.replace("&amp;", "&"), "https://s.example/") == (
        "https://s.example/q?x={query}&p="
    )


def test_the_crawlee_http_crawler_is_used_not_the_plain_fallback(monkeypatch) -> None:
    from app.services.listing_capture.web_discovery import crawl

    def refuse(*_args, **_kwargs):
        raise AssertionError("plain fallback used")

    monkeypatch.setattr(crawl, "_fetch_plain", refuse)
    getter = FakeGetter({f"{ORIGIN}/a": "<html>a</html>", f"{ORIGIN}/robots.txt": ""})
    result = crawl.fetch_pages([f"{ORIGIN}/a"], getter, gate_key_for=lambda _u: "host:x")
    assert result[f"{ORIGIN}/a"].body == "<html>a</html>"


def test_playwright_renders_a_script_built_page_through_the_gate() -> None:
    import pytest

    from app.services.listing_capture.web_discovery import crawl

    if not crawl.browser_available():
        pytest.skip("Playwright is not installed")
    data = json.dumps({"@context": "https://schema.org", "@type": "Product", "gtin13": GTIN})
    script = ("<script>var s=document.createElement('script');s.type='application/ld+json';"
              f"s.text={json.dumps(data)};document.head.appendChild(s);</script>")
    shell = f"<html><head></head><body><div id=app></div>{script}</body></html>"
    getter = FakeGetter({f"{ORIGIN}/p/1": shell, f"{ORIGIN}/robots.txt": ""})
    result = crawl.render_pages([f"{ORIGIN}/p/1"], getter, gate_key_for=lambda _u: "host:x")
    page = result.get(f"{ORIGIN}/p/1")
    if page is None:
        pytest.skip("the browser could not start on this machine")
    assert page.rendered
    assert page_facts_from_html(page.body)["barcodes"] == [GTIN]
    assert (f"{ORIGIN}/p/1", "host:x") in getter.calls
