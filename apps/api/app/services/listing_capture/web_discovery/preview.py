"""Preview: work out what Discover would save, without saving anything.

``run_preview`` runs on the Celery worker. Its first statement is ``SET TRANSACTION READ ONLY``,
so Postgres itself rejects any INSERT, UPDATE or DELETE (``ReadOnlySqlTransaction``). The caller
(the task) ends with ``session.rollback()``. The only writes are operational and live in Redis: the
plan (``wd:preview:<tenant>:<id>``, 24 h), the HTTP, search and robots caches, and the site pause
records (politeness has to persist).

The plan holds the whole result. Apply loads it and writes exactly what the user reviewed; it does
not recompute (see ``apply.py``).
"""

from __future__ import annotations

import inspect
import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol
from urllib.parse import urlsplit

import redis
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.dimensions import DimCustomer
from app.services.listing_capture import discovery, site_pause
from app.services.listing_capture.site_onboarding import SiteOnboardError, normalize_domain
from app.services.listing_capture.web_discovery import candidates as cand
from app.services.listing_capture.web_discovery.scoring import (
    MAX_QUEUED_PER_CUSTOMER,
    OUTCOME_AUTO,
    OUTCOME_DROPPED,
    OUTCOME_MONITORED,
    OUTCOME_QUEUE,
    OUTCOME_REJECTED,
    OUTCOME_USER,
    SOURCE_USER,
    build_evidence,
    decide,
    normalize_host,
    rank_key,
)
from app.services.listing_capture.web_discovery.settings import (
    SCOPE_CUSTOMER,
    SCOPE_DOMAIN,
    SCOPE_REPORTING,
    SCOPE_UNLINKED,
    SCOPES,
    DiscoverySettings,
    load_discovery_settings,
)

PLAN_TTL_SECONDS = 24 * 3600
RUNNING_LOCK_SECONDS = 900

STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
STATUS_EXPIRED = "expired"

DROP_REVIEW_LIMIT = "over_review_limit"
SEARCH_NOT_USED = "not_used"


class RequestError(ValueError):
    """A Preview request that cannot be accepted."""

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        super().__init__(message or code)


class StoreUnavailable(RuntimeError):
    """Redis (the plan store) is not reachable. There is no in-process fallback."""


# --------------------------------------------------------------------------- plan store


class PlanStore(Protocol):
    def save(self, tenant_id: str, preview_id: str, plan: dict[str, Any]) -> None: ...

    def load(self, tenant_id: str, preview_id: str) -> dict[str, Any] | None: ...

    def acquire(self, tenant_id: str, preview_id: str) -> str | None:
        """None when this preview holds the tenant lock, else the running preview id."""
        ...

    def release(self, tenant_id: str, preview_id: str) -> None: ...


class RedisPlanStore:
    """Plans and the per-tenant running lock in Redis. The key carries the database name."""

    def __init__(self, client: Any) -> None:
        self._client = client
        self._prefix = f"cip:web_discovery:{site_pause._database_name()}:"  # noqa: SLF001

    def _plan_key(self, tenant_id: str, preview_id: str) -> str:
        return f"{self._prefix}wd:preview:{tenant_id}:{preview_id}"

    def _lock_key(self, tenant_id: str) -> str:
        return f"{self._prefix}wd:running:{tenant_id}"

    def save(self, tenant_id: str, preview_id: str, plan: dict[str, Any]) -> None:
        try:
            self._client.set(
                self._plan_key(tenant_id, preview_id),
                json.dumps(plan, default=str),
                ex=PLAN_TTL_SECONDS,
            )
        except (redis.exceptions.RedisError, OSError) as exc:
            raise StoreUnavailable(type(exc).__name__) from exc

    def load(self, tenant_id: str, preview_id: str) -> dict[str, Any] | None:
        try:
            raw = self._client.get(self._plan_key(tenant_id, preview_id))
        except (redis.exceptions.RedisError, OSError) as exc:
            raise StoreUnavailable(type(exc).__name__) from exc
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    def acquire(self, tenant_id: str, preview_id: str) -> str | None:
        try:
            if self._client.set(
                self._lock_key(tenant_id),
                preview_id,
                nx=True,
                ex=RUNNING_LOCK_SECONDS,
            ):
                return None
            held = self._client.get(self._lock_key(tenant_id))
        except (redis.exceptions.RedisError, OSError) as exc:
            raise StoreUnavailable(type(exc).__name__) from exc
        if isinstance(held, bytes):
            held = held.decode("utf-8", errors="replace")
        return str(held) if held else None

    def release(self, tenant_id: str, preview_id: str) -> None:
        try:
            held = self._client.get(self._lock_key(tenant_id))
            if isinstance(held, bytes):
                held = held.decode("utf-8", errors="replace")
            if held == preview_id:
                self._client.delete(self._lock_key(tenant_id))
        except (redis.exceptions.RedisError, OSError):
            return None


class MemoryPlanStore:
    """Process-local plan store for tests only (production uses Redis and never falls back)."""

    def __init__(self) -> None:
        self.plans: dict[tuple[str, str], dict[str, Any]] = {}
        self.locks: dict[str, str] = {}

    def save(self, tenant_id: str, preview_id: str, plan: dict[str, Any]) -> None:
        self.plans[(tenant_id, preview_id)] = json.loads(json.dumps(plan, default=str))

    def load(self, tenant_id: str, preview_id: str) -> dict[str, Any] | None:
        plan = self.plans.get((tenant_id, preview_id))
        return json.loads(json.dumps(plan)) if plan is not None else None

    def acquire(self, tenant_id: str, preview_id: str) -> str | None:
        held = self.locks.get(tenant_id)
        if held is not None:
            return held
        self.locks[tenant_id] = preview_id
        return None

    def release(self, tenant_id: str, preview_id: str) -> None:
        if self.locks.get(tenant_id) == preview_id:
            self.locks.pop(tenant_id, None)


def default_plan_store() -> PlanStore:
    client = site_pause._redis_client()  # noqa: SLF001 - the one Redis client the app uses
    try:
        client.ping()
    except (redis.exceptions.RedisError, OSError) as exc:
        raise StoreUnavailable(type(exc).__name__) from exc
    return RedisPlanStore(client)


# --------------------------------------------------------------------------- request


def normalize_request(raw: dict[str, Any]) -> dict[str, Any]:
    """Clean a Preview request or raise a RequestError with a stable code."""
    scope = raw.get("scope")
    if scope not in SCOPES:
        raise RequestError("scope_invalid", f"scope must be one of {', '.join(SCOPES)}")
    request: dict[str, Any] = {"scope": scope}
    if scope in (SCOPE_CUSTOMER, SCOPE_DOMAIN):
        customer_id = raw.get("customer_id")
        if not isinstance(customer_id, int) or isinstance(customer_id, bool):
            raise RequestError("customer_required", "customer_id is required for this scope")
        request["customer_id"] = customer_id
    if scope == SCOPE_DOMAIN:
        try:
            request["domain"] = normalize_domain(str(raw.get("domain") or ""))
        except SiteOnboardError as exc:
            raise RequestError("domain_invalid", str(exc)) from exc
    if scope == SCOPE_UNLINKED:
        customer_id = raw.get("customer_id")
        request["customer_id"] = (
            customer_id
            if isinstance(customer_id, int) and not isinstance(customer_id, bool)
            else None
        )
    return request


def new_plan(
    tenant_id: str,
    preview_id: str,
    request: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    return {
        "preview_id": preview_id,
        "tenant_id": tenant_id,
        "status": STATUS_QUEUED,
        "request": request,
        "created_at": (now or datetime.now(UTC)).isoformat(),
        "finished_at": None,
        "progress": {"done": 0, "total": 0},
        "settings_fingerprint": None,
        "result": None,
        "applied": None,
        "error": None,
    }


def new_preview_id() -> str:
    return str(uuid.uuid4())


def mark_failed(store: PlanStore, tenant_id: str, preview_id: str, error: str) -> None:
    """Record a failed preview; error is a code or exception class, never a message."""
    plan = store.load(tenant_id, preview_id) or new_plan(tenant_id, preview_id, {})
    plan["status"] = STATUS_FAILED
    plan["error"] = error
    plan["finished_at"] = datetime.now(UTC).isoformat()
    store.save(tenant_id, preview_id, plan)


# --------------------------------------------------------------------------- search tracking


class SearchTracker:
    """Wraps the search function to count queries and summarise attempts for the result."""

    def __init__(self, fn: Callable[[str], Any] | None, providers: list[str]) -> None:
        self._fn = fn
        self._providers = list(providers)
        self.queries = 0
        self._statuses: list[str] = []
        self._used: str | None = None
        self._attempts: list[dict[str, Any]] = []

    @property
    def enabled(self) -> bool:
        return self._fn is not None and bool(self._providers)

    def __call__(self, query: str) -> Any:
        assert self._fn is not None
        self.queries += 1
        try:
            outcome = self._fn(query)
        except Exception as exc:  # noqa: BLE001 - a preview never fails because of search
            self._statuses.append("unavailable")
            self._add_attempt(
                {
                    "provider": None,
                    "status": "unavailable",
                    "http_status": None,
                    "reason": type(exc).__name__,
                }
            )
            return None
        status = str(getattr(outcome, "status", "unavailable"))
        self._statuses.append(status)
        provider = getattr(outcome, "provider", None)
        if status in ("ok", "empty") and self._used is None and provider:
            self._used = str(provider)
        for attempt in getattr(outcome, "attempts", None) or []:
            if isinstance(attempt, dict):
                self._add_attempt(attempt)
        return outcome

    def _add_attempt(self, attempt: dict[str, Any]) -> None:
        clean = {
            "provider": attempt.get("provider"),
            "status": attempt.get("status"),
            "http_status": attempt.get("http_status"),
            "reason": attempt.get("reason"),
        }
        if clean not in self._attempts:
            self._attempts.append(clean)

    def summary(self, *, available: bool = True) -> dict[str, Any]:
        if not self._providers:
            status = "off"
        elif not available:
            status = "unavailable"
        elif self.queries == 0:
            status = SEARCH_NOT_USED
        elif any(status_value == "ok" for status_value in self._statuses):
            status = "ok"
        elif any(status_value == "empty" for status_value in self._statuses):
            status = "empty"
        else:
            status = "unavailable"
        attempts = list(self._attempts)
        if self._providers and not available and not attempts:
            attempts = [
                {
                    "provider": None,
                    "status": "unavailable",
                    "http_status": None,
                    "reason": "search_not_installed",
                }
            ]
        return {"status": status, "provider_used": self._used, "attempts": attempts}


def default_search_fn(
    settings: DiscoverySettings, getter: Any, cache: Any
) -> Callable[[str], Any] | None:
    """Build the search callable from tenant settings, or None when search is off."""
    if not settings.search_providers:
        return None
    try:
        from app.services.listing_capture.web_discovery.search import web_search
    except ImportError:
        return None
    parameters = inspect.signature(web_search).parameters
    takes_any = any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()
    )
    extra: dict[str, Any] = {}
    if settings.searxng_url and ("searxng_url" in parameters or takes_any):
        extra["searxng_url"] = settings.searxng_url
    if "search_options" in parameters or takes_any:
        extra["search_options"] = settings.search_options

    def run(query: str) -> Any:
        return web_search(
            query,
            providers=list(settings.search_providers),
            getter=getter,
            cache=cache,
            **extra,
        )

    return run


def engine_hosts_for(settings: DiscoverySettings) -> frozenset[str]:
    """Search-engine hosts are never proposed as a customer's site."""
    hosts: set[str] = set()
    try:
        from app.services.listing_capture.web_discovery import search as search_module

        hosts |= {str(host) for host in getattr(search_module, "SEARCH_ENGINE_HOSTS", ())}
    except ImportError:
        pass
    if settings.searxng_url:
        hosts.add(urlsplit(settings.searxng_url).hostname or "")
    return frozenset(normalize_host(host) for host in hosts if host)


# --------------------------------------------------------------------------- one customer


def _site_state(host: str, ctx: cand.CustomerContext) -> tuple[str, str | None]:
    """An existing site key, or the state indicating Apply would create a site."""
    key = ctx.own_site_hosts.get(host) or ctx.other_site_hosts.get(host)
    return ("existing", key) if key else ("would_create", None)


def _candidate_entry(
    item: cand.Candidate,
    *,
    item_no: int,
    customer: DimCustomer,
    ctx: cand.CustomerContext,
    settings: DiscoverySettings,
) -> dict[str, Any]:
    extra = dict(item.extra)
    if item.redirected_from:
        extra["redirected_from"] = item.redirected_from
    if item.drop_reason:
        extra["drop_reason"] = item.drop_reason
    evidence = build_evidence(
        host=item.host,
        customer_name=customer.name,
        sources=item.sources,
        endings=settings.domain_endings,
        country=settings.country,
        home=item.home,
        http_status=item.http_status,
        final_url=item.final_url,
        robots=item.robots,
        product_hits=item.product_hits,
        extra=extra,
    )
    user_entered = SOURCE_USER in item.sources
    if item.outcome_hint == OUTCOME_DROPPED:
        outcome = OUTCOME_DROPPED
    else:
        outcome = decide(
            evidence,
            user_entered=user_entered,
            rejected=item.host in ctx.rejected_hosts and not user_entered,
            already_monitored=item.outcome_hint == OUTCOME_MONITORED,
        )
    state, site_key = _site_state(item.host, ctx)
    entry = {
        "item_id": f"c-{item_no}",
        "domain": item.host,
        "outcome": outcome,
        "drop_reason": item.drop_reason if outcome == OUTCOME_DROPPED else None,
        "proposed_site_key": (
            site_key
            or discovery._site_key_from_origin(f"https://{item.host}")  # noqa: SLF001
        ),
        "evidence": evidence,
    }
    return entry


def _order_and_limit(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Saved-on-Apply first, then the review queue ranked (at most 5), then the rest."""
    queued = sorted(
        (entry for entry in entries if entry["outcome"] == OUTCOME_QUEUE),
        key=lambda entry: rank_key(entry["evidence"]),
    )
    for extra in queued[MAX_QUEUED_PER_CUSTOMER:]:
        extra["outcome"] = OUTCOME_DROPPED
        extra["drop_reason"] = DROP_REVIEW_LIMIT
    order = {
        OUTCOME_AUTO: 0,
        OUTCOME_USER: 0,
        OUTCOME_QUEUE: 1,
        OUTCOME_MONITORED: 2,
        OUTCOME_REJECTED: 3,
        OUTCOME_DROPPED: 4,
    }
    queue_rank = {id(entry): index for index, entry in enumerate(queued)}
    return sorted(
        entries,
        key=lambda entry: (
            order.get(entry["outcome"], 5),
            queue_rank.get(id(entry), 0),
            entry["domain"],
        ),
    )


def preview_customer(
    session: Session,
    customer: DimCustomer,
    settings: DiscoverySettings,
    *,
    getter: Any,
    resolve: Callable[[str], list[str]],
    search: Callable[[str], Any] | None,
    engine_hosts: frozenset[str],
    user_domain: str | None,
    counter: list[int],
    find_pages: Callable[..., list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    notes: list[str] = []
    found, ctx = cand.gather_candidates(
        session,
        customer,
        settings,
        search=search,
        resolve=resolve,
        engine_hosts=engine_hosts,
        user_domain=user_domain,
        notes=notes,
    )
    loaded = cand.load_homepages(found, getter)
    entries: list[dict[str, Any]] = []
    for item in loaded:
        counter[0] += 1
        entries.append(
            _candidate_entry(
                item,
                item_no=counter[0],
                customer=customer,
                ctx=ctx,
                settings=settings,
            )
        )
    entries = _order_and_limit(entries)

    sites: list[dict[str, Any]] = []
    for entry in entries:
        if entry["outcome"] not in (OUTCOME_AUTO, OUTCOME_USER, OUTCOME_MONITORED):
            continue
        state, site_key = _site_state(entry["domain"], ctx)
        stored = ctx.site_search_patterns.get(site_key or "")
        site = {
            "domain": entry["domain"],
            "site_key": site_key or entry["proposed_site_key"],
            "state": state,
            "search_pattern": (
                {"value": stored, "how": "stored"} if stored else {"value": None, "how": "none"}
            ),
            "fetch": {"stopped": None, "requests": 0},
            "pages": [],
        }
        summary = (
            getter.gate_summary(f"host:{entry['domain']}")
            if hasattr(getter, "gate_summary")
            else None
        )
        if summary:
            site["fetch"] = {
                "stopped": summary.get("stopped"),
                "requests": summary.get("requests", 0),
            }
        if find_pages is not None:
            site["pages"] = find_pages(session, customer, site, entry, getter, settings)
        sites.append(site)
    return {
        "customer_id": int(customer.id),
        "customer_name": str(customer.name or ""),
        "reporting": ctx.reporting,
        "notes": notes,
        "candidates": entries,
        "sites": sites,
    }


# --------------------------------------------------------------------------- the run


def _totals(customers: list[dict[str, Any]], listings: list[dict[str, Any]]) -> dict[str, int]:
    candidates = [candidate for block in customers for candidate in block["candidates"]]
    pages = [
        page
        for block in customers
        for site in block["sites"]
        for page in site.get("pages") or []
    ]
    return {
        "sites_auto": sum(
            1 for candidate in candidates if candidate["outcome"] in (OUTCOME_AUTO, OUTCOME_USER)
        ),
        "sites_review": sum(
            1 for candidate in candidates if candidate["outcome"] == OUTCOME_QUEUE
        ),
        "pages_auto": sum(1 for page in pages if page.get("outcome") == "auto_link"),
        "pages_review": sum(1 for page in pages if page.get("outcome") == "steward_queue"),
        "listings_auto": sum(1 for row in listings if row.get("outcome") == "auto_link"),
        "listings_review": sum(1 for row in listings if row.get("outcome") == "steward_queue"),
    }


def _load_customers(
    session: Session, tenant_id: str, request: dict[str, Any]
) -> list[DimCustomer]:
    scope = request["scope"]
    if scope == SCOPE_REPORTING:
        customers = [
            customer
            for _config, customer in discovery._reporting_customers(  # noqa: SLF001
                session, tenant_id
            )
        ]
        seen = {int(customer.id) for customer in customers}
        for raw in request.get("also_customer_ids") or []:
            try:
                customer_id = int(raw)
            except (TypeError, ValueError):
                continue
            if customer_id in seen:
                continue
            row = session.get(DimCustomer, customer_id)
            if isinstance(row, DimCustomer) and str(row.tenant_id) == tenant_id:
                customers.append(row)
                seen.add(customer_id)
        return customers
    if scope in (SCOPE_CUSTOMER, SCOPE_DOMAIN):
        customer = session.get(DimCustomer, int(request["customer_id"]))
        if not isinstance(customer, DimCustomer) or str(customer.tenant_id) != tenant_id:
            raise RequestError("customer_not_found", "That customer is not in this tenant.")
        return [customer]
    return []


def run_preview(
    session: Session,
    *,
    tenant_id: str,
    preview_id: str,
    request: dict[str, Any],
    getter: Any,
    resolve: Callable[[str], list[str]],
    plan_store: PlanStore,
    search: Callable[[str], Any] | None = None,
    search_factory: Callable[[DiscoverySettings], Callable[[str], Any] | None] | None = None,
    engine_hosts: frozenset[str] | None = None,
    find_pages: Callable[..., list[dict[str, Any]]] | None = None,
    link_listings: Callable[..., list[dict[str, Any]]] | None = None,
    now: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """Compute the preview and save it to the plan store.

    The first statement is SET TRANSACTION READ ONLY. The caller rolls the session back.
    ``search_factory`` builds a query callable from the loaded tenant settings.
    """
    clock = now or (lambda: datetime.now(UTC))
    session.execute(text("SET TRANSACTION READ ONLY"))

    plan = plan_store.load(tenant_id, preview_id) or new_plan(
        tenant_id, preview_id, request, now=clock()
    )
    plan["status"] = STATUS_RUNNING
    plan_store.save(tenant_id, preview_id, plan)

    scope = request["scope"]
    settings = load_discovery_settings(session, tenant_id)
    missing = settings.missing_for(scope)
    if missing:
        plan["status"] = STATUS_FAILED
        plan["error"] = "settings_missing"
        plan["finished_at"] = clock().isoformat()
        plan_store.save(tenant_id, preview_id, plan)
        return plan

    customers = _load_customers(session, tenant_id, request)
    plan["progress"] = {"done": 0, "total": len(customers)}
    plan["settings_fingerprint"] = settings.fingerprint()
    plan_store.save(tenant_id, preview_id, plan)

    search_fn = (
        search
        if search is not None
        else (search_factory(settings) if search_factory else None)
    )
    hosts = engine_hosts if engine_hosts is not None else engine_hosts_for(settings)
    tracker = SearchTracker(search_fn, settings.search_providers)
    search_for_customers: Callable[[str], Any] | None = tracker if tracker.enabled else None
    search_available = search_fn is not None
    counter = [0]
    stopped: str | None = None
    blocks: list[dict[str, Any]] = []
    for index, customer in enumerate(customers):
        policy = getattr(getter, "policy", None)
        if policy is not None and policy.time_left() <= 0:
            stopped = "time_limit"
            break
        blocks.append(
            preview_customer(
                session,
                customer,
                settings,
                getter=getter,
                resolve=resolve,
                search=search_for_customers,
                engine_hosts=hosts,
                user_domain=request.get("domain") if scope == SCOPE_DOMAIN else None,
                counter=counter,
                find_pages=find_pages,
            )
        )
        plan["progress"] = {"done": index + 1, "total": len(customers)}
        plan_store.save(tenant_id, preview_id, plan)

    listings: list[dict[str, Any]] = []
    notes: list[str] = []
    if scope == SCOPE_UNLINKED:
        if link_listings is None:
            from app.services.listing_capture.web_discovery.linking import (
                link_unlinked_listings,
            )

            link_listings = link_unlinked_listings
        listings = link_listings(session, tenant_id, request.get("customer_id"), getter)

    plan["result"] = {
        "scope": scope,
        "created_at": plan["created_at"],
        "finished_at": clock().isoformat(),
        "stopped": stopped,
        "settings": settings.public(),
        "search": tracker.summary(available=search_available),
        "customers": blocks,
        "listings": listings,
        "notes": notes,
        "totals": _totals(blocks, listings),
    }
    plan["status"] = STATUS_DONE
    plan["finished_at"] = plan["result"]["finished_at"]
    plan_store.save(tenant_id, preview_id, plan)
    return plan
