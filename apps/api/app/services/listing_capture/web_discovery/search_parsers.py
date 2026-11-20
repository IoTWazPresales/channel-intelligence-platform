"""Parsers for the free web-search providers (stdlib ``html.parser`` and ``json`` only).

Pure functions: a response body in, a ``ParsedPage`` out. No network, no clock. The selectors for
the DuckDuckGo pages are community-observed, not official, so every parser fails soft:

- ``blocked``: the engine refused us (HTTP 202, or a challenge page). Never cached.
- ``empty``: the engine answered and said there are no results. Safe to cache.
- ``ok``: at least one organic result.
- ``unrecognised``: the page has neither results nor a "no results" message (markup drift).
  The caller treats it as a provider failure and moves on; it is never cached as "empty".

Redirect links of both DuckDuckGo providers (``//duckduckgo.com/l/?uddg=<target>&rut=...``) are
unwrapped to the target. Ads are skipped.
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


# --------------------------------------------------------------------------- links


def _is_ddg_host(host: str) -> bool:
    return host == _DDG_HOST or host.endswith("." + _DDG_HOST)


def is_ad_href(href: str) -> bool:
    """A DuckDuckGo ad click-tracker (``duckduckgo.com/y.js``)."""
    try:
        parts = urlsplit((href or "").strip())
        return _is_ddg_host((parts.hostname or "").lower()) and parts.path.rstrip("/") == "/y.js"
    except ValueError:
        return False


def unwrap_result_href(href: str | None) -> str | None:
    """The target URL of a result link, or None when it is not a usable ``http(s)`` link.

    A DuckDuckGo redirect (path ``/l/``, scheme-relative or relative) yields the ``uddg`` value.
    Any other link is used as is. Ads and links without a host return None.
    """
    text = (href or "").strip()
    if not text or is_ad_href(text):
        return None
    try:
        parts = urlsplit(text)
        host = (parts.hostname or "").lower()
        if parts.path.rstrip("/") == "/l" and (not host or _is_ddg_host(host)):
            targets = parse_qs(parts.query).get("uddg")
            if not targets:
                return None
            text = targets[0].strip()
        if text.startswith("//"):
            text = "https:" + text
        parts = urlsplit(text)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            return None
        if parts.username is not None or parts.password is not None:
            return None
        # Validate the port too: malformed URLs are discarded, never a parser exception.
        _ = parts.port
    except ValueError:
        return None
    return None if is_ad_href(text) else text


# --------------------------------------------------------------------------- block detection


def detect_block(status: int, body: str) -> str | None:
    """The reason a DuckDuckGo response is a block, or None. HTTP 202 or a challenge page."""
    if int(status or 0) == 202:
        return REASON_HTTP_202
    lowered = (body or "").lower()
    if any(marker in lowered for marker in BLOCK_MARKERS):
        return REASON_ANOMALY_PAGE
    return None


# --------------------------------------------------------------------------- html walking


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
    """Text of one element, ended by the matching close tag of the same name."""

    def __init__(self, tag: str) -> None:
        self.tag = tag
        self.depth = 1
        self.parts: list[str] = []

    def text(self) -> str:
        return " ".join("".join(self.parts).split())


class _Block:
    def __init__(self) -> None:
        self.depth = 1
        self.ad = False
        self.href: str | None = None
        self.title = ""
        self.snippet = ""
        self.title_scope: _Scope | None = None
        self.snippet_scope: _Scope | None = None
        self.link_found = False


class _DdgHtmlParser(HTMLParser):
    """A ``div.result`` block: its ``a.result__a`` link and its ``.result__snippet`` text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[_Block] = []
        self._block: _Block | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = _classes(attrs)
        block = self._block
        if block is None:
            if tag == "div" and "result" in classes:
                block = _Block()
                block.ad = "result--ad" in classes
                self._block = block
            return
        if tag == "div":
            block.depth += 1
            if "result--ad" in classes:
                block.ad = True
        if tag == "a" and "result__a" in classes and not block.link_found:
            block.link_found = True
            block.href = _attr(attrs, "href")
            block.title_scope = _Scope("a")
        elif "result__snippet" in classes and block.snippet_scope is None and not block.snippet:
            block.snippet_scope = _Scope(tag)
        else:
            for scope in (block.title_scope, block.snippet_scope):
                if scope is not None and tag == scope.tag:
                    scope.depth += 1

    def handle_endtag(self, tag: str) -> None:
        block = self._block
        if block is None:
            return
        for name in ("title_scope", "snippet_scope"):
            scope: _Scope | None = getattr(block, name)
            if scope is not None and tag == scope.tag:
                scope.depth -= 1
                if scope.depth == 0:
                    if name == "title_scope":
                        block.title = scope.text()
                    else:
                        block.snippet = scope.text()
                    setattr(block, name, None)
        if tag == "div":
            block.depth -= 1
            if block.depth == 0:
                self.blocks.append(block)
                self._block = None

    def handle_data(self, data: str) -> None:
        block = self._block
        if block is None:
            return
        for scope in (block.title_scope, block.snippet_scope):
            if scope is not None:
                scope.parts.append(data)

    def close(self) -> None:
        super().close()
        if self._block is not None:  # unterminated markup: keep what was read
            self.blocks.append(self._block)
            self._block = None


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
    except Exception:  # noqa: BLE001 - html.parser can raise on very broken input
        return body or ""
    return " ".join(" ".join(parser.parts).split())


def _page_from_hits(hits: list[ParsedHit], body: str, *, saw_markup: bool) -> ParsedPage:
    if hits:
        return ParsedPage(PARSED_OK, hits)
    if saw_markup or _NO_RESULTS.search(_visible_text(body)):
        # Result blocks existed but every one was an ad or had no usable link, or the engine said
        # there is nothing to show.
        return ParsedPage(PARSED_EMPTY, [], REASON_NO_RESULTS)
    return ParsedPage(PARSED_UNRECOGNISED, [], REASON_UNRECOGNISED)


# --------------------------------------------------------------------------- providers


def parse_ddg_html(body: str, status: int = 200) -> ParsedPage:
    """DuckDuckGo HTML (``html.duckduckgo.com/html/``)."""
    reason = detect_block(status, body)
    if reason:
        return ParsedPage(PARSED_BLOCKED, [], reason)
    parser = _DdgHtmlParser()
    try:
        parser.feed(body or "")
        parser.close()
    except Exception:  # noqa: BLE001
        return ParsedPage(PARSED_UNRECOGNISED, [], REASON_UNRECOGNISED)
    hits: list[ParsedHit] = []
    seen: set[str] = set()
    for block in parser.blocks:
        if block.ad or not block.link_found:
            continue
        url = unwrap_result_href(block.href)
        if url is None or url in seen:
            continue
        seen.add(url)
        hits.append(ParsedHit(url=url, title=block.title, snippet=block.snippet))
    return _page_from_hits(hits, body, saw_markup=bool(parser.blocks))


class _DdgLiteParser(HTMLParser):
    """``a.result-link`` anchors; the ``td.result-snippet`` after each one is its snippet."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        # [href, title, snippet] per anchor, in document order.
        self.rows: list[list[str | None]] = []
        self._title_scope: _Scope | None = None
        self._snippet_scope: _Scope | None = None
        self._snippet_taken = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = _classes(attrs)
        if tag == "a" and "result-link" in classes:
            self.rows.append([_attr(attrs, "href"), "", ""])
            self._title_scope = _Scope("a")
            self._snippet_taken = False
            return
        if "result-snippet" in classes and self.rows and not self._snippet_taken:
            self._snippet_scope = _Scope(tag)
            self._snippet_taken = True
            return
        for scope in (self._title_scope, self._snippet_scope):
            if scope is not None and tag == scope.tag:
                scope.depth += 1

    def handle_endtag(self, tag: str) -> None:
        for name, index in (("_title_scope", 1), ("_snippet_scope", 2)):
            scope: _Scope | None = getattr(self, name)
            if scope is not None and tag == scope.tag:
                scope.depth -= 1
                if scope.depth == 0:
                    self.rows[-1][index] = scope.text()
                    setattr(self, name, None)

    def handle_data(self, data: str) -> None:
        for scope in (self._title_scope, self._snippet_scope):
            if scope is not None:
                scope.parts.append(data)


def parse_ddg_lite(body: str, status: int = 200) -> ParsedPage:
    """DuckDuckGo Lite (``lite.duckduckgo.com/lite/``)."""
    reason = detect_block(status, body)
    if reason:
        return ParsedPage(PARSED_BLOCKED, [], reason)
    parser = _DdgLiteParser()
    try:
        parser.feed(body or "")
        parser.close()
    except Exception:  # noqa: BLE001
        return ParsedPage(PARSED_UNRECOGNISED, [], REASON_UNRECOGNISED)
    hits: list[ParsedHit] = []
    seen: set[str] = set()
    for href, title, snippet in parser.rows:
        url = unwrap_result_href(href)
        if url is None or url in seen:
            continue
        seen.add(url)
        hits.append(ParsedHit(url=url, title=title or "", snippet=snippet or ""))
    return _page_from_hits(hits, body, saw_markup=bool(parser.rows))


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
