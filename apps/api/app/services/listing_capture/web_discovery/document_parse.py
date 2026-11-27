"""HTML, URL and sitemap helpers for product-page discovery.

selectolax (MIT, lexbor) reads links and search forms. courlan (Apache-2.0) and
w3lib (BSD-3-Clause) clean URLs. Sitemap XML is read with the standard library:
ultimate-sitemap-parser is GPL-3.0-or-later on every PyPI release, so it is not used.

Nothing here names a site, a customer or a country, and nothing fetches.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from urllib.parse import urlsplit

from courlan import clean_url
from selectolax.lexbor import LexborHTMLParser
from w3lib.url import canonicalize_url

# A sitemap larger than this is ignored. A bound on input size, not a tenant setting.
MAX_SITEMAP_CHARS = 5_000_000
_SEARCH_INPUT_NAMES = frozenset({"q", "query", "search"})
_NAV_TAGS = frozenset({"nav", "header", "footer"})


def search_form(html: str) -> tuple[str, str] | None:
    """The action and input name of the first form with a ``q``, ``query`` or ``search`` input."""
    tree = LexborHTMLParser(html or "")
    for form in tree.css("form"):
        for node in form.css("input"):
            name = (node.attributes.get("name") or "").strip().lower()
            if name in _SEARCH_INPUT_NAMES:
                return (form.attributes.get("action") or "").strip(), name
    return None


def document_links(html: str) -> list[tuple[str, bool]]:
    """``(href, inside nav/header/footer)`` for each anchor that has an href."""
    tree = LexborHTMLParser(html or "")
    links: list[tuple[str, bool]] = []
    for node in tree.css("a"):
        href = (node.attributes.get("href") or "").strip()
        if not href or href.startswith("#"):
            continue
        links.append((href, _inside_navigation(node)))
    return links


def _inside_navigation(node: object) -> bool:
    current = node
    while current is not None:
        tag = (getattr(current, "tag", None) or "").lower()
        if tag in _NAV_TAGS:
            return True
        current = getattr(current, "parent", None)
    return False


def absolute_url(base: str, href: str) -> str | None:
    """Join ``href`` to ``base``, then clean it. A URL the cleaners reject is dropped."""
    from urllib.parse import urljoin

    raw = (href or "").strip()
    if not raw:
        return None
    joined = urljoin(base, raw)
    cleaned = clean_url(joined) or ""
    target = canonicalize_url(cleaned or joined)
    parts = urlsplit(target)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return None
    return target.split("#", 1)[0]


def sitemap_locs(xml_text: str) -> tuple[str, list[str]]:
    """``('index'|'urlset'|'unknown', loc URLs)`` from one sitemap document.

    The caller fetched the bytes (robots and pacing stay outside this function).
    """
    text = xml_text or ""
    if not text.strip() or len(text) > MAX_SITEMAP_CHARS:
        return "unknown", []
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return "unknown", []
    kind_tag = root.tag.rsplit("}", 1)[-1].lower()
    kind = "index" if kind_tag == "sitemapindex" else "urlset" if kind_tag == "urlset" else "unknown"
    locs: list[str] = []
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1].lower() != "loc":
            continue
        value = (element.text or "").strip()
        if value and value not in locs:
            locs.append(value)
    return kind, locs
