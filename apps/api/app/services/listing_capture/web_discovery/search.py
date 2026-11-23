"""Tenant-selected search through ddgs or the existing SearXNG HTTP seam.

One DDGS.text invocation is one guarded call. ddgs owns its internal requests and browser
impersonation; this adapter uses only its supported constructor and text options. The backend
is explicitly DuckDuckGo, so ddgs cannot silently fan out to other search engines.

All ddgs exceptions record a pause and return an unavailable attempt. Some ddgs failures hide
the underlying HTTP status; those pauses use status 0 rather than inventing a 403 or 429.
Search failure never fails Preview or writes product/link data.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import urlencode, urlsplit

from app.services import tenant_settings as ts
from app.services.listing_capture.observation import SITE_PAUSE_HTTP_STATUSES
from app.services.listing_capture.site_fetch import STOP_PAUSED
from app.services.listing_capture.site_pause import MEMORY_HOURS, pause_site
from app.services.listing_capture.web_discovery.cache import sha256_hex
from app.services.listing_capture.web_discovery.polite import REFUSED_ROBOTS
from app.services.listing_capture.web_discovery.scoring import normalize_host
from app.services.listing_capture.web_discovery.search_parsers import (
    PARSED_BLOCKED,
    PARSED_EMPTY,
    PARSED_OK,
    ParsedHit,
    ParsedPage,
    parse_searxng,
    unwrap_result_href,
)

PROVIDER_DDG_HTML = "ddg_html"
PROVIDER_DDG_LITE = "ddg_lite"
PROVIDER_SEARXNG = "searxng"
# ddgs "auto": the library's own choice of free, keyless engines (no API key).
PROVIDER_DDGS_AUTO = "ddgs_auto"
PROVIDERS = (PROVIDER_DDG_HTML, PROVIDER_DDG_LITE, PROVIDER_SEARXNG, PROVIDER_DDGS_AUTO)
_DDGS_BACKENDS = {PROVIDER_DDG_HTML: "duckduckgo", PROVIDER_DDGS_AUTO: "auto"}

# Protocol endpoint, not a tenant default. ddgs 9.16.1 POSTs to this HTML endpoint.
DDG_HTML_URL = "https://html.duckduckgo.com/html/"
SEARCH_ENGINE_HOSTS = frozenset(
    {"duckduckgo.com", "html.duckduckgo.com", "lite.duckduckgo.com", "links.duckduckgo.com"}
)
MAX_RESULTS_PER_QUERY = ts.MAX_SEARCH_RESULTS
_CACHE_ADAPTER = "ddgs-9.16.1"

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
    hits: list[ParsedHit],
    *,
    extra_engine_hosts: frozenset[str] = frozenset(),
    limit: int = MAX_RESULTS_PER_QUERY,
) -> list[SearchResult]:
    """Normalise hosts, exclude search engines, de-duplicate and rank organic results."""
    results: list[SearchResult] = []
    seen: set[str] = set()
    for hit in hits:
        url = unwrap_result_href(hit.url)
        if url is None or url in seen:
            continue
        try:
            host = normalize_host(urlsplit(url).hostname or "")
        except ValueError:
            continue
        if not host or _is_engine_host(host, extra_engine_hosts):
            continue
        seen.add(url)
        results.append(SearchResult(url, host, hit.title, hit.snippet, len(results) + 1))
        if len(results) >= min(limit, MAX_RESULTS_PER_QUERY):
            break
    return results


def _configuration(
    provider: str, options: dict[str, Any], searxng_url: str | None
) -> dict[str, Any]:
    return {
        "adapter": _CACHE_ADAPTER if provider == PROVIDER_DDG_HTML else (f"{_CACHE_ADAPTER}:auto" if provider == PROVIDER_DDGS_AUTO else PROVIDER_SEARXNG),
        "options": options,
        "searxng_url": searxng_url if provider == PROVIDER_SEARXNG else None,
    }


def _cache_read(
    cache: Any,
    provider: str,
    query: str,
    configuration: dict[str, Any],
    extra_hosts: frozenset[str],
    limit: int,
) -> list[SearchResult] | None:
    if cache is None:
        return None
    try:
        record = cache.get_outcome(provider, query)
        if not isinstance(record, dict) or record.get("status") not in (STATUS_OK, STATUS_EMPTY):
            return None
        # Reject old hand-parsed entries and answers for different tenant search options.
        if record.get("configuration") != configuration:
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
        results = build_results(hits, extra_engine_hosts=extra_hosts, limit=limit)
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
    configuration: dict[str, Any],
) -> None:
    if cache is None:
        return
    try:
        cache.put_outcome(
            provider,
            query,
            {
                "status": STATUS_OK if results else STATUS_EMPTY,
                "results": [asdict(result) for result in results],
                "configuration": configuration,
            },
        )
    except Exception:  # noqa: BLE001
        return


def request_url(provider: str, query: str, searxng_url: str | None) -> str | None:
    """The guarded endpoint; ddgs sends its query itself using POST."""
    if provider in _DDGS_BACKENDS:
        return DDG_HTML_URL
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
    """A SearXNG challenge or unfamiliar page is not a usable HTTP-cache entry."""
    try:
        getter.cache.store.delete(f"wd:http:{sha256_hex(url)}")
    except Exception:  # noqa: BLE001
        return


def _pause_search_host(
    getter: Any,
    gate_key: str,
    http_status: int,
    previous: dict[str, Any] | None,
) -> None:
    policy = getter.policy
    gate = getter.gate(gate_key)
    if gate.stopped == STOP_PAUSED:
        return
    # A robots 200 may have cleared expired history before a library call failed.
    if previous and not policy.store.get(gate_key):
        hours = int(previous.get("hours") or 0)
        policy.store.set(gate_key, previous, ttl_seconds=(hours + MEMORY_HOURS) * 3600)
    record = pause_site(policy.store, gate_key, http_status=http_status, now=policy.now())
    gate.stopped = STOP_PAUSED
    gate.refused_status = http_status
    gate.pause_record = record
    gate.paused_until = datetime.fromisoformat(str(record["until"]))


def _refusal(
    provider: str, status: int, refused: str | None
) -> dict[str, Any] | None:
    if refused == REFUSED_ROBOTS:
        return _attempt(provider, ATTEMPT_ROBOTS, None, "robots_disallowed")
    if refused == STOP_PAUSED:
        if status in SITE_PAUSE_HTTP_STATUSES:
            return _attempt(provider, ATTEMPT_BLOCKED, status, f"http_{status}")
        return _attempt(provider, ATTEMPT_PAUSED, None, "site_paused")
    if refused:
        return _attempt(provider, ATTEMPT_ERROR, status or None, refused)
    return None


def _exception_status(exc: Exception) -> int:
    """Use exposed status information only; never parse or publish diagnostic messages."""
    if type(exc).__name__ == "RatelimitException":
        return 429
    response = getattr(exc, "response", None)
    for code in (
        getattr(exc, "status_code", None),
        getattr(exc, "code", None),
        getattr(response, "status_code", None),
    ):
        if isinstance(code, int) and not isinstance(code, bool) and 100 <= code <= 599:
            return code
    return 0


def _ddgs_page(query: str, options: dict[str, Any], backend: str = "duckduckgo") -> tuple[int, ParsedPage]:
    # Import and construct inside the guarded operation: even a missing/broken dependency
    # follows the fail-soft pause path, and a robots refusal constructs no client.
    from ddgs import DDGS

    arguments: dict[str, Any] = {
        "backend": backend,
        "max_results": options["max_results"],
    }
    if "region" in options:
        arguments["region"] = options["region"]
    import ddgs as ddgs_module

    no_results = getattr(ddgs_module, "DDGSException", None)
    if no_results is None:
        try:
            from ddgs.exceptions import DDGSException as no_results
        except ImportError:
            no_results = None
    try:
        with DDGS(timeout=options["timeout_seconds"]) as client:
            rows = client.text(query, **arguments)
    except Exception as exc:  # noqa: BLE001 - re-raised unless it is the plain "no results" class
        # ddgs raises the base class when every engine answered with no results. That is an
        # empty search, not a block: it must not pause the search host. Subclasses (rate limit,
        # timeout) still raise and take the pause path.
        if no_results is None or type(exc) is not no_results:
            raise
        return 200, ParsedPage(PARSED_EMPTY, [], "no_results")
    if not isinstance(rows, list):
        raise ValueError("Unexpected ddgs result type")

    hits: list[ParsedHit] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Unexpected ddgs result item")
        href = row.get("href")
        if not isinstance(href, str):
            raise ValueError("Missing ddgs result URL")
        url = unwrap_result_href(href)
        if url is not None:
            hits.append(
                ParsedHit(
                    url=url,
                    title=" ".join(str(row.get("title") or "").split()),
                    snippet=" ".join(str(row.get("body") or "").split()),
                )
            )
    if rows and not hits:
        raise ValueError("No usable ddgs result URLs")
    status = PARSED_OK if hits else PARSED_EMPTY
    return 200, ParsedPage(status, hits, None if hits else "no_results")


def _run_provider(
    provider: str,
    query: str,
    getter: Any,
    searxng_url: str | None,
    options: dict[str, Any],
) -> tuple[dict[str, Any], ParsedPage | None]:
    url = request_url(provider, query, searxng_url)
    if url is None:
        return _attempt(provider, ATTEMPT_ERROR, None, "searxng_url_not_set"), None
    gate_key = f"search:{urlsplit(url).hostname}"
    if getter.paused(gate_key):
        return _attempt(provider, ATTEMPT_PAUSED, None, "site_paused"), None
    try:
        previous = getter.policy.store.get(gate_key)
    except Exception:  # noqa: BLE001
        previous = None

    spacing = options["min_interval_seconds"]
    if provider in _DDGS_BACKENDS:
        try:
            called = getter.guarded_call(
                url,
                lambda: _ddgs_page(query, options, _DDGS_BACKENDS[provider]),
                gate_key=gate_key,
                spacing=spacing,
            )
        except Exception as exc:  # noqa: BLE001 - every ddgs error pauses and fails soft
            status = _exception_status(exc)
            reason = f"ddgs_{type(exc).__name__}"
            try:
                _pause_search_host(getter, gate_key, status, previous)
            except Exception:  # noqa: BLE001 - a broken pause store must not fail Preview
                reason = f"{reason}_pause_unavailable"
            attempt_status = (
                ATTEMPT_BLOCKED if status in {202, 403, 429} else ATTEMPT_ERROR
            )
            return _attempt(provider, attempt_status, status or None, reason), None
        refused = _refusal(provider, called.status, called.refused)
        if refused is not None:
            return refused, None
        return _attempt(provider, called.value.status, None, called.value.reason), called.value

    fetched = getter.get(url, gate_key=gate_key, spacing=spacing)
    status = int(fetched.status or 0)
    refused = _refusal(provider, status, fetched.refused)
    if refused is not None:
        return refused, None
    if status in SITE_PAUSE_HTTP_STATUSES:
        return _attempt(provider, ATTEMPT_BLOCKED, status, f"http_{status}"), None
    parsed = parse_searxng(fetched.body, status)
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
    search_options: dict[str, Any] | None = None,
) -> SearchOutcome:
    """Try tenant providers in order; failure leaves other candidate sources usable."""
    if not providers:
        return SearchOutcome(status=STATUS_OFF)
    text_value = (query or "").strip()
    if not text_value:
        return SearchOutcome(status=STATUS_EMPTY)
    try:
        options = ts.SETTING_VALIDATORS[ts.KEY_DISCOVERY_SEARCH_OPTIONS](search_options)
    except (TypeError, ValueError):
        reason = "search_options_not_set" if search_options is None else "search_options_invalid"
        return SearchOutcome(
            status=STATUS_UNAVAILABLE,
            attempts=[_attempt(provider, ATTEMPT_ERROR, None, reason) for provider in providers],
        )
    try:
        extra_hosts = frozenset(
            {normalize_host(urlsplit(searxng_url).hostname or "")} if searxng_url else set()
        ) - {""}
    except ValueError:
        extra_hosts = frozenset()

    attempts: list[dict[str, Any]] = []
    for provider in providers:
        if provider == PROVIDER_DDG_LITE:
            attempts.append(_attempt(provider, ATTEMPT_ERROR, None, "ddgs_lite_unsupported"))
            continue
        if provider not in (*_DDGS_BACKENDS, PROVIDER_SEARXNG):
            attempts.append(_attempt(provider, ATTEMPT_ERROR, None, "unknown_provider"))
            continue
        configuration = _configuration(provider, options, searxng_url)
        cached = _cache_read(
            cache, provider, text_value, configuration, extra_hosts, options["max_results"]
        )
        if cached is not None:
            status = STATUS_OK if cached else STATUS_EMPTY
            attempts.append(_attempt(provider, status, None, "cache"))
            return SearchOutcome(status, provider, cached, attempts)
        try:
            attempt, parsed = _run_provider(
                provider, text_value, getter, searxng_url, options
            )
            if parsed is None:
                attempts.append(attempt)
                continue
            results = build_results(
                parsed.hits,
                extra_engine_hosts=extra_hosts,
                limit=options["max_results"],
            )
        except Exception as exc:  # noqa: BLE001 - never expose messages or fail Preview
            attempts.append(_attempt(provider, ATTEMPT_ERROR, None, type(exc).__name__))
            continue
        status = STATUS_OK if results else STATUS_EMPTY
        attempt["status"] = status
        attempts.append(attempt)
        _cache_write(cache, provider, text_value, results, configuration)
        return SearchOutcome(status, provider, results, attempts)
    return SearchOutcome(status=STATUS_UNAVAILABLE, attempts=attempts)
