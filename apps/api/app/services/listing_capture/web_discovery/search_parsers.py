"""SearXNG JSON/HTML parsing and shared search-result values.

DuckDuckGo result parsing belongs to ddgs. These pure functions retain the tenant-selected
SearXNG seam, including challenge detection and fail-soft handling of unfamiliar markup.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, urlsplit

PARSED_OK = "ok"
PARSED_EMPTY = "empty"
PARSED_BLOCKED = "blocked"
PARSED_UNRECOGNISED = "unrecognised"

REASON_HTTP_202 = "http_202"
REASON_ANOMALY_PAGE = "anomaly_page"
REASON_NO_RESULTS = "no_results"
REASON_UNRECOGNISED = "unrecognised_markup"

BLOCK_MARKERS = ("anomaly-modal", "challenge-form", "anomaly.js")
_NO_RESULTS = re.compile(
    r"no\s+results|did\s+not\s+find\s+any\s+results|didn't\s+find\s+any\s+results", re.IGNORECASE
)
_DDG_HOST = "duckduckgo.com"


@dataclass(frozen=True)
class ParsedHit:
    url: str
    title: str = ""
    snippet: str = ""


@dataclass
class ParsedPage:
    status: str
    hits: list[ParsedHit] = field(default_factory=list)
    reason: str | None = None


def _is_ddg_host(host: str) -> bool:
    return host == _DDG_HOST or host.endswith("." + _DDG_HOST)


def is_ad_href(href: str) -> bool:
    """A DuckDuckGo ad click-tracker, also possible in aggregated SearXNG results."""
    try:
        parts = urlsplit((href or "").strip())
        return _is_ddg_host((parts.hostname or "").lower()) and parts.path.rstrip("/") == "/y.js"
    except ValueError:
        return False


def unwrap_result_href(href: str | None) -> str | None:
    """Validate a result URL and unwrap aggregated DuckDuckGo redirect links."""
    text_value = (href or "").strip()
    if not text_value or is_ad_href(text_value):
        return None
    try:
        parts = urlsplit(text_value)
        host = (parts.hostname or "").lower()
        if parts.path.rstrip("/") == "/l" and (not host or _is_ddg_host(host)):
            targets = parse_qs(parts.query).get("uddg")
            if not targets:
                return None
            text_value = targets[0].strip()
        if text_value.startswith("//"):
            text_value = "https:" + text_value
        parts = urlsplit(text_value)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            return None
        if parts.username is not None or parts.password is not None:
            return None
        _ = parts.port
    except ValueError:
        return None
    return None if is_ad_href(text_value) else text_value


def detect_block(status: int, body: str) -> str | None:
    """Recognise a challenge before treating a SearXNG answer as empty."""
    if int(status or 0) == 202:
        return REASON_HTTP_202
    lowered = (body or "").lower()
    if any(marker in lowered for marker in BLOCK_MARKERS):
        return REASON_ANOMALY_PAGE
    return None


def _classes(attrs: list[tuple[str, str | None]]) -> set[str]:
    for name, value in attrs:
        if name == "class" and value:
            return set(value.split())
    return set()


def _attr(attrs: list[tuple[str, str | None]], key: str) -> str | None:
    for name, value in attrs:
        if name == key:
            return value
    return None


class _Scope:
    def __init__(self, tag: str) -> None:
        self.tag = tag
        self.parts: list[str] = []

    def text(self) -> str:
        return " ".join("".join(self.parts).split())


class _TextOnly(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style"):
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def _visible_text(body: str) -> str:
    parser = _TextOnly()
    try:
        parser.feed(body or "")
        parser.close()
    except Exception:  # noqa: BLE001
        return body or ""
    return " ".join(" ".join(parser.parts).split())


def _page_from_hits(hits: list[ParsedHit], body: str, *, saw_markup: bool) -> ParsedPage:
    if hits:
        return ParsedPage(PARSED_OK, hits)
    if saw_markup or _NO_RESULTS.search(_visible_text(body)):
        return ParsedPage(PARSED_EMPTY, [], REASON_NO_RESULTS)
    return ParsedPage(PARSED_UNRECOGNISED, [], REASON_UNRECOGNISED)


class _SearxngHtmlParser(HTMLParser):
    """``article.result``: the link in its ``h3`` and the ``p.content`` snippet."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.articles: list[dict[str, Any]] = []
        self._current: dict[str, Any] | None = None
        self._h3 = 0
        self._title_scope: _Scope | None = None
        self._snippet_scope: _Scope | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = _classes(attrs)
        if tag == "article" and "result" in classes:
            self._current = {"href": None, "title": "", "snippet": ""}
            self.articles.append(self._current)
            return
        current = self._current
        if current is None:
            return
        if tag == "h3":
            self._h3 += 1
        elif tag == "a" and self._h3 and current["href"] is None:
            current["href"] = _attr(attrs, "href")
            self._title_scope = _Scope("a")
        elif tag == "p" and "content" in classes and not current["snippet"]:
            self._snippet_scope = _Scope("p")

    def handle_endtag(self, tag: str) -> None:
        current = self._current
        if current is None:
            return
        if tag == "article":
            self._current = None
            self._h3 = 0
            self._title_scope = self._snippet_scope = None
        elif tag == "h3" and self._h3:
            self._h3 -= 1
        elif tag == "a" and self._title_scope is not None:
            current["title"] = self._title_scope.text()
            self._title_scope = None
        elif tag == "p" and self._snippet_scope is not None:
            current["snippet"] = self._snippet_scope.text()
            self._snippet_scope = None

    def handle_data(self, data: str) -> None:
        for scope in (self._title_scope, self._snippet_scope):
            if scope is not None:
                scope.parts.append(data)


def parse_searxng_json(body: str) -> ParsedPage | None:
    """A SearXNG ``format=json`` answer, or None when the body is not that JSON."""
    try:
        data = json.loads(body)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        return None
    hits: list[ParsedHit] = []
    seen: set[str] = set()
    for item in data["results"]:
        if not isinstance(item, dict):
            continue
        url = unwrap_result_href(str(item.get("url") or ""))
        if url is None or url in seen:
            continue
        seen.add(url)
        hits.append(
            ParsedHit(
                url=url,
                title=" ".join(str(item.get("title") or "").split()),
                snippet=" ".join(str(item.get("content") or "").split()),
            )
        )
    if hits:
        return ParsedPage(PARSED_OK, hits)
    return ParsedPage(PARSED_EMPTY, [], REASON_NO_RESULTS)


def parse_searxng(body: str, status: int = 200) -> ParsedPage:
    """SearXNG: JSON when the instance serves it, otherwise the HTML result list."""
    reason = detect_block(status, body)
    if reason:
        return ParsedPage(PARSED_BLOCKED, [], reason)
    from_json = parse_searxng_json(body)
    if from_json is not None:
        return from_json
    parser = _SearxngHtmlParser()
    try:
        parser.feed(body or "")
        parser.close()
    except Exception:  # noqa: BLE001
        return ParsedPage(PARSED_UNRECOGNISED, [], REASON_UNRECOGNISED)
    hits: list[ParsedHit] = []
    seen: set[str] = set()
    for article in parser.articles:
        url = unwrap_result_href(article["href"])
        if url is None or url in seen:
            continue
        seen.add(url)
        hits.append(ParsedHit(url=url, title=article["title"], snippet=article["snippet"]))
    return _page_from_hits(hits, body, saw_markup=bool(parser.articles))
