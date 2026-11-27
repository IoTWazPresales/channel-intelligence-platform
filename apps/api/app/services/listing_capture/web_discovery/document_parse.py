"""HTML and URL helpers for product-page discovery.

selectolax (MIT, lexbor) reads links and search forms. courlan (Apache-2.0) and
w3lib (BSD-3-Clause) clean URLs. Sitemaps are read in ``sitemaps``.

Nothing here names a site, a customer or a country, and nothing fetches.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from courlan import clean_url
from selectolax.lexbor import LexborHTMLParser
from w3lib.url import canonicalize_url

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
