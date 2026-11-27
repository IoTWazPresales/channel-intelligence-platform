"""Read-only proof that the Discovery V2 libraries work on THIS runtime (API or worker venv).

Run it with the interpreter that runs the worker, from ``apps/api``::

    .venv\\Scripts\\python.exe scripts\\ops\\prove_discovery_libraries.py

It prints one row per library: group, library, version, evidence, works yes/no.
Exit code 0 only when every row works.

What it does and does not do:

- No database, no Redis, no settings, no ``.env`` and no environment value is read or printed.
- No outbound network. Pages come from an in-memory getter that stands in for the polite getter, so
  the project's own wrappers (``crawl.fetch_pages``, ``crawl.render_pages``, ``page_facts``,
  ``robots``, ``scoring``) run on synthetic input under the reserved ``.test`` domain.
- The search library (ddgs) is proven by import and client construction only; a live search is an
  outbound call and runs only when ``--live-search "<query>"`` is given.

Grouping (ASSUMPTION C1 in the step 3 tracker): (1) Crawlee + Playwright (+ browserforge),
(2) ddgs, (3) extruct + price-parser, (4) tldextract + protego,
(5) selectolax + courlan + w3lib + Babel + ultimate-sitemap-parser (GPL-3.0-or-later).
"""

from __future__ import annotations

import argparse
import importlib.metadata as metadata
import sys
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

_API_ROOT = Path(__file__).resolve().parents[2]
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

# Synthetic and reserved: ``.test`` never resolves, so nothing here can reach a real site.
_HOST = "shop.acme.test"
_PRODUCT_URL = f"https://{_HOST}/p/widget-1"
_JSON_LD_PAGE = """<html><head><title>Widget</title>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Product","name":"Widget One","gtin13":"4006381333931",
 "mpn":"WID-1","brand":{"@type":"Brand","name":"Acme"},
 "offers":{"@type":"Offer","price":"1299.50","priceCurrency":"USD",
           "availability":"https://schema.org/InStock"}}
</script></head><body><h1>Widget One</h1></body></html>"""
_SCRIPT_BUILT_PAGE = """<html><head><title>Shell</title></head><body><div id="root"></div>
<script>document.getElementById('root').innerHTML =
  '<a href="/p/built-by-script">built-by-script-link</a>';</script></body></html>"""
_ROBOTS = "User-agent: *\nDisallow: /private\nCrawl-delay: 2\nSitemap: https://shop.acme.test/sitemap.xml\n"


@dataclass
class Check:
    group: str
    library: str
    version: str
    evidence: str
    works: bool


class _MemoryGetter:
    """Stands in for ``PoliteGetter``.

    Same ``get`` signature, answers from memory, never the network.
    """

    def __init__(self, pages: dict[str, str]) -> None:
        self._pages = pages
        self.requested: list[str] = []

    def get(self, url: str, *, gate_key: str = "", spacing: float | None = None):  # noqa: ARG002
        from app.services.listing_capture.web_discovery.polite import Fetched

        self.requested.append(url)
        if url in self._pages:
            return Fetched(200, self._pages[url], url)
        return Fetched(404, "", url)


def _version(distribution: str) -> str:
    try:
        return metadata.version(distribution)
    except metadata.PackageNotFoundError:
        return "MISSING"


def _crawlee_http() -> tuple[bool, str]:
    from app.services.listing_capture.web_discovery import crawl

    getter = _MemoryGetter({_PRODUCT_URL: _JSON_LD_PAGE})
    out = crawl.fetch_pages([_PRODUCT_URL], getter, gate_key_for=lambda _u: _HOST)
    page = out.get(_PRODUCT_URL)
    ok = page is not None and page.status == 200 and "Widget One" in page.body and not page.rendered
    return (
        ok,
        "HttpCrawler fetched one synthetic page through the gated client"
        if ok
        else "no page returned",
    )


def _playwright_chromium() -> tuple[bool, str]:
    from app.services.listing_capture.web_discovery import crawl

    path = crawl._chromium_executable_path()  # noqa: SLF001 - the helper the capability banner uses
    present = bool(path) and Path(str(path)).is_file()
    return (
        present,
        "chromium executable file exists" if present else "chromium executable not found",
    )


def _crawlee_render() -> tuple[bool, str]:
    from app.services.listing_capture.web_discovery import crawl

    getter = _MemoryGetter({_PRODUCT_URL: _SCRIPT_BUILT_PAGE})
    out = crawl.render_pages([_PRODUCT_URL], getter, gate_key_for=lambda _u: _HOST)
    page = out.get(_PRODUCT_URL)
    # The script text also contains the link, so match the serialized DOM (an element inside #root),
    # which the page source does not contain.
    built = '<div id="root"><a href="/p/built-by-script">built-by-script-link</a></div>'
    ok = bool(page and page.rendered and built in page.body and built not in _SCRIPT_BUILT_PAGE)
    return ok, (
        "PlaywrightCrawler ran the page script; the link exists only in the rendered DOM"
        if ok
        else "browser render returned nothing usable"
    )


def _browserforge() -> tuple[bool, str]:
    import browserforge.fingerprints  # noqa: F401 - Crawlee's dependency

    return True, "imports; Discovery runs with fingerprint_generator=None (no generator used)"


def _ddgs_client() -> tuple[bool, str]:
    from ddgs import DDGS

    with DDGS(timeout=5) as client:
        ok = callable(getattr(client, "text", None))
    return ok, "DDGS client constructs and exposes text(); no search sent"


def _ddgs_live(query: str) -> tuple[bool, str]:
    from app.services.listing_capture.web_discovery import search

    status, page = search._ddgs_page(query, {"max_results": 3, "timeout_seconds": 15})  # noqa: SLF001
    return (
        status == 200 and page.status == search.PARSED_OK,
        f"live search status {status}, {len(page.hits)} hits",
    )


def _extruct() -> tuple[bool, str]:
    from app.services.listing_capture.web_discovery.page_facts import page_facts_from_html

    facts = page_facts_from_html(_JSON_LD_PAGE, _PRODUCT_URL)
    ok = "4006381333931" in facts.gtin and "WID-1" in facts.mpn and facts.name == "Widget One"
    return ok, "JSON-LD Product read: gtin, mpn and name" if ok else f"unexpected facts {facts}"


def _price_parser() -> tuple[bool, str]:
    from app.services.listing_capture.web_discovery.page_facts import page_facts_from_html

    facts = page_facts_from_html(_JSON_LD_PAGE, _PRODUCT_URL)
    ok = facts.price_amount == Decimal("1299.50") and facts.price_currency == "USD"
    return (
        ok,
        "offer price parsed to Decimal 1299.50 with its currency" if ok else "price not parsed",
    )


def _tldextract() -> tuple[bool, str]:
    from app.services.listing_capture.web_discovery import scoring

    host = scoring.host_from_url(f"https://www.{_HOST}/x")
    key = scoring.domain_key(host, [".test"])
    ok = host == _HOST and key == "acme"
    return (
        ok,
        "offline suffix list: host kept with subdomain, registrable name 'acme'"
        if ok
        else f"{host!r} {key!r}",
    )


def _protego() -> tuple[bool, str]:
    from app.services.listing_capture.web_discovery.robots import parse_robots

    rules = parse_robots(_ROBOTS)
    ok = (
        rules.allowed("/p/widget-1")
        and not rules.allowed("/private/x")
        and rules.spacing_floor() == 2.0
        and rules.sitemaps == [f"https://{_HOST}/sitemap.xml"]
    )
    return (
        ok,
        "robots.txt parsed: allow, disallow, crawl-delay and sitemap"
        if ok
        else "robots rules wrong",
    )


def _selectolax() -> tuple[bool, str]:
    from app.services.listing_capture.web_discovery.document_parse import (
        document_links,
        search_form,
    )

    html = (
        '<nav><a href="/login">in</a></nav><a href="/p/item-1">p</a>'
        '<form action="/find"><input name="search"></form>'
    )
    ok = search_form(html) == ("/find", "search") and ("/login", True) in document_links(html)
    return ok, "lexbor form and navigation link" if ok else "form or link parse failed"


def _urls() -> tuple[bool, str]:
    from app.services.listing_capture.web_discovery.document_parse import absolute_url

    url = absolute_url(f"https://{_HOST}/", "/p/GLIDE14")
    ok = url == f"https://{_HOST}/p/GLIDE14"
    return ok, "path case kept" if ok else f"{url!r}"


def _babel() -> tuple[bool, str]:
    from app.services.listing_capture.web_discovery.page_facts import page_facts_from_html

    page = _JSON_LD_PAGE.replace('"1299.50"', '"1.299,50"')
    facts = page_facts_from_html(page, _PRODUCT_URL, locale="de_DE")
    ok = facts.price_amount == Decimal("1299.50")
    return ok, "de_DE 1.299,50 parsed to 1299.50" if ok else f"{facts.price_amount!r}"


def _sitemaps() -> tuple[bool, str]:
    from app.services.listing_capture.web_discovery.sitemaps import sitemap_page_urls

    root = f"https://{_HOST}/sitemap.xml"
    body = f"<urlset><url><loc>{_PRODUCT_URL}</loc></url></urlset>"
    seen: list[str] = []

    def fetch(url: str) -> tuple[int, str]:
        seen.append(url)
        return (200, body) if url == root else (404, "")

    pages = sitemap_page_urls([root], fetch, max_children=2)
    ok = pages == [_PRODUCT_URL] and seen == [root]
    return ok, "urlset read through the given fetch only" if ok else f"{pages!r} {seen!r}"


def _run(group: str, library: str, distribution: str, fn: Callable[[], tuple[bool, str]]) -> Check:
    version = _version(distribution)
    if version == "MISSING":
        return Check(group, library, version, "package not installed", False)
    try:
        ok, evidence = fn()
    except Exception as exc:  # noqa: BLE001 - a failing library is a result, not a crash
        return Check(group, library, version, f"{type(exc).__name__}: {str(exc)[:120]}", False)
    return Check(group, library, version, evidence, bool(ok))


def run_checks(*, include_browser: bool = True, live_search: str | None = None) -> list[Check]:
    g1, g2, g3, g4 = (
        "1 Crawlee + Playwright",
        "2 ddgs",
        "3 extruct + price-parser",
        "4 tldextract + protego",
    )
    checks = [
        _run(g1, "crawlee (HttpCrawler)", "crawlee", _crawlee_http),
        _run(g1, "browserforge", "browserforge", _browserforge),
    ]
    if include_browser:
        checks.append(_run(g1, "playwright (chromium present)", "playwright", _playwright_chromium))
        checks.append(_run(g1, "crawlee (PlaywrightCrawler render)", "crawlee", _crawlee_render))
    checks.append(_run(g2, "ddgs (client)", "ddgs", _ddgs_client))
    if live_search:
        checks.append(_run(g2, "ddgs (live search)", "ddgs", lambda: _ddgs_live(live_search)))
    checks += [
        _run(g3, "extruct", "extruct", _extruct),
        _run(g3, "price-parser", "price-parser", _price_parser),
        _run(g4, "tldextract", "tldextract", _tldextract),
        _run(g4, "protego", "protego", _protego),
        _run("5 parsers", "selectolax", "selectolax", _selectolax),
        _run("5 parsers", "courlan", "courlan", _urls),
        _run("5 parsers", "w3lib", "w3lib", _urls),
        _run("5 parsers", "Babel", "Babel", _babel),
        _run("5 parsers", "ultimate-sitemap-parser", "ultimate-sitemap-parser", _sitemaps),
    ]
    return checks


def render_table(checks: list[Check]) -> str:
    rows = [("group", "library", "version", "works", "evidence")]
    rows += [
        (c.group, c.library, c.version, "yes" if c.works else "NO", c.evidence) for c in checks
    ]
    widths = [max(len(row[i]) for row in rows) for i in range(4)]
    lines = []
    for row in rows:
        lines.append(" | ".join(row[i].ljust(widths[i]) for i in range(4)) + " | " + row[4])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--no-browser", action="store_true", help="skip the chromium checks")
    parser.add_argument(
        "--live-search", metavar="QUERY", help="send ONE real search (outbound network)"
    )
    args = parser.parse_args(argv)
    checks = run_checks(include_browser=not args.no_browser, live_search=args.live_search)
    print(render_table(checks))
    return 0 if all(c.works for c in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
