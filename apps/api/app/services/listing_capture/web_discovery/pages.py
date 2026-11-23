"""(c) Product pages on accepted sites (DISCOVERY_V2 §4.4), read-only.

For each accepted site and up to ``limit`` of the customer's products:

1. **Site search, learned and reused:** the site's stored ``search_url_pattern``; else the
   site's OpenSearch description (``<link rel="search">``); else the home-page search form
   (``discovery._discover_search_pattern``). The first pattern whose result page leads to
   a product page with exact identity evidence is *learned* and reused for the remaining
   products. Nothing is guessed from a built-in list: every pattern comes from the site.
2. **robots.txt + sitemaps:** ``Sitemap:`` lines from robots.txt, then ``/sitemap.xml``
   (the robots.txt standard location), following a sitemap index one level.
3. **Page facts:** extruct (JSON-LD, microdata, OpenGraph) plus identity keys in data
   embedded in the page (``identity.page_facts_from_html``).
4. **Browser fallback:** a page with no facts that looks script-built is rendered with
   Crawlee's Playwright crawler when ``discovery.browser_fallback_enabled`` is on;
   otherwise it is reported as ``needs_browser``.
5. **Linking decision:** ``linking.decide`` (exact GTIN/EAN, or an exact normalised model
   or part code matching exactly one product). Anything else goes to the steward queue.
6. **Patterns:** two or more auto-linked pages on a site → ``_derived_patterns``.

All fetching goes through Crawlee (``crawl.fetch_pages`` / ``crawl.render_pages``) on top of
the polite getter, so robots.txt, per-site spacing and the 403/429 pause apply. No site,
domain, path or country is named in this module.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from typing import Any
from urllib.parse import quote, urljoin, urlsplit

from app.services.listing_capture import discovery
from app.services.listing_capture.adapters import SiteConfig
from app.services.listing_capture.identity import page_facts_from_html
from app.services.listing_capture.web_discovery import candidates as cand
from app.services.listing_capture.web_discovery import crawl
from app.services.listing_capture.web_discovery.linking import (
    AUTO_LINK,
    QUEUE,
    CatalogueIndex,
    decide,
)
from app.services.listing_capture.web_discovery.polite import DEFAULT_SPACING_SECONDS
from app.services.listing_capture.web_discovery.scoring import normalize_host

PRODUCTS_PER_SITE = 5
QUERIES_PER_PRODUCT = 2
PAGES_PER_PRODUCT = 3
SITEMAP_CHILDREN = 3
MAX_SITEMAP_LOCS = 50_000
CLIENT_RENDERED_TEXT = 500
CLIENT_RENDERED_SCRIPTS = 3

OUTCOME_NEEDS_BROWSER = "needs_browser"

_LINK_TAG = re.compile(r"<link\b[^>]*>", re.IGNORECASE)
_ATTR = re.compile(r"""([a-zA-Z:-]+)\s*=\s*["']([^"']*)["']""")
_URL_TAG = re.compile(r"<Url\b[^>]*>", re.IGNORECASE)
_SCRIPT = re.compile(r"<script\b", re.IGNORECASE)


def _attrs(tag: str) -> dict[str, str]:
    return {key.lower(): value for key, value in _ATTR.findall(tag)}


def opensearch_href(home: str, base: str) -> str | None:
    for tag in _LINK_TAG.findall(home or ""):
        attrs = _attrs(tag)
        if "search" in attrs.get("rel", "").lower().split() and (
            attrs.get("type", "").lower() == "application/opensearchdescription+xml"
        ) and attrs.get("href"):
            return urljoin(base, attrs["href"])
    return None


def opensearch_pattern(description: str, base: str) -> str | None:
    """The ``text/html`` ``Url`` template of an OpenSearch description, as ``{query}``."""
    for tag in _URL_TAG.findall(description or ""):
        attrs = _attrs(tag)
        template = attrs.get("template") or ""
        if attrs.get("type", "text/html").lower() == "text/html" and "{searchTerms}" in template:
            pattern = urljoin(base, template.replace("{searchTerms}", "{query}"))
            # Optional OpenSearch parameters ({name?}) are dropped.
            pattern = re.sub(r"\{[A-Za-z:]+\?\}", "", pattern)
            if "{query}" in pattern and "{" not in pattern.replace("{query}", ""):
                return pattern
    return None


def looks_client_rendered(body: str) -> bool:
    try:
        import html_text

        text = html_text.extract_text(body or "")
    except Exception:  # noqa: BLE001
        text = re.sub(r"<[^>]+>", " ", body or "")
    return len(text.strip()) < CLIENT_RENDERED_TEXT and len(_SCRIPT.findall(body or "")) >= (
        CLIENT_RENDERED_SCRIPTS
    )


def _has_identity(facts: dict[str, Any]) -> bool:
    return bool(facts.get("barcodes") or facts.get("models"))


def sitemap_locs(body: str) -> tuple[list[str], bool]:
    """``<loc>`` values and whether the document is a sitemap index."""
    locs = [item.strip() for item in discovery._LOC.findall(body or "")]  # noqa: SLF001
    index = bool(re.search(r"<sitemapindex\b", body or "", flags=re.IGNORECASE))
    return locs[:MAX_SITEMAP_LOCS], index


def robots_sitemaps(body: str) -> list[str]:
    out = []
    for line in (body or "").splitlines():
        key, _, value = line.partition(":")
        if key.strip().lower() == "sitemap" and value.strip():
            out.append(value.strip())
    return out


def _token_forms(token: str) -> list[str]:
    raw = token.strip().lower()
    forms = {raw, re.sub(r"[^a-z0-9]+", "-", raw).strip("-"), re.sub(r"[^a-z0-9]", "", raw)}
    return [form for form in forms if len(form) >= 4]


class _Site:
    """Per-site state for one find_pages call."""

    def __init__(self, site: dict[str, Any], getter: Any, settings: Any, spacing: float) -> None:
        self.domain = normalize_host(str(site.get("domain") or ""))
        self.origin = f"https://{self.domain}"
        self.getter = getter
        self.browser = bool(getattr(settings, "browser_fallback_enabled", False))
        self.spacing = spacing
        self.bodies: dict[str, crawl.PageResult] = {}
        self._sitemap: list[str] | None = None

    def gate_key(self, url: str) -> str:
        return f"host:{normalize_host(urlsplit(url).hostname or '')}"

    def same_site(self, url: str) -> bool:
        return normalize_host(urlsplit(url).hostname or "") == self.domain

    def time_left(self) -> bool:
        policy = getattr(self.getter, "policy", None)
        return policy is None or policy.time_left() > 0

    def fetch(self, urls: list[str]) -> dict[str, crawl.PageResult]:
        wanted = [url for url in urls if url not in self.bodies and self.same_site(url)]
        if wanted and self.time_left():
            self.bodies.update(
                crawl.fetch_pages(wanted, self.getter, gate_key_for=self.gate_key,
                                  spacing=self.spacing)
            )
        return {url: self.bodies[url] for url in urls if url in self.bodies}

    def body(self, url: str) -> str:
        page = self.fetch([url]).get(url)
        return page.body if page is not None and page.status == 200 and not page.refused else ""

    def http_get(self, url: str) -> tuple[int, str]:
        page = self.fetch([url]).get(url)
        if page is None or page.refused:
            return 0, ""
        return page.status, page.body

    def render(self, url: str) -> crawl.PageResult | None:
        if not self.browser or not self.time_left():
            return None
        rendered = crawl.render_pages([url], self.getter, gate_key_for=self.gate_key,
                                      spacing=self.spacing).get(url)
        if rendered is not None and rendered.body:
            self.bodies[url] = rendered
        return rendered

    def sitemap(self) -> list[str]:
        if self._sitemap is not None:
            return self._sitemap
        roots = robots_sitemaps(self.body(self.origin + "/robots.txt")) or [
            self.origin + "/sitemap.xml"
        ]
        locs: list[str] = []
        for root in roots[:SITEMAP_CHILDREN]:
            found, is_index = sitemap_locs(self.body(root))
            if is_index:
                for child in found[:SITEMAP_CHILDREN]:
                    locs.extend(sitemap_locs(self.body(child))[0])
            else:
                locs.extend(found)
        self._sitemap = [loc for loc in dict.fromkeys(locs) if self.same_site(loc)]
        return self._sitemap


def _search_patterns(state: _Site, site: dict[str, Any]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    stored = (site.get("search_pattern") or {}).get("value")
    if stored:
        out.append((stored, "stored"))
    home = state.body(state.origin + "/")
    href = opensearch_href(home, state.origin + "/")
    if href and state.same_site(href):
        pattern = opensearch_pattern(state.body(href), href)
        if pattern and state.same_site(pattern):
            out.append((pattern, "opensearch"))
    config = SiteConfig(site_key=str(site.get("site_key") or state.domain), display_name=state.domain)
    form = discovery._discover_search_pattern(  # noqa: SLF001
        config, {"origin": state.origin}, state.http_get
    )
    if form and state.same_site(form):
        out.append((form, "form"))
    return list(dict.fromkeys(out))


def _item_id(customer_id: int, product_id: int, url: str) -> str:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
    return f"p-{customer_id}-{product_id}-{digest}"


def _read_page(state: _Site, url: str) -> tuple[dict[str, Any], crawl.PageResult | None, bool]:
    page = state.fetch([url]).get(url)
    if page is None or page.refused or page.status != 200:
        return {}, page, False
    facts = page_facts_from_html(page.body)
    if _has_identity(facts) or not looks_client_rendered(page.body):
        return facts, page, False
    rendered = state.render(url)
    if rendered is None or not rendered.body:
        return facts, page, True
    return page_facts_from_html(rendered.body), rendered, False


def _capture(config: SiteConfig, url: str, body: str, product: Any) -> dict[str, Any]:
    captured = discovery._capture_url(  # noqa: SLF001
        config, url, lambda _u: (200, body), product
    )
    return dict(captured or {})



def _process(state: _Site, config: SiteConfig, index: CatalogueIndex, info: Any, product: Any,
             found: list[tuple[str, str, str | None]], pages: list[dict[str, Any]],
             auto_urls: list[str], customer_id: int) -> bool:
    """Read candidate pages for one product; True when an item was recorded."""
    found = list(dict.fromkeys(found))[:PAGES_PER_PRODUCT]
    state.fetch([url for url, _by, _pattern in found])
    recorded = False
    for url, found_by, pattern in found:
        facts, page, needs_browser = _read_page(state, url)
        if needs_browser:
            pages.append({
                "item_id": _item_id(customer_id, int(info.id), url),
                "url": url,
                "product_id": int(info.id),
                "outcome": OUTCOME_NEEDS_BROWSER,
                "how": None,
                "reason": "needs_browser",
                "candidates": [],
                "facts": facts,
                "found_by": found_by,
            })
            return True
        if not _has_identity(facts):
            continue
        decision = decide(facts, index, expected_product_id=int(info.id))
        if decision.outcome not in (AUTO_LINK, QUEUE):
            continue
        item = decision.to_dict(index)
        item.update(
            item_id=_item_id(customer_id, int(info.id), url),
            url=url,
            product_id=int(info.id),
            found_by=found_by,
            rendered=bool(page is not None and page.rendered),
            _pattern=pattern,
        )
        if decision.outcome == AUTO_LINK and page is not None:
            item["capture"] = _capture(config, url, page.body, product)
            auto_urls.append(url)
        pages.append(item)
        recorded = True
        if decision.outcome == AUTO_LINK:
            break
    return recorded

def find_product_pages(
    session: Any,
    customer: Any,
    site: dict[str, Any],
    entry: dict[str, Any],
    getter: Any,
    settings: Any,
    *,
    index: CatalogueIndex,
    products: list[cand.ProductInfo],
    limit: int = PRODUCTS_PER_SITE,
) -> list[dict[str, Any]]:
    """Product pages on one accepted site. Writes nothing; ``site`` gains ``learned``."""
    del session, entry
    spacing = DEFAULT_SPACING_SECONDS
    state = _Site(site, getter, settings, spacing)
    if not state.domain:
        return []
    config = SiteConfig(
        site_key=str(site.get("site_key") or state.domain),
        display_name=state.domain,
        adapter_key="html_page",
    )
    patterns = _search_patterns(state, site)
    learned_pattern: tuple[str, str] | None = None
    pages: list[dict[str, Any]] = []
    auto_urls: list[str] = []
    customer_id = int(customer.id)

    for info in cand.choose_products(products)[:limit] if products else []:
        if not state.time_left():
            break
        product = index.products.get(int(info.id))
        if product is None:
            continue
        tokens = [query for _kind, query in discovery._identity_queries(product)]  # noqa: SLF001
        tokens = [token for token in tokens if token][:QUERIES_PER_PRODUCT]
        if not tokens:
            continue
        found: list[tuple[str, str, str | None]] = []  # (url, found_by, pattern)
        order = ([learned_pattern] if learned_pattern else []) + [
            item for item in patterns if item != learned_pattern
        ]
        for pattern, how in order:
            for token in tokens:
                search_url = pattern.replace("{query}", quote(token, safe=""))
                body = state.body(search_url)
                if body and looks_client_rendered(body):
                    rendered = state.render(search_url)
                    body = rendered.body if rendered is not None and rendered.body else body
                links = discovery._urls_from_document(config, body, search_url, token) if body else []  # noqa: SLF001
                for link in links:
                    if state.same_site(link):
                        found.append((link, f"search:{how}", pattern))
            if found:
                break
        recorded = _process(state, config, index, info, product, found, pages, auto_urls,
                            customer_id)
        if recorded and learned_pattern is None:
            hit = next((page for page in reversed(pages)
                        if page.get("outcome") == AUTO_LINK
                        and page.get("product_id") == int(info.id)), None)
            pattern = hit.get("_pattern") if hit else None
            learned_pattern = next((item for item in patterns if item[0] == pattern), None)
        if not recorded:
            forms = [form for token in tokens for form in _token_forms(token)]
            sitemap_found: list[tuple[str, str, str | None]] = []
            for loc in state.sitemap():
                lowered = loc.lower()
                if any(form in lowered for form in forms):
                    sitemap_found.append((loc, "sitemap", None))
                if len(sitemap_found) >= PAGES_PER_PRODUCT:
                    break
            _process(state, config, index, info, product, sitemap_found, pages, auto_urls,
                     customer_id)
    for page in pages:
        page.pop("_pattern", None)

    learned: dict[str, Any] = {}
    if learned_pattern is not None:
        site["search_pattern"] = {"value": learned_pattern[0], "how": learned_pattern[1]}
        if learned_pattern[1] != "stored":
            learned["search_url_pattern"] = learned_pattern[0]
    if len(auto_urls) >= 2:
        learned.update(discovery._derived_patterns(auto_urls))  # noqa: SLF001
    if learned:
        site["learned"] = learned
    return pages


def make_page_finder(
    *,
    index_loader: Callable[[Any, str], CatalogueIndex] = CatalogueIndex.load,
    limit: int = PRODUCTS_PER_SITE,
) -> Callable[..., list[dict[str, Any]]]:
    """The ``find_pages`` callback for ``preview.run_preview``; one catalogue per run."""
    indexes: dict[str, CatalogueIndex] = {}

    def find_pages(session: Any, customer: Any, site: dict[str, Any], entry: dict[str, Any],
                   getter: Any, settings: Any) -> list[dict[str, Any]]:
        tenant_id = str(customer.tenant_id)
        if tenant_id not in indexes:
            indexes[tenant_id] = index_loader(session, tenant_id)
        products = cand.read_context(session, customer).products
        return find_product_pages(session, customer, site, entry, getter, settings,
                                  index=indexes[tenant_id], products=products, limit=limit)

    return find_pages
