"""Tenant-selected free web search, through S1's polite getter and seven-day cache.

Providers fail soft and fall back in the configured order. Search never writes product data.
A 202 or challenge page pauses the search host using the existing site-pause back-off.
403/429 are handled by PoliteGetter; a refusal is never retried or parsed.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import urlencode, urlsplit

from app.services.listing_capture.observation import SITE_PAUSE_HTTP_STATUSES
from app.services.listing_capture.site_fetch import STOP_PAUSED
from app.services.listing_capture.site_pause import MEMORY_HOURS, pause_site
from app.services.listing_capture.web_discovery.cache import sha256_hex
from app.services.listing_capture.web_discovery.polite import (
    REFUSED_ROBOTS,
    SEARCH_SPACING_SECONDS,
)
from app.services.listing_capture.web_discovery.scoring import normalize_host
from app.services.listing_capture.web_discovery.search_parsers import (
    PARSED_BLOCKED,
    PARSED_EMPTY,
    PARSED_OK,
    ParsedHit,
    ParsedPage,
    parse_ddg_html,
    parse_ddg_lite,
    parse_searxng,
)

PROVIDER_DDG_HTML = "ddg_html"
PROVIDER_DDG_LITE = "ddg_lite"
PROVIDER_SEARXNG = "searxng"
PROVIDERS = (PROVIDER_DDG_HTML, PROVIDER_DDG_LITE, PROVIDER_SEARXNG)

# Protocol endpoints, not tenant defaults. The tenant selects whether and in what order to use them.
DDG_HTML_URL = "https://html.duckduckgo.com/html/"
DDG_LITE_URL = "https://lite.duckduckgo.com/lite/"
SEARCH_ENGINE_HOSTS = frozenset(
    {"duckduckgo.com", "html.duckduckgo.com", "lite.duckduckgo.com", "links.duckduckgo.com"}
)
MAX_RESULTS_PER_QUERY = 10

STATUS_OK = "ok"
STATUS_EMPTY = "empty"
STATUS_UNAVAILABLE = "unavailable"
STATUS_OFF = "off"

ATTEMPT_BLOCKED = "blocked"
ATTEMPT_PAUSED = "paused"
ATTEMPT_ROBOTS = "robots"
ATTEMPT_ERROR = "error"


@dataclass(frozen=True)
class SearchResult:
    url: str
    host: str
    title: str
    snippet: str
    rank: int


@dataclass
class SearchOutcome:
    status: str
    provider: str | None = None
    results: list[SearchResult] = field(default_factory=list)
    attempts: list[dict[str, Any]] = field(default_factory=list)


def _attempt(
    provider: str, status: str, http_status: int | None = None, reason: str | None = None
) -> dict[str, Any]:
    return {"provider": provider, "status": status, "http_status": http_status, "reason": reason}


def _is_engine_host(host: str, extra: frozenset[str]) -> bool:
    return any(
        host == engine or host.endswith("." + engine) for engine in SEARCH_ENGINE_HOSTS | extra
    )


def build_results(
    hits: list[ParsedHit], *, extra_engine_hosts: frozenset[str] = frozenset()
) -> list[SearchResult]:
    """Normalise hosts, exclude search engines, and rank the first ten organic results."""
    results: list[SearchResult] = []
    for hit in hits:
        try:
            parts = urlsplit(hit.url)
            host = normalize_host(parts.hostname or "")
        except ValueError:
            continue
        if parts.scheme not in ("http", "https") or not host:
            continue
        if _is_engine_host(host, extra_engine_hosts):
            continue
        results.append(SearchResult(hit.url, host, hit.title, hit.snippet, len(results) + 1))
        if len(results) >= MAX_RESULTS_PER_QUERY:
            break
    return results


def _cache_read(
    cache: Any,
    provider: str,
    query: str,
    searxng_url: str | None,
    extra_hosts: frozenset[str],
) -> list[SearchResult] | None:
    if cache is None:
        return None
    try:
        record = cache.get_outcome(provider, query)
        if not isinstance(record, dict) or record.get("status") not in (STATUS_OK, STATUS_EMPTY):
            return None
        # The run-state store is shared. Never reuse another tenant's SearXNG instance answer.
        if provider == PROVIDER_SEARXNG and record.get("searxng_url") != searxng_url:
            return None
        items = record.get("results")
        if not isinstance(items, list):
            return None
        hits = [
            ParsedHit(
                url=str(item["url"]),
                title=str(item.get("title") or ""),
                snippet=str(item.get("snippet") or ""),
            )
            for item in items
        ]
        results = build_results(hits, extra_engine_hosts=extra_hosts)
        if record["status"] == STATUS_OK and not results:
            return None
        if record["status"] == STATUS_EMPTY and items:
            return None
        return results
    except Exception:  # noqa: BLE001 - cache failures never fail Preview
        return None


def _cache_write(
    cache: Any,
    provider: str,
    query: str,
    results: list[SearchResult],
    searxng_url: str | None,
) -> None:
    if cache is None:
        return
    record: dict[str, Any] = {
        "status": STATUS_OK if results else STATUS_EMPTY,
        "results": [asdict(result) for result in results],
    }
    if provider == PROVIDER_SEARXNG:
        record["searxng_url"] = searxng_url
    try:
        cache.put_outcome(provider, query, record)
    except Exception:  # noqa: BLE001
        return


def request_url(provider: str, query: str, searxng_url: str | None) -> str | None:
    """Build a provider request, without selecting any default providers or instance."""
    if provider == PROVIDER_DDG_HTML:
        return f"{DDG_HTML_URL}?{urlencode({'q': query})}"
    if provider == PROVIDER_DDG_LITE:
        return f"{DDG_LITE_URL}?{urlencode({'q': query})}"
    if provider != PROVIDER_SEARXNG:
        return None
    base = (searxng_url or "").strip().rstrip("/")
    try:
        parts = urlsplit(base)
        if parts.scheme != "https" or not parts.hostname or parts.query or parts.fragment:
            return None
        if parts.username is not None or parts.password is not None:
            return None
        _ = parts.port
    except ValueError:
        return None
    return f"{base}/search?{urlencode({'q': query, 'format': 'json'})}"


def _forget_cached_response(getter: Any, url: str) -> None:
    """PoliteGetter caches 200s before parsing; a challenge is not a usable HTTP-cache entry."""
    try:
        getter.cache.store.delete(f"wd:http:{sha256_hex(url)}")
    except Exception:  # noqa: BLE001 - a cache eviction never fails Preview
        return


def _pause_search_host(
    getter: Any,
    gate_key: str,
    http_status: int,
    previous: dict[str, Any] | None,
) -> None:
    policy = getter.policy
    # The generic gate clears old pause history on a 200 (including a robots 200).
    # Restore it only when parsing proves that the search response was actually a block.
    if previous and not policy.store.get(gate_key):
        hours = int(previous.get("hours") or 0)
        policy.store.set(gate_key, previous, ttl_seconds=(hours + MEMORY_HOURS) * 3600)
    record = pause_site(policy.store, gate_key, http_status=http_status, now=policy.now())
    gate = getter.gate(gate_key, SEARCH_SPACING_SECONDS)
    gate.stopped = STOP_PAUSED
    gate.refused_status = http_status
    gate.pause_record = record
    gate.paused_until = datetime.fromisoformat(str(record["until"]))


def _parse(provider: str, status: int, body: str) -> ParsedPage:
    if provider == PROVIDER_DDG_HTML:
        return parse_ddg_html(body, status)
    if provider == PROVIDER_DDG_LITE:
        return parse_ddg_lite(body, status)
    return parse_searxng(body, status)


def _run_provider(
    provider: str, query: str, getter: Any, searxng_url: str | None
) -> tuple[dict[str, Any], ParsedPage | None]:
    url = request_url(provider, query, searxng_url)
    if url is None:
        reason = "searxng_url_not_set" if provider == PROVIDER_SEARXNG else "unknown_provider"
        return _attempt(provider, ATTEMPT_ERROR, None, reason), None
    gate_key = f"search:{urlsplit(url).hostname}"
    # Check the gate before the HTTP cache, so cached challenges cannot extend a pause.
    if getter.paused(gate_key):
        return _attempt(provider, ATTEMPT_PAUSED, None, "site_paused"), None
    try:
        previous = getter.policy.store.get(gate_key)
    except Exception:  # noqa: BLE001
        previous = None
    fetched = getter.get(url, gate_key=gate_key, spacing=SEARCH_SPACING_SECONDS)
    status = int(fetched.status or 0)
    if fetched.refused:
        if fetched.refused == REFUSED_ROBOTS:
            return _attempt(provider, ATTEMPT_ROBOTS, None, "robots_disallowed"), None
        if fetched.refused == STOP_PAUSED:
            if status in SITE_PAUSE_HTTP_STATUSES:
                return _attempt(provider, ATTEMPT_BLOCKED, status, f"http_{status}"), None
            return _attempt(provider, ATTEMPT_PAUSED, None, "site_paused"), None
        return _attempt(provider, ATTEMPT_ERROR, status or None, str(fetched.refused)), None
    if status in SITE_PAUSE_HTTP_STATUSES:
        return _attempt(provider, ATTEMPT_BLOCKED, status, f"http_{status}"), None
    parsed = _parse(provider, status, fetched.body)
    if parsed.status == PARSED_BLOCKED:
        _forget_cached_response(getter, url)
        _pause_search_host(getter, gate_key, status, previous)
        return _attempt(provider, ATTEMPT_BLOCKED, status, parsed.reason), None
    if status != 200:
        reason = f"http_{status}" if status else "unreachable"
        return _attempt(provider, ATTEMPT_ERROR, status or None, reason), None
    if parsed.status not in (PARSED_OK, PARSED_EMPTY):
        _forget_cached_response(getter, url)
        return _attempt(provider, ATTEMPT_ERROR, status, parsed.reason), None
    return _attempt(provider, parsed.status, status, parsed.reason), parsed


def web_search(
    query: str,
    *,
    providers: list[str] | tuple[str, ...],
    getter: Any,
    cache: Any | None = None,
    searxng_url: str | None = None,
) -> SearchOutcome:
    """Try the tenant's providers in order; all failures yield search unavailable."""
    if not providers:
        return SearchOutcome(status=STATUS_OFF)
    text = (query or "").strip()
    if not text:
        return SearchOutcome(status=STATUS_EMPTY)
    try:
        extra_hosts = frozenset(
            {normalize_host(urlsplit(searxng_url).hostname or "")} if searxng_url else set()
        ) - {""}
    except ValueError:
        extra_hosts = frozenset()
    attempts: list[dict[str, Any]] = []
    for provider in providers:
        cached = _cache_read(cache, provider, text, searxng_url, extra_hosts)
        if cached is not None:
            status = STATUS_OK if cached else STATUS_EMPTY
            attempts.append(_attempt(provider, status, None, "cache"))
            return SearchOutcome(status, provider, cached, attempts)
        try:
            attempt, parsed = _run_provider(provider, text, getter, searxng_url)
            if parsed is None:
                attempts.append(attempt)
                continue
            results = build_results(parsed.hits, extra_engine_hosts=extra_hosts)
        except Exception as exc:  # noqa: BLE001 - never expose exception messages or fail Preview
            attempts.append(_attempt(provider, ATTEMPT_ERROR, None, type(exc).__name__))
            continue
        status = STATUS_OK if results else STATUS_EMPTY
        attempt["status"] = status
        attempts.append(attempt)
        _cache_write(cache, provider, text, results, searxng_url)
        return SearchOutcome(status, provider, results, attempts)
    return SearchOutcome(status=STATUS_UNAVAILABLE, attempts=attempts)
