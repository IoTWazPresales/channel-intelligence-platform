"""Sitemap pages for product-page discovery, read with ultimate-sitemap-parser.

ultimate-sitemap-parser (GPL-3.0-or-later) parses XML, plain-text and index sitemaps. It
never fetches by itself: every request goes through the caller's ``fetch``, which keeps
robots and the site's pacing. Nothing here names a site, a customer or a country.
"""

from __future__ import annotations

from collections.abc import Callable

from usp.exceptions import SitemapException
from usp.fetch_parse import SitemapFetcher
from usp.web_client.abstract_client import (
    AbstractWebClient,
    AbstractWebClientResponse,
    AbstractWebClientSuccessResponse,
    WebClientErrorResponse,
)

Fetch = Callable[[str], tuple[int, str]]

# A sitemap larger than this is ignored. A bound on input size, not a tenant setting.
MAX_SITEMAP_CHARS = 5_000_000


class _Response(AbstractWebClientSuccessResponse):
    def __init__(self, url: str, body: str) -> None:
        self._url = url
        self._body = body

    def status_code(self) -> int:
        return 200

    def status_message(self) -> str:
        return "OK"

    def header(self, case_insensitive_name: str) -> str | None:
        return None

    def raw_data(self) -> bytes:
        return self._body.encode("utf-8")

    def url(self) -> str:
        return self._url


class _FetchClient(AbstractWebClient):
    """Hands every sitemap request to ``fetch``. Failures are final: the gate decides retries."""

    def __init__(self, fetch: Fetch) -> None:
        self._fetch = fetch

    def set_max_response_data_length(self, max_response_data_length: int | None) -> None:
        return None

    def get(self, url: str) -> AbstractWebClientResponse:
        try:
            status, body = self._fetch(url)
        except Exception as exc:  # noqa: BLE001
            return WebClientErrorResponse(f"fetch failed: {exc}", retryable=False)
        if status != 200 or not body:
            return WebClientErrorResponse(f"status {status}", retryable=False)
        if len(body) > MAX_SITEMAP_CHARS:
            return WebClientErrorResponse("sitemap too large", retryable=False)
        return _Response(url, body)


def sitemap_page_urls(roots: list[str], fetch: Fetch, *, max_children: int) -> list[str]:
    """Page URLs from each root sitemap, in order, without duplicates.

    An index is followed one level down, to at most ``max_children`` child sitemaps.
    """
    client = _FetchClient(fetch)

    def children(urls: list[str], level: int, _parents: set[str]) -> list[str]:
        return urls[:max_children] if level == 0 else []

    pages: dict[str, None] = {}
    for root in roots:
        try:
            tree = SitemapFetcher(
                url=root,
                recursion_level=0,
                web_client=client,
                quiet_404=True,
                recurse_list_callback=children,
            ).sitemap()
        except SitemapException:
            continue
        for page in tree.all_pages():
            pages.setdefault(page.url, None)
    return list(pages)
