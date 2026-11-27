"""Find catalogue product pages for customers and propose listings.

A reporting customer is ``customer_report_config.reports_expected`` and not merged away
(``app.services.customer_reporting``). A site is a confirmed web site or a marketplace
already on the customer's listings. ``listing_seed`` is not a source of a site or of
URL patterns. Nothing here names a retailer.

For each product with ``reported_soh`` > 0 in the customer's latest reported period
(the newest period that has a stock figure, including zero),
and with no listing on that site and no open queue row, discovery searches in order:
barcode, then model, using the site's search URL, then a search form on the site
origin, then the origin sitemap. A page is kept only when its barcode or model matches
the product. One match proposes a ``cst_listing_seed`` row (status ``proposed``) and
remembers the URL. It does not create a ``customer_listing``.
URL-less feed proposals are enriched in place. Each run searches at most 25 products
per customer/site and keeps its last product id in the shared run-state store; the
next run resumes there, wrapping after the catalogue has been visited.

Every request goes through the shared per-site fetch policy (``site_fetch``), the same
rules the listing poll uses: the site's ``rate_limit_seconds`` spacing (default 5 s), no
request to a site paused by an earlier 403/429, a 403/429 pauses the site and ends its
search for this run (the product being searched is rolled back and searched again next
run), and a run stops starting requests after the shared time budget.

The budget is shared by every (customer, site) pair of a tenant, so a run does not always
start with the lowest customer id. The pairs form one fixed cycle (customer id, then the
customer's site order); when the budget cuts a pair short, the next run starts at that
pair and carries on round the cycle (``discovery:<tenant>:rotation`` in the run-state
store). Pairs before it in the cycle wait until the cycle comes back round, so a customer
or site that uses most of the budget every run cannot starve the pairs after it. A dry
run (``apply=False``) does not move the rotation. ``autoconfigure_sites`` rotates the
tenants of a scheduled run the same way.

An empty adapter is set to the general HTML reader after a corroborated page. Price,
stock, the page seller, and the buy box are stored on the proposal for the steward.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from contextvars import ContextVar
from hashlib import sha256
from typing import Any
from urllib.parse import quote, urljoin, urlsplit

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.cst_listing_seed import CstListingSeed
from app.models.customer_report_config import CustomerReportConfig
from app.models.dimensions import DimCustomer, DimProduct
from app.models.fact_customer_sellthrough import FactCustomerSellthrough
from app.models.listing_capture import CustomerListing
from app.models.listing_link import (
    LINK_CONFIRMED,
    LINK_REJECTED,
    QUEUE_OPEN,
    ListingLink,
    ListingLinkQueue,
)
from app.models.listing_site import ListingSite
from app.services.customer_reporting import reporting_customer_clauses
from app.services.listing_capture.adapters import configured_adapter
from app.services.listing_capture.adapters.html_page import ADAPTER_KEY as HTML_PAGE_ADAPTER
from app.services.listing_capture.adapters.html_page import parse as parse_html
from app.services.listing_capture.adapters.html_page import seller_or_first_party
from app.services.listing_capture.identity import (
    barcode_key,
    corroboration,
    model_key,
    page_facts_from_html,
    page_facts_from_json,
    product_barcodes,
    product_models,
)
from app.services.listing_capture.links import confirmed_link, queue_case, remember_link
from app.services.listing_capture.site_fetch import (
    FetchPolicy,
    SiteFetchGate,
    default_fetch_policy,
    site_spacing_seconds,
)
from app.services.listing_capture.site_pause import load_run_state, save_run_state
from app.services.listing_capture.sites import (
    SITE_KEY_RE,
    create_site,
    site_config_from_row,
    update_site,
)

ACTOR = "listing-discovery"
REASON_NO_SITE_KEY = "no_site_key"
REASON_NO_CATALOGUE = "no_catalogue_products"
REASON_NO_FETCH = "no_live_fetch"
REASON_NO_SEARCH = "no_search_url"
REASON_NOT_FOUND = "not_found_on_site"
REASON_AMBIGUOUS = "ambiguous"
REASON_READER = "reader_not_configured"
REASON_NO_IDENTITY = "no_barcode_or_model"
REASON_PAUSED = "site_paused"
REASON_TIME_LIMIT = "time_limit"

_HttpGet = Callable[[str], tuple[int, str]]
_SELLER_NAME = re.compile(
    r'"seller"\s*:\s*\{[^{}]*?"(?:name|display_name)"\s*:\s*"((?:\\.|[^"\\])*)"',
    re.IGNORECASE,
)
_SEED_URL_KEYS = ("origin", "domain", "website", "homepage")
# Tenant locale for Babel prices, and robots rules for the run. Unset locale keeps price-parser.
_PRICE_LOCALE: ContextVar[str | None] = ContextVar("cip_discovery_price_locale", default=None)
_ROBOTS: ContextVar[dict[str, Any] | None] = ContextVar("cip_discovery_robots", default=None)
# Robots Sitemap: lines considered, plus /sitemap.xml when it is not already one of them.
_SITEMAP_SEEDS = 2
_SITEMAP_INDEX_CHILDREN = 2


def discover_reporting_customers(
    session: Session,
    *,
    tenant_id: str | None = None,
    http_get: _HttpGet | None = None,
    apply: bool = True,
    product_limit: int = 25,
    run_store=None,
    fetch_policy: FetchPolicy | None = None,
) -> dict[str, Any]:
    """Propose listings for reporting customers. ``apply=False`` does not write.

    ``fetch_policy`` carries the pause store, clock, sleep and time budget shared by
    every site in this run (default: the app pause store, real time, 10 min).
    """
    if product_limit < 1:
        raise ValueError("product_limit must be positive")
    policy = None
    if http_get is not None:
        policy = fetch_policy if fetch_policy is not None else default_fetch_policy()
    entries: list[dict[str, Any]] = []
    for tid in _tenant_ids(session, tenant_id):
        locale_token = _PRICE_LOCALE.set(_configured_locale(session, tid))
        robots_token = _ROBOTS.set({})
        try:
            _discover_tenant(
                session,
                tid,
                entries,
                http_get=http_get,
                apply=apply,
                product_limit=product_limit,
                run_store=run_store,
                policy=policy,
            )
        finally:
            _PRICE_LOCALE.reset(locale_token)
            _ROBOTS.reset(robots_token)
    return {"customers": entries}


def _discover_tenant(
    session: Session,
    tid: str,
    entries: list[dict[str, Any]],
    *,
    http_get: _HttpGet | None,
    apply: bool,
    product_limit: int,
    run_store: Any,
    policy: FetchPolicy | None,
) -> None:
    pairs = [
        (config, customer)
        for config, customer in _reporting_customers(session, tid)
        if str(customer.tenant_id) == tid
    ]
    rotate = apply and policy is not None
    rotation_key = f"discovery:{tid}:rotation"
    plans: list[dict[str, Any]] = []
    units: list[tuple[int, str]] = []
    for config, customer in pairs:
        seed = _seed(config)
        plan: dict[str, Any] = {
            "customer": customer,
            "seed": seed,
            "keys": [],
            "sites": {},
            "entry": None,
        }
        try:
            plan["keys"] = _site_keys(
                session, tenant_id=tid, customer_id=int(customer.id), seed=seed
            )
        except Exception as exc:
            plan["entry"] = _failed_entry(customer, tid, exc)
        if plan["entry"] is None and not plan["keys"]:
            plan["entry"] = _entry(
                customer_id=int(customer.id),
                tenant_id=tid,
                site_key=None,
                reason=REASON_NO_SITE_KEY,
            )
        plan["own_site"] = bool(_seed_origin(seed)) and not bool(
            str(seed.get("marketplace") or "").strip()
        )
        plans.append(plan)
        units.extend((len(plans) - 1, key) for key in plan["keys"])
    if rotate:
        units = _rotated_units(units, plans, load_run_state(rotation_key, store=run_store) or {})
    cut_short: dict[str, Any] | None = None
    for index, key in units:
        plan = plans[index]
        if plan["entry"] is not None:
            continue
        customer = plan["customer"]
        try:
            with session.begin_nested():
                site_row = _discover_site(
                    session,
                    customer=customer,
                    site_key=key,
                    seed=plan["seed"],
                    own_site=plan["own_site"],
                    http_get=http_get,
                    apply=apply,
                    product_limit=product_limit,
                    run_store=run_store,
                    policy=policy,
                )
        except Exception as exc:
            plan["entry"] = _failed_entry(customer, tid, exc)
            continue
        plan["sites"][key] = site_row
        if cut_short is None and _site_time_limited(site_row):
            cut_short = {"customer_id": int(customer.id), "site_key": key}
    if rotate:
        save_run_state(
            rotation_key, cut_short or {"customer_id": 0, "site_key": ""}, store=run_store
        )
    for plan in plans:
        if plan["entry"] is None:
            plan["entry"] = _customer_entry(
                plan["customer"], [plan["sites"][k] for k in plan["keys"]]
            )
        entries.append(plan["entry"])


def _failed_entry(customer: DimCustomer, tenant_id: str, exc: Exception) -> dict[str, Any]:
    return _entry(
        customer_id=int(customer.id),
        tenant_id=tenant_id,
        site_key=None,
        reason="discovery_failed",
        detail=type(exc).__name__,
    )


def _rotated_units(
    units: list[tuple[int, str]], plans: list[dict[str, Any]], state: dict[str, Any]
) -> list[tuple[int, str]]:
    """The cycle of (customer, site) pairs, starting at the pair the budget last cut short.

    If that pair no longer exists, start at the next pair after it in the cycle.
    """
    start_customer = int(state.get("customer_id") or 0)
    start_key = str(state.get("site_key") or "")
    if start_customer <= 0 or not units:
        return units
    for position, (index, key) in enumerate(units):
        if int(plans[index]["customer"].id) == start_customer and key == start_key:
            return units[position:] + units[:position]
    for position, (index, _key) in enumerate(units):
        if int(plans[index]["customer"].id) > start_customer:
            return units[position:] + units[:position]
    return units


def _site_time_limited(site_row: dict[str, Any] | None) -> bool:
    return ((site_row or {}).get("fetch") or {}).get("stopped") == REASON_TIME_LIMIT


def _time_limited(entry: dict[str, Any]) -> bool:
    """True when the shared time budget cut one of this customer's sites short."""
    return any(_site_time_limited(site) for site in entry.get("sites") or [])


def _customer_entry(customer: DimCustomer, site_rows: list[dict[str, Any]]) -> dict[str, Any]:
    tenant_id = str(customer.tenant_id)
    ready = [
        row
        for row in site_rows
        if row["reader_ready"] and row["proposed_listings"] + row["watched_listings"] > 0
    ]
    reason = None if ready else _first_reason(site_rows)
    return _entry(
        customer_id=int(customer.id),
        tenant_id=tenant_id,
        site_key=site_rows[0]["site_key"],
        reason=reason,
        reader=site_rows[0]["reader"],
        reader_ready=any(row["reader_ready"] for row in site_rows),
        proposed_listings=sum(int(row["proposed_listings"]) for row in site_rows),
        proposed_created=sum(int(row["proposed_created"]) for row in site_rows),
        watched_listings=sum(int(row["watched_listings"]) for row in site_rows),
        sites=site_rows,
    )


def _discover_site(
    session: Session,
    *,
    customer: DimCustomer,
    site_key: str,
    seed: dict[str, Any],
    own_site: bool,
    http_get: _HttpGet | None,
    apply: bool,
    product_limit: int,
    run_store=None,
    policy: FetchPolicy | None = None,
) -> dict[str, Any]:
    from app.services.listing_capture.autoconfig import _seed_seller, _seller_present

    tenant_id = str(customer.tenant_id)
    row = _load_site(session, tenant_id, site_key)
    # Reject malformed seller data before discovery writes in its own savepoint.
    # Autoconfiguration keeps an existing customer seller without re-reading the seed.
    if not _seller_present(row, int(customer.id)):
        _seed_seller(seed)
    if row is None and apply:
        display = _display_name(seed, site_key)
        row = create_site(
            session,
            tenant_id=tenant_id,
            site_key=site_key,
            fields={"display_name": display},
            actor=ACTOR,
        )
    if row is not None and apply:
        if (
            own_site
            and _blank(row.first_party_seller)
            and not _seller_present(row, int(customer.id))
        ):
            _safe_update(session, row, {"first_party_seller": str(customer.name or "").strip()})
        row = _load_site(session, tenant_id, site_key) or row
    if row is None:
        return _site_entry(site_key, reason=REASON_NO_SITE_KEY)
    product_ids = _catalogue_product_ids(session, tenant_id=tenant_id, customer_id=int(customer.id))
    if not product_ids:
        return _site_entry(
            site_key,
            reason=REASON_NO_CATALOGUE,
            reader=_reader_name(row),
            reader_ready=_reader_ready(row),
        )
    if http_get is None:
        return _site_entry(
            site_key,
            reason=REASON_NO_FETCH,
            reader=_reader_name(row),
            reader_ready=_reader_ready(row),
        )
    gate = SiteFetchGate(
        site_key=site_key,
        spacing_seconds=site_spacing_seconds(row.rate_limit_seconds),
        policy=policy if policy is not None else default_fetch_policy(),
    )
    if gate.check_pause():
        return _site_entry(
            site_key,
            reason=REASON_PAUSED,
            reader=_reader_name(row),
            reader_ready=_reader_ready(row),
            fetch=gate.summary(),
        )
    raw_get = http_get
    http_get = gate.bind(raw_get)

    proposed = 0
    created = 0
    watched = 0
    reasons: list[str] = []
    searched = 0
    cursor_key = f"discovery:{tenant_id}:{int(customer.id)}:{int(row.id)}"
    previous = load_run_state(cursor_key, store=run_store) or {}
    after = int(previous.get("after_product_id") or 0)
    ordered = sorted(set(product_ids))
    resumed = [pid for pid in ordered if pid > after]
    remaining = resumed or ordered
    last_product_id = after if resumed else 0
    for product_id in remaining:
        if searched >= product_limit:
            break
        previous_product_id = last_product_id
        last_product_id = product_id
        if _has_listing(
            session, customer_id=int(customer.id), site_key=site_key, product_id=product_id
        ):
            watched += 1
            continue
        if _queue_exists(session, site_id=int(row.id), product_id=product_id):
            reasons.append(REASON_AMBIGUOUS)
            continue
        proposal = _proposed_seed(
            session, customer_id=int(customer.id), site_key=site_key, product_id=product_id
        )
        if proposal is not None and str((proposal.raw_json or {}).get("url") or "").strip():
            proposed += 1
            continue
        product = session.get(DimProduct, product_id)
        if not isinstance(product, DimProduct) or str(product.tenant_id) != tenant_id:
            continue
        if not product_barcodes(product) and not product_models(product):
            reasons.append(REASON_NO_IDENTITY)
            continue
        if not gate.can_send():
            last_product_id = previous_product_id
            break
        # A refusal or the time budget can cut a search short; its partial result must not
        # be written (it would look like "not found"), so each search has its own savepoint.
        savepoint = session.begin_nested() if apply else None
        try:
            outcome = _find_and_propose(
                session,
                customer=customer,
                product=product,
                row=row,
                seed=seed,
                http_get=http_get,
                apply=apply,
            )
        except Exception:
            if savepoint is not None and savepoint.is_active:
                savepoint.rollback()
            raise
        if gate.stopped is not None:
            if savepoint is not None and savepoint.is_active:
                savepoint.rollback()
            last_product_id = previous_product_id
            row = _load_site(session, tenant_id, site_key) or row
            break
        if savepoint is not None and savepoint.is_active:
            savepoint.commit()
        searched += 1
        row = _load_site(session, tenant_id, site_key) or row
        if outcome["created"]:
            created += 1
            proposed += 1
        elif outcome["proposed"]:
            proposed += 1
        elif outcome["reason"]:
            reasons.append(str(outcome["reason"]))
    next_after = last_product_id if last_product_id < remaining[-1] else 0
    if apply:
        save_run_state(cursor_key, {"after_product_id": next_after}, store=run_store)
    ready = _reader_ready(row)
    reason = None
    if gate.stopped == "site_paused":
        reason = REASON_PAUSED
    elif proposed + watched == 0:
        fallback = REASON_TIME_LIMIT if gate.stopped else REASON_NOT_FOUND
        reason = reasons[0] if reasons else fallback
    elif not ready:
        reason = REASON_READER
    return _site_entry(
        site_key,
        reason=reason,
        reader=_reader_name(row),
        reader_ready=ready,
        proposed_listings=proposed,
        proposed_created=created,
        watched_listings=watched,
        next_after_product_id=next_after or None,
        fetch=gate.summary(),
    )


def _find_and_propose(
    session: Session,
    *,
    customer: DimCustomer,
    product: DimProduct,
    row: ListingSite,
    seed: dict[str, Any],
    http_get: _HttpGet,
    apply: bool,
) -> dict[str, Any]:
    config = site_config_from_row(row).for_customer(int(customer.id))
    remembered = confirmed_link(session, int(row.id), int(product.id))
    if remembered is not None:
        captured = _capture_url(config, remembered.url, http_get, product) or {}
        if not captured.get("corroboration"):
            return {"created": False, "proposed": False, "reason": REASON_NOT_FOUND}
        if not _complete_capture(captured):
            if apply:
                queue_case(
                    session,
                    site=config,
                    product_id=int(product.id),
                    customer_id=int(customer.id),
                    listing_id=None,
                    reason="capture_incomplete",
                    candidates=[{"url": str(captured.get("url") or remembered.url)}],
                    evidence={k: captured.get(k) for k in ("price", "availability", "seller")},
                )
            return {"created": False, "proposed": False, "reason": "capture_incomplete"}
        created = _store_proposal(
            session,
            customer=customer,
            product=product,
            row=row,
            captured=captured,
            apply=apply,
        )
        return {"created": created, "proposed": True, "reason": None}

    search_pattern = (row.search_url_pattern or "").strip() or _discover_search_pattern(
        config, seed, http_get
    )
    if search_pattern and apply and _blank(row.search_url_pattern):
        _safe_update(session, row, {"search_url_pattern": search_pattern})
        row = _load_site(session, str(row.tenant_id), str(row.site_key)) or row
        config = site_config_from_row(row).for_customer(int(customer.id))
    candidates = _search_candidates(config, product, search_pattern, seed, http_get)
    if not candidates and not search_pattern:
        return {"created": False, "proposed": False, "reason": REASON_NO_SEARCH}
    corroborated = [item for item in candidates if item.get("corroboration")]
    rejected = _rejected_urls(session, int(row.id), int(product.id))
    corroborated = [item for item in corroborated if item["url"] not in rejected]
    if len(corroborated) > 1:
        if apply:
            queue_case(
                session,
                site=config,
                product_id=int(product.id),
                customer_id=int(customer.id),
                listing_id=None,
                reason=REASON_AMBIGUOUS,
                candidates=[{"url": item["url"]} for item in corroborated[:8]],
                evidence={"stock_code": None},
            )
        return {"created": False, "proposed": False, "reason": REASON_AMBIGUOUS}
    if len(corroborated) != 1:
        open_candidates = [item for item in candidates if item["url"] not in rejected]
        if apply and open_candidates:
            queue_case(
                session,
                site=config,
                product_id=int(product.id),
                customer_id=int(customer.id),
                listing_id=None,
                reason=REASON_NOT_FOUND,
                candidates=[{"url": item["url"]} for item in open_candidates[:8]],
                evidence={},
            )
        return {"created": False, "proposed": False, "reason": REASON_NOT_FOUND}
    found = corroborated[0]
    if not found.get("price") or not found.get("availability") or not found.get("seller"):
        if apply:
            queue_case(
                session,
                site=config,
                product_id=int(product.id),
                customer_id=int(customer.id),
                listing_id=None,
                reason="capture_incomplete",
                candidates=[{"url": found["url"]}],
                evidence={k: found.get(k) for k in ("price", "availability", "seller")},
            )
        return {"created": False, "proposed": False, "reason": "capture_incomplete"}
    if apply and _blank(row.adapter_key):
        fields: dict[str, Any] = {"adapter_key": HTML_PAGE_ADAPTER}
        fields.update(_patterns_for(found["url"], str(found.get("token") or "")))
        _safe_update(session, row, fields)
        row = _load_site(session, str(row.tenant_id), str(row.site_key)) or row
    created = _store_proposal(
        session, customer=customer, product=product, row=row, captured=found, apply=apply
    )
    return {"created": created, "proposed": True, "reason": None}


def _store_proposal(
    session: Session,
    *,
    customer: DimCustomer,
    product: DimProduct,
    row: ListingSite,
    captured: dict[str, Any],
    apply: bool,
) -> bool:
    if not apply or not _complete_capture(captured):
        return False
    # Search tokens (especially digit-stripped models) are not page identities.
    # Hash the full URL, not a truncated prefix; keep different catalogue products distinct.
    external_id = (
        f"discovery:{int(product.id)}:{sha256(str(captured['url']).encode('utf-8')).hexdigest()}"
    )
    existing = session.scalar(
        select(CstListingSeed.id).where(
            CstListingSeed.customer_id == int(customer.id),
            CstListingSeed.marketplace == str(row.site_key),
            CstListingSeed.external_id == external_id,
        )
    )
    config = site_config_from_row(row).for_customer(int(customer.id))
    remember_link(
        session,
        site=config,
        product_id=int(product.id),
        url=str(captured["url"]),
        status=LINK_CONFIRMED,
        evidence={"corroboration": captured.get("corroboration"), "source": ACTOR},
        actor=ACTOR,
    )
    if existing is not None:
        return False
    proposal = _proposed_seed(
        session,
        customer_id=int(customer.id),
        site_key=str(row.site_key),
        product_id=int(product.id),
    )
    created = proposal is None
    evidence = {
        "source": ACTOR,
        "url": captured.get("url"),
        "price": captured.get("price"),
        "availability": captured.get("availability"),
        "seller": captured.get("seller"),
        "buy_box": captured.get("buy_box"),
        "marketplace_sellers": captured.get("marketplace_sellers") or [],
        "corroboration": captured.get("corroboration"),
    }
    if proposal is not None:
        # Enrich the feed proposal in place, preserving its external id and import evidence.
        proposal.raw_json = {**(proposal.raw_json or {}), **evidence}
    else:
        proposal = CstListingSeed(
            customer_id=int(customer.id),
            marketplace=str(row.site_key),
            external_id=external_id,
            product_id=int(product.id),
            status="proposed",
            raw_json=evidence,
        )
    session.add(proposal)
    session.flush()
    return created


def _search_candidates(
    config: Any,
    product: DimProduct,
    search_pattern: str,
    seed: dict[str, Any],
    http_get: _HttpGet,
) -> list[dict[str, Any]]:
    queries = _identity_queries(product)
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    if search_pattern and "{query}" in search_pattern:
        for _kind, query in queries:
            status, body = _http(http_get, search_pattern.replace("{query}", quote(query, safe="")))
            if status != 200 or not body:
                continue
            for url in _urls_from_document(config, body, search_pattern, query):
                if url in seen:
                    continue
                seen.add(url)
                captured = _capture_url(config, url, http_get, product, token=query)
                if captured is not None:
                    found.append(captured)
            if any(item.get("corroboration") for item in found):
                return found
    if not any(item.get("corroboration") for item in found):
        origin = _origin_text(
            _seed_origin(seed) or search_pattern or config.product_url_pattern or ""
        )
        tokens = [query for _kind, query in queries if query]
        for url in _sitemap_urls(origin, tokens, http_get) if origin and tokens else []:
            if url in seen:
                continue
            seen.add(url)
            token = next((item for item in tokens if item in url), "")
            captured = _capture_url(config, url, http_get, product, token=token or None)
            if captured is not None:
                found.append(captured)
    return found


def _capture_url(
    config: Any,
    url: str,
    http_get: _HttpGet,
    product: DimProduct,
    token: str | None = None,
) -> dict[str, Any] | None:
    status, body = _http(http_get, url)
    if status != 200 or not body:
        return None
    data = _json_object(body)
    facts = page_facts_from_html(body)
    if data is not None:
        json_facts = page_facts_from_json(data)
        if corroboration(json_facts, product):
            facts = json_facts
    how = corroboration(facts, product)
    if how is None:
        return {"url": url, "corroboration": None, "token": token}
    parsed = parse_html(body, site=config, parser_version="discovery")
    availability = (
        parsed.availability if parsed.availability in {"in_stock", "out_of_stock"} else None
    )
    locale = _PRICE_LOCALE.get()
    if locale:
        from app.services.listing_capture.web_discovery.page_facts import (
            page_facts_from_html as locale_page_facts,
        )

        amount = locale_page_facts(body, url, locale=locale).price_amount
        price = float(amount) if amount is not None else None
    else:
        price = parsed.price if parsed.parse_status == "ok" else None
    # The seller of the offer that supplied the price (BACKLOG-226 item 4), not the first one.
    # An ambiguous page gives no seller rather than the own seller (Codex review of PR #104, B1).
    seller = seller_or_first_party(body, price, config.first_party_seller)
    sellers = _seller_names(body)
    if seller and seller not in sellers:
        sellers.insert(0, seller)
    used = token or (product_barcodes(product)[0] if product_barcodes(product) else "")
    return {
        "url": url,
        "corroboration": how,
        "token": barcode_key(used) or model_key(used) or used,
        "price": price,
        "availability": availability,
        "seller": seller,
        "marketplace_sellers": sellers,
        "buy_box": {"price": price, "availability": availability, "seller": seller},
    }


def _urls_from_document(config: Any, body: str, base: str, token: str) -> list[str]:
    data = _json_object(body)
    urls: list[str] = []
    if data is not None:
        from app.services.listing_capture.adapters.rest_buybox import product_url, search_hits

        for hit in search_hits(data):
            built = product_url(config, str(hit.get("page_id") or ""), slug=hit.get("slug"))
            if built:
                urls.append(built)
        if urls:
            return urls[:3]
    from app.services.listing_capture.web_discovery.document_parse import (
        absolute_url,
        document_links,
    )

    host = urlsplit(base).netloc.lower()
    ranked: list[tuple[int, str]] = []
    for href, navigation in document_links(body):
        absolute = absolute_url(base, href)
        if absolute is None or urlsplit(absolute).netloc.lower() != host:
            continue
        path = urlsplit(absolute).path
        product_link = bool(re.search(r"/(?:p|products?|dp|items?)/", path, re.IGNORECASE))
        if config.page_id_pattern:
            try:
                product_link = product_link or bool(re.search(config.page_id_pattern, absolute))
            except re.error:
                pass
        navigation = navigation or path.rstrip("/").lower() in {
            "",
            "/login",
            "/cart",
            "/account",
            "/contact",
            "/about",
            "/wishlist",
            "/checkout",
        }
        rank = (0 if product_link else 4 if navigation else 2) + (
            0 if token and token in absolute else 1
        )
        ranked.append((rank, absolute.split("#")[0]))
    ranked.sort(key=lambda item: item[0])
    return list(dict.fromkeys(url for _rank, url in ranked))[:3]


def _discover_search_pattern(config: Any, seed: dict[str, Any], http_get: _HttpGet) -> str | None:
    existing = (config.search_url_pattern or "").strip()
    if existing:
        return existing
    origin = _origin_text(_seed_origin(seed) or config.product_url_pattern or "")
    if not origin:
        return None
    status, body = _http(http_get, origin + "/")
    found = _search_form(body) if status == 200 and body else None
    if found is None:
        return None
    action, input_name = found
    target = urljoin(origin + "/", action) if action else origin + "/"
    parts = urlsplit(target)
    if not parts.scheme or not parts.netloc:
        return None
    piece = f"{input_name}={{query}}"
    named = re.compile(rf"(^|&){re.escape(input_name)}=[^&]*")
    current = parts.query or ""
    if named.search(current):
        query = named.sub(lambda match: f"{match.group(1)}{input_name}={{query}}", current, count=1)
    else:
        query = f"{current}&{piece}" if current else piece
    pattern = parts._replace(query=query).geturl()
    if "{query}" not in pattern:
        return None
    return pattern


def _search_form(body: str) -> tuple[str, str] | None:
    """The action and input name of the form that contains ``q``, ``query``, or ``search``."""
    from app.services.listing_capture.web_discovery.document_parse import search_form

    return search_form(body)


def _sitemap_urls(origin: str, tokens: list[str], http_get: _HttpGet) -> list[str]:
    from app.services.listing_capture.web_discovery.document_parse import sitemap_locs

    host = urlsplit(origin).netloc.lower()
    scheme = urlsplit(origin).scheme or "https"
    rules = _robots_for(http_get, f"{scheme}://{host}/")
    seeds = [item for item in (rules.sitemaps or []) if item][:_SITEMAP_SEEDS]
    default = origin.rstrip("/") + "/sitemap.xml"
    if default not in seeds:
        seeds.append(default)
    locs: list[str] = []
    for seed_url in seeds:
        status, body = _http(http_get, seed_url)
        if status != 200 or not body:
            continue
        kind, found = sitemap_locs(body)
        if kind == "index":
            for child in found[:_SITEMAP_INDEX_CHILDREN]:
                child_status, child_body = _http(http_get, child)
                if child_status == 200 and child_body:
                    _kind, child_locs = sitemap_locs(child_body)
                    locs.extend(child_locs)
        else:
            locs.extend(found)
    host = urlsplit(origin).netloc.lower()
    wanted = [token for token in tokens if token]
    matched: list[str] = []
    for token in wanted:
        hits = [
            loc
            for loc in locs
            if urlsplit(loc).netloc.lower() == host and token in loc and loc not in matched
        ]
        matched.extend(hits[:3])
    return matched


def _patterns_for(url: str, token: str) -> dict[str, str]:
    derived = _derived_patterns([url])
    if derived:
        return derived
    if not token or token not in url:
        return {}
    product = url.replace(token, "{page_id}", 1)
    page = re.escape(url).replace(re.escape(token), r"([^/?#]+)", 1)
    if "{page_id}" not in product:
        return {}
    return {"product_url_pattern": product, "page_id_pattern": page}


def _derived_patterns(urls: list[str]) -> dict[str, str]:
    from app.services.listing_capture.url_pattern import derive_listing_url_pattern

    try:
        derived = derive_listing_url_pattern([item for item in urls if item])
    except (TypeError, ValueError):
        return {}
    if derived is None:
        return {}
    out: dict[str, str] = {}
    product = getattr(derived, "product_url_pattern", None)
    page = getattr(derived, "page_id_pattern", None)
    if isinstance(product, str) and "{page_id}" in product:
        out["product_url_pattern"] = product
    if isinstance(page, str) and page:
        out["page_id_pattern"] = page
    return out


def _identity_queries(product: DimProduct) -> list[tuple[str, str]]:
    queries: list[tuple[str, str]] = []
    for barcode in product_barcodes(product):
        key = barcode_key(barcode)
        if key:
            queries.append(("barcode", key))
    for model in product_models(product):
        queries.append(("model", model))
    return queries


def _complete_capture(captured: dict[str, Any]) -> bool:
    """A proposal needs a corroborated page with price, stock, seller, and buy box."""
    if not captured.get("corroboration") or not captured.get("url"):
        return False
    availability = captured.get("availability")
    seller = captured.get("seller")
    buy_box = captured.get("buy_box")
    if (
        captured.get("price") is None
        or not availability
        or not seller
        or not isinstance(buy_box, dict)
    ):
        return False
    return (
        buy_box.get("price") is not None
        and bool(buy_box.get("availability"))
        and bool(buy_box.get("seller"))
    )


def _catalogue_product_ids(session: Session, *, tenant_id: str, customer_id: int) -> list[int]:
    latest = session.scalar(
        select(func.max(FactCustomerSellthrough.period_start_date)).where(
            FactCustomerSellthrough.tenant_id == tenant_id,
            FactCustomerSellthrough.customer_id == int(customer_id),
            FactCustomerSellthrough.reported_soh.is_not(None),
        )
    )
    if latest is None:
        return []
    rows = session.scalars(
        select(FactCustomerSellthrough.product_id)
        .where(
            FactCustomerSellthrough.tenant_id == tenant_id,
            FactCustomerSellthrough.customer_id == int(customer_id),
            FactCustomerSellthrough.period_start_date == latest,
            FactCustomerSellthrough.reported_soh > 0,
        )
        .distinct()
    ).all()
    return [int(row) for row in rows if row is not None]


def _safe_update(session: Session, row: ListingSite, fields: dict[str, Any]) -> None:
    cleaned = {
        key: value
        for key, value in fields.items()
        if value is not None and str(value).strip() != ""
    }
    if not cleaned:
        return
    try:
        update_site(session, row, fields=cleaned, actor=ACTOR)
    except ValueError:
        for key, value in cleaned.items():
            try:
                update_site(session, row, fields={key: value}, actor=ACTOR)
            except ValueError:
                continue


def _reporting_customers(
    session: Session, tenant_id: str
) -> list[tuple[CustomerReportConfig, DimCustomer]]:
    rows = session.execute(
        select(CustomerReportConfig, DimCustomer)
        .join(DimCustomer, DimCustomer.id == CustomerReportConfig.customer_id)
        .where(*reporting_customer_clauses(), DimCustomer.tenant_id == tenant_id)
        .order_by(DimCustomer.id)
    ).all()
    return [(cfg, cust) for cfg, cust in rows if isinstance(cust, DimCustomer)]


def _tenant_ids(session: Session, tenant_id: str | None) -> list[str]:
    if tenant_id is not None:
        return [str(tenant_id)]
    rows = session.scalars(
        select(DimCustomer.tenant_id)
        .join(CustomerReportConfig, CustomerReportConfig.customer_id == DimCustomer.id)
        .where(*reporting_customer_clauses())
        .distinct()
    ).all()
    return sorted({str(row) for row in rows if row})


def _site_keys(
    session: Session, *, tenant_id: str, customer_id: int, seed: dict[str, Any]
) -> list[str]:
    """Confirmed web sites plus marketplaces already on this customer's listings.

    ``listing_seed`` is not a source of a site. ``seed`` stays on the signature for callers.
    """
    del seed
    confirmed = _confirmed_web_site_keys(session, tenant_id=tenant_id, customer_id=customer_id)
    listed = _listing_marketplace_keys(session, tenant_id=tenant_id, customer_id=customer_id)
    return sorted(set(confirmed) | set(listed))


def _confirmed_web_site_keys(session: Session, *, tenant_id: str, customer_id: int) -> list[str]:
    """``listing_site.site_key`` of this customer's confirmed ``customer_web_site`` rows."""
    from app.models.customer_web_site import WEB_SITE_CONFIRMED, CustomerWebSite

    try:
        # Its own savepoint: a database without migration 20261123_0066 reads as "none confirmed".
        with session.begin_nested():
            found = session.scalars(
                select(ListingSite.site_key)
                .join(CustomerWebSite, CustomerWebSite.site_id == ListingSite.id)
                .where(
                    CustomerWebSite.tenant_id == tenant_id,
                    CustomerWebSite.customer_id == int(customer_id),
                    CustomerWebSite.status == WEB_SITE_CONFIRMED,
                    ListingSite.tenant_id == tenant_id,
                )
            ).all()
    except Exception:  # noqa: BLE001
        return []
    return sorted({str(key) for key in found if isinstance(key, str) and SITE_KEY_RE.match(key)})


def _listing_marketplace_keys(session: Session, *, tenant_id: str, customer_id: int) -> list[str]:
    found = session.scalars(
        select(func.lower(func.trim(CustomerListing.marketplace)))
        .join(DimCustomer, DimCustomer.id == CustomerListing.customer_id)
        .where(DimCustomer.tenant_id == tenant_id, CustomerListing.customer_id == int(customer_id))
        .distinct()
    ).all()
    return sorted(
        {str(value) for value in found if isinstance(value, str) and SITE_KEY_RE.match(value)}
    )


def _load_site(session: Session, tenant_id: str, site_key: str) -> ListingSite | None:
    row = session.scalar(
        select(ListingSite)
        .where(ListingSite.tenant_id == tenant_id, ListingSite.site_key == site_key)
        .options(selectinload(ListingSite.sellers))
    )
    return row if isinstance(row, ListingSite) else None


def _has_listing(session: Session, *, customer_id: int, site_key: str, product_id: int) -> bool:
    found = session.scalar(
        select(CustomerListing.id)
        .where(
            CustomerListing.customer_id == int(customer_id),
            CustomerListing.product_id == int(product_id),
            func.lower(func.trim(CustomerListing.marketplace)) == site_key,
        )
        .limit(1)
    )
    return found is not None


def _queue_exists(session: Session, *, site_id: int, product_id: int) -> bool:
    found = session.scalar(
        select(ListingLinkQueue.id)
        .where(
            ListingLinkQueue.site_id == int(site_id),
            ListingLinkQueue.product_id == int(product_id),
            ListingLinkQueue.status == QUEUE_OPEN,
        )
        .limit(1)
    )
    return found is not None


def _proposed_seed(
    session: Session, *, customer_id: int, site_key: str, product_id: int
) -> CstListingSeed | None:
    row = session.scalar(
        select(CstListingSeed).where(
            CstListingSeed.customer_id == int(customer_id),
            CstListingSeed.marketplace == site_key,
            CstListingSeed.product_id == int(product_id),
            CstListingSeed.status == "proposed",
        )
    )
    return row if isinstance(row, CstListingSeed) else None


def _rejected_urls(session: Session, site_id: int, product_id: int) -> set[str]:
    rows = session.scalars(
        select(ListingLink.url).where(
            ListingLink.site_id == int(site_id),
            ListingLink.product_id == int(product_id),
            ListingLink.status == LINK_REJECTED,
        )
    ).all()
    return {str(url) for url in rows if isinstance(url, str)}


def _seed(config: CustomerReportConfig) -> dict[str, Any]:
    profile = config.feed_profile_json if isinstance(config.feed_profile_json, dict) else {}
    seed = profile.get("listing_seed") if isinstance(profile, dict) else None
    return seed if isinstance(seed, dict) else {}


def _seed_origin(seed: dict[str, Any], fallback_domain: str | None = None) -> str | None:
    """The origin the seed names.

    With none, ``https://<fallback_domain>`` (a confirmed web site).
    """
    site = seed.get("site") if isinstance(seed.get("site"), dict) else {}
    for source in (site, seed):
        if not isinstance(source, dict):
            continue
        for key in _SEED_URL_KEYS:
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        for key in ("search_url_pattern", "product_url_pattern", "details_url_pattern"):
            value = source.get(key)
            if isinstance(value, str) and "://" in value:
                return value.strip()
    domain = (fallback_domain or "").strip().lower()
    if domain and "://" not in domain and "/" not in domain:
        return f"https://{domain}"
    return None


def _origin_text(value: str | None) -> str | None:
    text = (value or "").strip()
    if not text:
        return None
    if "://" not in text:
        text = "https://" + text
    parts = urlsplit(text)
    if not parts.scheme or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc}"


def _domain(value: str | None) -> str:
    host = urlsplit(_origin_text(value) or "").hostname or ""
    return host.lower().removeprefix("www.")


def _site_key_from_origin(origin: str) -> str | None:
    host = urlsplit(origin).hostname or ""
    if host.lower().startswith("www."):
        host = host[4:]
    key = re.sub(r"[^a-z0-9]+", "-", host.lower()).strip("-")[:32].strip("-")
    return key if key and SITE_KEY_RE.match(key) else None


def _display_name(seed: dict[str, Any], site_key: str) -> str:
    site = seed.get("site") if isinstance(seed.get("site"), dict) else {}
    name = site.get("display_name") if isinstance(site, dict) else None
    if isinstance(name, str) and name.strip():
        return name.strip()
    return site_key


def _reader_ready(row: ListingSite | None) -> bool:
    if row is None or not row.is_active:
        return False
    return configured_adapter(site_config_from_row(row)) is not None


def _reader_name(row: ListingSite | None) -> str | None:
    if row is None:
        return None
    text = str(row.adapter_key or "").strip()
    return text or None


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _json_object(body: str) -> dict[str, Any] | None:
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _seller_names(body: str) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for raw in _SELLER_NAME.findall(body or ""):
        try:
            name = json.loads(f'"{raw}"')
        except json.JSONDecodeError:
            name = raw
        if not isinstance(name, str):
            continue
        cleaned = name.strip()
        if cleaned and cleaned.casefold() not in seen:
            seen.add(cleaned.casefold())
            names.append(cleaned)
    return names


class _BoundGetter:
    """The shape Crawlee's gated client calls. Pacing stays inside the bound ``http_get``."""

    def __init__(self, http_get: _HttpGet) -> None:
        self._http_get = http_get

    def get(self, url: str, *, gate_key: str | None = None, spacing: float | None = None) -> Any:
        del gate_key, spacing
        status, body = _call_http(self._http_get, url)
        return type(
            "Fetched", (), {"status": status, "body": body, "final_url": url, "refused": None}
        )()


def _call_http(http_get: _HttpGet, url: str) -> tuple[int, str]:
    try:
        result = http_get(url)
    except (OSError, ValueError, RuntimeError, TypeError):
        return 0, ""
    if not isinstance(result, tuple) or len(result) < 2:
        return 0, ""
    status, body = result[0], result[1]
    if isinstance(body, bytes):
        body = body.decode("utf-8", errors="replace")
    try:
        code = int(status or 0)
    except (TypeError, ValueError):
        code = 0
    return code, body if isinstance(body, str) else ""


def _robots_for(http_get: _HttpGet, url: str) -> Any:
    from urllib.parse import urlsplit

    from app.services.listing_capture.web_discovery.robots import RobotsRules, rules_from_response

    parts = urlsplit(url)
    host = (parts.netloc or "").lower()
    cache = _ROBOTS.get()
    if not isinstance(cache, dict) or not host:
        return RobotsRules(mode="allow_all")
    cached = cache.get(host)
    if cached is not None:
        return cached
    status, body = _call_http(http_get, f"{parts.scheme}://{host}/robots.txt")
    rules = rules_from_response(status, body)
    cache[host] = rules
    return rules


def _configured_locale(session: Session, tenant_id: str) -> str | None:
    from app.services.tenant_settings import KEY_TENANT_LOCALE, get_setting

    try:
        value = get_setting(session, tenant_id, KEY_TENANT_LOCALE)
    except Exception:  # noqa: BLE001 - a missing setting reads as unset
        return None
    return value if isinstance(value, str) and value.strip() else None


def _http(http_get: _HttpGet, url: str) -> tuple[int, str]:
    from urllib.parse import urlsplit

    from app.services.listing_capture.web_discovery.crawl import fetch_pages

    path = (urlsplit(url).path or "").lower()
    if not path.endswith("/robots.txt") and not _robots_for(http_get, url).allowed(url):
        return 0, ""
    pages = fetch_pages(
        [url],
        _BoundGetter(http_get),
        gate_key_for=lambda item: (urlsplit(item).netloc or "").lower(),
    )
    page = pages.get(url)
    if page is None:
        return 0, ""
    body = page.body if isinstance(page.body, str) else ""
    return int(page.status or 0), body


def _first_reason(rows: list[dict[str, Any]]) -> str:
    for row in rows:
        if row.get("reason"):
            return str(row["reason"])
    return REASON_NOT_FOUND


def _entry(**kwargs: Any) -> dict[str, Any]:
    base = {
        "customer_id": None,
        "tenant_id": None,
        "site_key": None,
        "reader": None,
        "reader_ready": False,
        "proposed_listings": 0,
        "proposed_created": 0,
        "watched_listings": 0,
        "reason": None,
        "detail": None,
        "sites": [],
    }
    base.update(kwargs)
    return base


def _site_entry(
    site_key: str,
    *,
    reason: str | None,
    reader: str | None = None,
    reader_ready: bool = False,
    proposed_listings: int = 0,
    proposed_created: int = 0,
    watched_listings: int = 0,
    next_after_product_id: int | None = None,
    fetch: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "fetch": fetch,
        "site_key": site_key,
        "reason": reason,
        "reader": reader,
        "reader_ready": reader_ready,
        "proposed_listings": proposed_listings,
        "proposed_created": proposed_created,
        "watched_listings": watched_listings,
        "next_after_product_id": next_after_product_id,
    }
