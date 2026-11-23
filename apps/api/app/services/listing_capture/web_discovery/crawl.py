"""Crawlee-driven fetching for Discovery V2, under the existing polite gate.

Crawlee for Python (Apache-2.0) owns the request queue, de-duplication, retries,
robots.txt handling (``respect_robots_txt_file``) and the browser crawler. Every byte
it asks for still goes through :class:`~.polite.PoliteGetter`, so the per-site spacing,
the shared 403/429 pause, the robots check and the HTTP cache stay exactly as they are.

- :func:`fetch_pages` uses Crawlee's ``HttpCrawler`` with :class:`GatedHttpClient` as its
  HTTP client: one queue per call, concurrency 1, nothing persisted to disk.
- :func:`render_pages` uses Crawlee's ``PlaywrightCrawler`` (Python Playwright, Apache-2.0)
  for script-built pages. The page's own document is fetched through the polite getter
  and handed to the browser (``route.fulfill``), so the gate and robots decide whether a
  page is read at all. Images, media and fonts are not loaded. No fingerprint
  generator, no proxy, no session rotation and no CAPTCHA handling (D-0063): a block is
  a stop, not a retry.

Nothing here names a site, a domain, a path or a country.
"""

from __future__ import annotations

import asyncio
import importlib.util
import logging
import threading
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from app.services.listing_capture.observation import LISTING_CAPTURE_USER_AGENT

logger = logging.getLogger(__name__)

RENDER_TIMEOUT_SECONDS = 20
MAX_PAGES_PER_CALL = 40
_SKIPPED_RESOURCES = frozenset({"image", "media", "font"})


@dataclass(frozen=True)
class PageResult:
    url: str
    status: int
    body: str
    final_url: str
    refused: str | None = None
    rendered: bool = False


GateKeyFor = Callable[[str], str]


def crawlee_available() -> bool:
    return importlib.util.find_spec("crawlee") is not None


def browser_available() -> bool:
    return crawlee_available() and importlib.util.find_spec("playwright") is not None


_service_lock = threading.Lock()
_service_ready = False


def _prepare_services() -> None:
    """Crawlee keeps queues in memory only; it never writes a storage folder."""
    global _service_ready
    with _service_lock:
        if _service_ready:
            return
        from crawlee import service_locator
        from crawlee.configuration import Configuration
        from crawlee.storage_clients import MemoryStorageClient

        config = Configuration(persist_storage=False, write_metadata=False, purge_on_start=True)
        try:
            service_locator.set_configuration(config)
        except Exception:  # noqa: BLE001 - already set in this process
            config = service_locator.get_configuration()
        try:
            service_locator.set_storage_client(MemoryStorageClient.from_config(config))
        except Exception:  # noqa: BLE001 - already set in this process
            pass
        _service_ready = True


def _run(coro: Any) -> Any:
    """Run a Crawlee coroutine from sync code (Celery task or test), even inside a loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    box: dict[str, Any] = {}

    def target() -> None:
        try:
            box["value"] = asyncio.run(coro)
        except BaseException as exc:  # noqa: BLE001
            box["error"] = exc

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join()
    if "error" in box:
        raise box["error"]
    return box.get("value")


def _make_client(getter: Any, gate_key_for: GateKeyFor, spacing: float | None) -> Any:
    from crawlee._types import HttpHeaders
    from crawlee.http_clients import HttpClient, HttpCrawlingResult

    class _Response:
        def __init__(self, fetched: Any) -> None:
            self._fetched = fetched

        @property
        def http_version(self) -> str:
            return "HTTP/1.1"

        @property
        def status_code(self) -> int:
            return int(self._fetched.status or 0)

        @property
        def headers(self) -> Any:
            return HttpHeaders({"content-type": "text/html; charset=utf-8"})

        def read(self) -> bytes:
            return (self._fetched.body or "").encode("utf-8")

        async def read_stream(self) -> Any:  # pragma: no cover - never streamed
            yield self.read()

    class GatedHttpClient(HttpClient):
        """Crawlee HTTP client whose transport is the polite getter."""

        def __init__(self) -> None:
            super().__init__(persist_cookies_per_session=False)
            self.results: dict[str, Any] = {}

        async def _get(self, url: str) -> Any:
            fetched = await asyncio.to_thread(
                getter.get, url, gate_key=gate_key_for(url), spacing=spacing
            )
            self.results[url] = fetched
            return fetched

        async def crawl(self, request: Any, *, session: Any = None, proxy_info: Any = None,
                        statistics: Any = None) -> Any:
            fetched = await self._get(request.url)
            if statistics is not None:
                statistics.register_status_code(int(fetched.status or 0))
            return HttpCrawlingResult(http_response=_Response(fetched))

        async def send_request(self, url: str, *, method: str = "GET", headers: Any = None,
                               payload: Any = None, session: Any = None,
                               proxy_info: Any = None) -> Any:
            return _Response(await self._get(url))

        def stream(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
            raise NotImplementedError("discovery never streams")

        async def cleanup(self) -> None:
            return None

    return GatedHttpClient()


def _error_codes() -> list[int]:
    # Every status reaches the handler; the gate (not Crawlee) decides about 403/429.
    return list(range(400, 600))


async def _fetch(urls: list[str], getter: Any, gate_key_for: GateKeyFor,
                 spacing: float | None) -> dict[str, PageResult]:
    from crawlee import ConcurrencySettings, Request
    from crawlee.crawlers import HttpCrawler
    from crawlee.storages import RequestQueue

    _prepare_services()
    client = _make_client(getter, gate_key_for, spacing)
    queue = await RequestQueue.open(name=f"wd-{uuid.uuid4().hex}")
    out: dict[str, PageResult] = {}
    crawler = HttpCrawler(
        http_client=client,
        request_manager=queue,
        max_request_retries=1,
        max_requests_per_crawl=len(urls),
        concurrency_settings=ConcurrencySettings(min_concurrency=1, max_concurrency=1,
                                                 desired_concurrency=1),
        respect_robots_txt_file=True,
        ignore_http_error_status_codes=_error_codes(),
        configure_logging=False,
        use_session_pool=False,
    )

    @crawler.router.default_handler
    async def handler(context: Any) -> None:
        url = context.request.unique_key and context.request.url
        fetched = client.results.get(context.request.url)
        if fetched is None:
            return
        out[context.request.user_data.get("wd_url") or url] = PageResult(
            url=context.request.user_data.get("wd_url") or url,
            status=int(fetched.status or 0),
            body=fetched.body or "",
            final_url=fetched.final_url or url,
            refused=fetched.refused,
        )

    requests = [Request.from_url(url, user_data={"wd_url": url}) for url in urls]
    try:
        await crawler.run(requests)
    finally:
        await queue.drop()
    return out


def fetch_pages(urls: Iterable[str], getter: Any, *, gate_key_for: GateKeyFor,
                spacing: float | None = None) -> dict[str, PageResult]:
    """Fetch ``urls`` with Crawlee's HTTP crawler through the polite getter.

    A URL that robots.txt disallows, or that a paused site refuses, is simply absent from
    (or refused in) the result. Order and duplicates are handled by Crawlee's queue.
    """
    wanted = list(dict.fromkeys(url for url in urls if url))[:MAX_PAGES_PER_CALL]
    if not wanted:
        return {}
    if not crawlee_available():
        return _fetch_plain(wanted, getter, gate_key_for, spacing)
    try:
        return _run(_fetch(wanted, getter, gate_key_for, spacing))
    except Exception:  # noqa: BLE001 - never fail a preview because the crawler failed
        logger.exception("crawlee fetch failed; reading pages directly through the gate")
        return _fetch_plain(wanted, getter, gate_key_for, spacing)


def _fetch_plain(urls: list[str], getter: Any, gate_key_for: GateKeyFor,
                 spacing: float | None) -> dict[str, PageResult]:
    out: dict[str, PageResult] = {}
    for url in urls:
        fetched = getter.get(url, gate_key=gate_key_for(url), spacing=spacing)
        out[url] = PageResult(url, int(fetched.status or 0), fetched.body or "",
                              fetched.final_url or url, fetched.refused)
    return out


async def _render(urls: list[str], getter: Any, gate_key_for: GateKeyFor,
                  spacing: float | None) -> dict[str, PageResult]:
    from crawlee import ConcurrencySettings, Request
    from crawlee.crawlers import PlaywrightCrawler
    from crawlee.storages import RequestQueue

    _prepare_services()
    client = _make_client(getter, gate_key_for, spacing)
    queue = await RequestQueue.open(name=f"wd-render-{uuid.uuid4().hex}")
    out: dict[str, PageResult] = {}
    documents: dict[str, Any] = {}
    crawler = PlaywrightCrawler(
        browser_type="chromium",
        headless=True,
        fingerprint_generator=None,
        browser_new_context_options={"user_agent": LISTING_CAPTURE_USER_AGENT},
        http_client=client,
        request_manager=queue,
        max_request_retries=0,
        max_requests_per_crawl=len(urls),
        request_handler_timeout=timedelta(seconds=RENDER_TIMEOUT_SECONDS),
        concurrency_settings=ConcurrencySettings(min_concurrency=1, max_concurrency=1,
                                                 desired_concurrency=1),
        respect_robots_txt_file=True,
        ignore_http_error_status_codes=_error_codes(),
        configure_logging=False,
        use_session_pool=False,
    )

    @crawler.pre_navigation_hook
    async def gate_document(context: Any) -> None:
        target = context.request.url

        async def route(route_obj: Any) -> None:
            request = route_obj.request
            if request.resource_type in _SKIPPED_RESOURCES:
                await route_obj.abort()
                return
            if request.is_navigation_request() and request.url == target:
                fetched = await asyncio.to_thread(
                    getter.get, target, gate_key=gate_key_for(target), spacing=spacing
                )
                documents[target] = fetched
                if fetched.refused or not fetched.body:
                    await route_obj.abort()
                    return
                await route_obj.fulfill(status=int(fetched.status or 200), body=fetched.body,
                                        content_type="text/html; charset=utf-8")
                return
            await route_obj.continue_()

        await context.page.route("**/*", route)

    @crawler.router.default_handler
    async def handler(context: Any) -> None:
        url = context.request.user_data.get("wd_url") or context.request.url
        fetched = documents.get(context.request.url)
        try:
            await context.page.wait_for_load_state("networkidle",
                                                   timeout=RENDER_TIMEOUT_SECONDS * 1000 // 2)
        except Exception:  # noqa: BLE001 - render what loaded
            pass
        html = await context.page.content()
        out[url] = PageResult(url=url, status=int(getattr(fetched, "status", 0) or 0), body=html,
                              final_url=context.page.url or url,
                              refused=getattr(fetched, "refused", None), rendered=True)

    @crawler.failed_request_handler
    async def failed(context: Any, _error: Exception) -> None:
        url = context.request.user_data.get("wd_url") or context.request.url
        fetched = documents.get(context.request.url)
        out.setdefault(url, PageResult(url, int(getattr(fetched, "status", 0) or 0), "", url,
                                       getattr(fetched, "refused", None) or "render_failed",
                                       rendered=True))

    requests = [Request.from_url(url, user_data={"wd_url": url}) for url in urls]
    try:
        await crawler.run(requests)
    finally:
        await queue.drop()
    return out


def render_pages(urls: Iterable[str], getter: Any, *, gate_key_for: GateKeyFor,
                 spacing: float | None = None) -> dict[str, PageResult]:
    """Render script-built pages with Crawlee's Playwright crawler (headless Chromium)."""
    wanted = list(dict.fromkeys(url for url in urls if url))[:MAX_PAGES_PER_CALL]
    if not wanted or not browser_available():
        return {}
    try:
        return _run(_render(wanted, getter, gate_key_for, spacing))
    except Exception:  # noqa: BLE001 - a browser failure is "needs_browser", not a failed run
        logger.exception("crawlee browser render failed")
        return {}
