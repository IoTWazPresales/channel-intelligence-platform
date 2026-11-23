"""Find the sites that might be a customer's web shop, and load their home pages.

Sources, all keyed by host (lower-cased, ``www.`` stripped):

- ``on_file``: the customer's seed domain, its confirmed ``customer_web_site`` rows, the hosts of
  its ``customer_listing.url``
- ``email``: the domain part of its active contact addresses. A domain that appears on contacts of
  two or more different customers in the tenant is not proposed (this removes shared webmail
  without a hard-coded list). Only the domain is kept, never an address.
- ``product_search``: up to 3 of its products, searched by name or model plus the tenant country
- ``name_search``: its name plus the tenant country
- ``guess``: its name keys × the tenant's domain endings, kept only when the name resolves
- ``user``: a domain a steward typed. This scope starts from that domain only.

The database reads are in ``read_context``; ``assemble_candidates`` is pure (an injected ``search``
and ``resolve``), so tests need no database or network.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.models.commercial_lineup import CommercialLineupLine
from app.models.customer_report_config import CustomerReportConfig
from app.models.customer_web_site import WEB_SITE_CONFIRMED, WEB_SITE_REJECTED, CustomerWebSite
from app.models.dimensions import CustomerContact, DimCustomer, DimProduct
from app.models.facts import FactSalesSellout
from app.models.lineup import FactLineupPlanItem
from app.models.listing_capture import CustomerListing
from app.models.listing_site import ListingSite
from app.services.customer_reporting import is_reporting
from app.services.listing_capture import discovery
from app.services.listing_capture.site_onboarding import SiteOnboardError, normalize_domain
from app.services.listing_capture.web_discovery.homepage import HomeSignals, parse_home
from app.services.listing_capture.web_discovery.polite import DEFAULT_SPACING_SECONDS, Fetched
from app.services.listing_capture.web_discovery.scoring import (
    OUTCOME_DROPPED,
    OUTCOME_MONITORED,
    SOURCE_EMAIL,
    SOURCE_GUESS,
    SOURCE_NAME_SEARCH,
    SOURCE_ON_FILE,
    SOURCE_PRODUCT_SEARCH,
    SOURCE_USER,
    customer_keys,
    normalize_host,
)
from app.services.listing_capture.web_discovery.settings import DiscoverySettings

MAX_PRODUCTS_SEARCHED = 3
HOSTS_PER_QUERY = 3
MAX_GUESS_KEYS = 3
MAX_GUESS_ENDINGS = 6
MIN_GUESS_KEY_LENGTH = 3
MAX_HOMEPAGES_PER_CUSTOMER = 25
_PRODUCT_SOURCE_LIMIT = 500

DROP_ROBOTS = "robots_disallowed"
DROP_UNREACHABLE = "unreachable"
DROP_OTHER_CUSTOMER_SITE = "site_of_other_customer"
DROP_NOT_CHECKED = "not_checked_over_limit"

Search = Callable[[str], Any]
Resolve = Callable[[str], list[str]]


@dataclass
class ProductInfo:
    id: int
    sales_model_name: str | None = None
    part_number: str | None = None
    name: str = ""
    source_index: int = 0

    @property
    def label(self) -> str:
        return (self.sales_model_name or self.part_number or self.name or str(self.id))[:80]


@dataclass
class Candidate:
    host: str
    sources: set[str] = field(default_factory=set)
    # Product-search hits and the like, gathered before the home page is read.
    product_hits: list[dict[str, Any]] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)
    gate_key: str = ""
    outcome_hint: str | None = None  # already_monitored | dropped
    drop_reason: str | None = None
    # Filled by ``load_homepages``.
    http_status: int | None = None
    final_url: str | None = None
    robots: str = "unknown"
    home: HomeSignals | None = None
    redirected_from: str | None = None

    def __post_init__(self) -> None:
        if not self.gate_key:
            self.gate_key = f"host:{self.host}"


@dataclass
class CustomerContext:
    """What the database says about one customer. Built by ``read_context``; tests build it by hand."""

    customer_id: int
    name: str
    seed_host: str | None = None
    confirmed_hosts: list[str] = field(default_factory=list)
    rejected_hosts: set[str] = field(default_factory=set)
    listing_hosts: list[str] = field(default_factory=list)
    # host -> listing_site.site_key for this customer's own sites.
    own_site_hosts: dict[str, str] = field(default_factory=dict)
    # host -> site_key for the tenant's other listing sites (not this customer's).
    other_site_hosts: dict[str, str] = field(default_factory=dict)
    # site_key -> stored search_url_pattern, for the sites above and this customer's own.
    site_search_patterns: dict[str, str | None] = field(default_factory=dict)
    # True when the customer is a reporting customer.
    reporting: bool = False
    contact_domains: list[str] = field(default_factory=list)
    shared_contact_domains: set[str] = field(default_factory=set)
    products: list[ProductInfo] = field(default_factory=list)


# --------------------------------------------------------------------------- database reads


def _host_of(value: str | None) -> str:
    return normalize_host(discovery._domain(value))  # noqa: SLF001 - reuse the one host parser


def _site_hosts(site: ListingSite) -> set[str]:
    return {
        host
        for host in (
            _host_of(getattr(site, field_name, None))
            for field_name in ("product_url_pattern", "search_url_pattern", "details_url_pattern")
        )
        if host
    }


def _contact_domain(email: str | None) -> str | None:
    text = (email or "").strip()
    if "@" not in text:
        return None
    try:
        return normalize_host(normalize_domain(text.rsplit("@", 1)[1]))
    except SiteOnboardError:
        return None


def _product_info(row: DimProduct, source_index: int) -> ProductInfo:
    return ProductInfo(
        id=int(row.id),
        sales_model_name=(row.sales_model_name or "").strip() or None,
        part_number=(row.part_number or "").strip() or None,
        name=str(row.name or ""),
        source_index=source_index,
    )


def _product_ids_by_source(session: Session, tenant_id: str, customer_id: int) -> list[tuple[int, int]]:
    """``(source_index, product_id)`` in source order: catalogue, line-up plan, commercial line-up, sell-out."""
    found: list[tuple[int, int]] = []
    seen: set[int] = set()

    def add(index: int, ids: list[int | None]) -> None:
        for pid in ids:
            if pid is not None and int(pid) not in seen:
                seen.add(int(pid))
                found.append((index, int(pid)))

    add(0, list(discovery._catalogue_product_ids(session, tenant_id=tenant_id, customer_id=customer_id)))  # noqa: SLF001
    add(
        1,
        list(
            session.scalars(
                select(FactLineupPlanItem.product_id)
                .where(FactLineupPlanItem.customer_id == customer_id)
                .distinct()
                .order_by(FactLineupPlanItem.product_id)
                .limit(_PRODUCT_SOURCE_LIMIT)
            ).all()
        ),
    )
    add(
        2,
        list(
            session.scalars(
                select(CommercialLineupLine.product_id)
                .where(CommercialLineupLine.customer_id == customer_id, CommercialLineupLine.product_id.is_not(None))
                .distinct()
                .order_by(CommercialLineupLine.product_id)
                .limit(_PRODUCT_SOURCE_LIMIT)
            ).all()
        ),
    )
    add(
        3,
        list(
            session.scalars(
                select(FactSalesSellout.product_id)
                .where(FactSalesSellout.tenant_id == tenant_id, FactSalesSellout.customer_id == customer_id)
                .distinct()
                .order_by(FactSalesSellout.product_id)
                .limit(_PRODUCT_SOURCE_LIMIT)
            ).all()
        ),
    )
    return found


def read_context(session: Session, customer: DimCustomer) -> CustomerContext:
    """Read everything the candidate step needs about one customer. Reads only."""
    tenant_id = str(customer.tenant_id)
    customer_id = int(customer.id)
    ctx = CustomerContext(customer_id=customer_id, name=str(customer.name or ""))

    config = session.scalar(
        select(CustomerReportConfig).where(CustomerReportConfig.customer_id == customer_id)
    )
    seed = discovery._seed(config) if isinstance(config, CustomerReportConfig) else {}  # noqa: SLF001
    ctx.seed_host = _host_of(discovery._seed_origin(seed)) or None  # noqa: SLF001

    web_rows = session.execute(
        select(CustomerWebSite.domain, CustomerWebSite.status).where(
            CustomerWebSite.tenant_id == tenant_id, CustomerWebSite.customer_id == customer_id
        )
    ).all()
    ctx.confirmed_hosts = [normalize_host(d) for d, status in web_rows if status == WEB_SITE_CONFIRMED]
    ctx.rejected_hosts = {normalize_host(d) for d, status in web_rows if status == WEB_SITE_REJECTED}

    urls = session.scalars(select(CustomerListing.url).where(CustomerListing.customer_id == customer_id)).all()
    ctx.listing_hosts = sorted({host for host in (_host_of(u) for u in urls) if host})

    own_keys = set(
        discovery._site_keys(session, tenant_id=tenant_id, customer_id=customer_id, seed=seed)  # noqa: SLF001
    )
    for site in session.scalars(select(ListingSite).where(ListingSite.tenant_id == tenant_id)).all():
        hosts = _site_hosts(site)
        ctx.site_search_patterns[str(site.site_key)] = site.search_url_pattern
        for host in hosts:
            if str(site.site_key) in own_keys:
                ctx.own_site_hosts[host] = str(site.site_key)
            else:
                ctx.other_site_hosts[host] = str(site.site_key)
    for host in ctx.own_site_hosts:
        ctx.other_site_hosts.pop(host, None)
    ctx.reporting = isinstance(config, CustomerReportConfig) and is_reporting(config, customer)

    emails = session.scalars(
        select(CustomerContact.email).where(
            CustomerContact.customer_id == customer_id,
            CustomerContact.is_active.is_(True),
            CustomerContact.email.is_not(None),
        )
    ).all()
    ctx.contact_domains = sorted({d for d in (_contact_domain(e) for e in emails) if d})
    if ctx.contact_domains:
        domain_expr = func.lower(func.split_part(CustomerContact.email, "@", 2))
        shared = session.execute(
            select(domain_expr)
            .join(DimCustomer, DimCustomer.id == CustomerContact.customer_id)
            .where(DimCustomer.tenant_id == tenant_id, domain_expr.in_(ctx.contact_domains))
            .group_by(domain_expr)
            .having(func.count(distinct(CustomerContact.customer_id)) > 1)
        ).all()
        ctx.shared_contact_domains = {normalize_host(str(row[0])) for row in shared}

    pairs = _product_ids_by_source(session, tenant_id, customer_id)
    if pairs:
        by_id = {
            int(p.id): p
            for p in session.scalars(
                select(DimProduct).where(
                    DimProduct.tenant_id == tenant_id, DimProduct.id.in_([pid for _i, pid in pairs])
                )
            ).all()
        }
        ctx.products = [_product_info(by_id[pid], idx) for idx, pid in pairs if pid in by_id]
    return ctx


def rejected_hosts(session: Session, tenant_id: str, customer_id: int) -> set[str]:
    rows = session.scalars(
        select(CustomerWebSite.domain).where(
            CustomerWebSite.tenant_id == tenant_id,
            CustomerWebSite.customer_id == int(customer_id),
            CustomerWebSite.status == WEB_SITE_REJECTED,
        )
    ).all()
    return {normalize_host(str(d)) for d in rows}


# --------------------------------------------------------------------------- pure assembly


def choose_products(products: list[ProductInfo]) -> list[ProductInfo]:
    """Up to 3 products: by source order, then products that have a sales model name, then id."""
    seen: set[int] = set()
    unique: list[ProductInfo] = []
    for product in products:
        if product.id not in seen:
            seen.add(product.id)
            unique.append(product)
    unique.sort(key=lambda p: (p.source_index, p.sales_model_name is None, p.id))
    return unique[:MAX_PRODUCTS_SEARCHED]


def product_query(product: ProductInfo, country_name: str) -> str:
    if product.sales_model_name:
        return f'"{product.sales_model_name}" {country_name}'
    if product.part_number:
        return f'"{product.part_number}" {country_name}'
    return f"{product.name[:80]} {country_name}"


def name_query(name: str, country_name: str) -> str:
    return f'"{name.strip()}" {country_name}'


def _result_hosts(outcome: Any, limit: int = HOSTS_PER_QUERY) -> list[tuple[str, int]]:
    """The first ``limit`` distinct result hosts with their rank (from 1)."""
    found: list[tuple[str, int]] = []
    for index, result in enumerate(getattr(outcome, "results", None) or [], start=1):
        host = normalize_host(getattr(result, "host", None) or urlsplit(getattr(result, "url", "") or "").hostname or "")
        if not host or any(host == existing for existing, _rank in found):
            continue
        found.append((host, int(getattr(result, "rank", None) or index)))
        if len(found) >= limit:
            break
    return found


def _usable_hostname(host: str) -> bool:
    try:
        return normalize_domain(host) == host
    except SiteOnboardError:
        return False


class _Pool:
    def __init__(self, ctx: CustomerContext, settings: DiscoverySettings, engine_hosts: frozenset[str]) -> None:
        self.ctx = ctx
        self.items: dict[str, Candidate] = {}
        self.excluded = [d.lower() for d in settings.excluded_domains]
        self.engine_hosts = engine_hosts

    def _skip(self, host: str) -> bool:
        if not host or not _usable_hostname(host):
            return True
        if host in self.engine_hosts:
            return True
        return any(host == d or host.endswith("." + d) for d in self.excluded)

    def add(self, raw_host: str, source: str, *, hit: dict[str, Any] | None = None, extra: dict[str, Any] | None = None) -> None:
        host = normalize_host(raw_host)
        if self._skip(host):
            return
        item = self.items.get(host)
        if item is None:
            item = Candidate(host=host)
            self.items[host] = item
        item.sources.add(source)
        if hit is not None:
            item.product_hits.append(hit)
        if extra:
            item.extra.update(extra)

    def finish(self) -> list[Candidate]:
        ctx = self.ctx
        for host, item in self.items.items():
            if host in ctx.own_site_hosts:
                item.gate_key = ctx.own_site_hosts[host]
                item.outcome_hint = OUTCOME_MONITORED
            elif host in ctx.confirmed_hosts:
                item.outcome_hint = OUTCOME_MONITORED
            elif host in ctx.other_site_hosts and SOURCE_USER not in item.sources:
                # Shown, not proposed. A steward who types the domain still reuses that site.
                item.outcome_hint = OUTCOME_DROPPED
                item.drop_reason = DROP_OTHER_CUSTOMER_SITE
        return sorted(self.items.values(), key=lambda c: (-len(c.sources), c.host))


def assemble_candidates(
    ctx: CustomerContext,
    settings: DiscoverySettings,
    *,
    search: Search | None,
    resolve: Resolve,
    engine_hosts: frozenset[str] = frozenset(),
    user_domain: str | None = None,
    notes: list[str] | None = None,
) -> list[Candidate]:
    """The candidate sites for one customer. Pure given ``search`` and ``resolve``."""
    pool = _Pool(ctx, settings, engine_hosts)
    if user_domain:
        pool.add(user_domain, SOURCE_USER)
        return pool.finish()

    # 1. on file
    if ctx.seed_host:
        pool.add(ctx.seed_host, SOURCE_ON_FILE, extra={"on_file_via": "seed"})
    for host in ctx.confirmed_hosts:
        pool.add(host, SOURCE_ON_FILE, extra={"on_file_via": "confirmed"})
    for host in ctx.listing_hosts:
        pool.add(host, SOURCE_ON_FILE, extra={"on_file_via": "listing"})

    # 2. contact email domains (the domain only)
    for domain in ctx.contact_domains:
        if domain in ctx.shared_contact_domains:
            continue
        pool.add(domain, SOURCE_EMAIL)

    country_name = settings.country_name or ""
    chosen = choose_products(ctx.products)
    if not ctx.products and notes is not None:
        notes.append("No products on record for this customer")

    # 3. product search, then 4. name search
    if search is not None and country_name:
        for product in chosen:
            query = product_query(product, country_name)
            for host, rank in _result_hosts(search(query)):
                pool.add(
                    host,
                    SOURCE_PRODUCT_SEARCH,
                    hit={"product_id": product.id, "product_label": product.label, "query": query, "rank": rank},
                )
        if ctx.name.strip():
            for host, rank in _result_hosts(search(name_query(ctx.name, country_name))):
                pool.add(host, SOURCE_NAME_SEARCH, extra={"name_search_rank": rank})

    # 5. guesses: name keys x the tenant's domain endings, kept only when the name resolves
    keys = [k for k in customer_keys(ctx.name) if len(k) >= MIN_GUESS_KEY_LENGTH][:MAX_GUESS_KEYS]
    for key in keys:
        for ending in settings.domain_endings[:MAX_GUESS_ENDINGS]:
            bare = f"{key}{ending}"
            if resolve(bare) or resolve(f"www.{bare}"):
                pool.add(bare, SOURCE_GUESS, extra={"guessed_host": bare})
    return pool.finish()


def gather_candidates(
    session: Session,
    customer: DimCustomer,
    settings: DiscoverySettings,
    *,
    search: Search | None,
    resolve: Resolve,
    engine_hosts: frozenset[str] = frozenset(),
    user_domain: str | None = None,
    notes: list[str] | None = None,
) -> tuple[list[Candidate], CustomerContext]:
    """Read the customer, then assemble its candidates. Reads only; writes nothing."""
    ctx = read_context(session, customer)
    items = assemble_candidates(
        ctx,
        settings,
        search=search,
        resolve=resolve,
        engine_hosts=engine_hosts,
        user_domain=user_domain,
        notes=notes,
    )
    return items, ctx


# --------------------------------------------------------------------------- home pages


def _apply_fetch(item: Candidate, fetched: Fetched) -> None:
    item.http_status = int(fetched.status or 0)
    item.final_url = fetched.final_url
    if fetched.refused is not None:
        item.drop_reason = DROP_ROBOTS if fetched.refused == "robots" else str(fetched.refused)
        item.robots = "disallowed" if fetched.refused == "robots" else "unknown"
        return
    if item.http_status == 0:
        item.drop_reason = DROP_UNREACHABLE
        return
    if item.http_status != 200:
        item.drop_reason = f"http_{item.http_status}"
        return
    item.robots = "allowed"
    item.home = parse_home(fetched.body)


def load_homepages(
    candidates: list[Candidate],
    getter: Any,
    *,
    limit: int = MAX_HOMEPAGES_PER_CUSTOMER,
) -> list[Candidate]:
    """Load ``https://<host>/`` for each candidate that is not already decided, through the polite getter.

    A candidate that is unreachable, robots-disallowed or not 200 gets a ``drop_reason`` (shown in a
    Preview, never saved). A redirect to a different host replaces the host (``redirected_from``)
    and merges into any candidate already on that host.
    """
    loaded = 0
    for item in candidates:
        if item.outcome_hint == OUTCOME_DROPPED:
            continue
        if loaded >= limit:
            item.outcome_hint = OUTCOME_DROPPED
            item.drop_reason = DROP_NOT_CHECKED
            continue
        loaded += 1
        fetched = getter.get(f"https://{item.host}/", gate_key=item.gate_key, spacing=DEFAULT_SPACING_SECONDS)
        _apply_fetch(item, fetched)
        if item.drop_reason is not None and item.outcome_hint != OUTCOME_MONITORED:
            item.outcome_hint = OUTCOME_DROPPED
    return merge_redirects(candidates)


def merge_redirects(candidates: list[Candidate]) -> list[Candidate]:
    """Replace a candidate's host by its final host after a redirect, merging duplicates."""
    merged: dict[str, Candidate] = {}
    for item in candidates:
        if item.http_status == 200 and item.final_url and item.drop_reason is None:
            final_host = normalize_host(urlsplit(item.final_url).hostname or "")
            if final_host and final_host != item.host:
                item.redirected_from = item.host
                item.host = final_host
                if item.gate_key == f"host:{item.redirected_from}":
                    item.gate_key = f"host:{final_host}"
        existing = merged.get(item.host)
        if existing is None:
            merged[item.host] = item
            continue
        # Two candidates ended on one host: keep the one whose home page loaded, union the evidence.
        item_loaded = item.drop_reason is None
        winner, loser = (item, existing) if (existing.drop_reason is not None and item_loaded) else (existing, item)
        winner.sources |= loser.sources
        winner.product_hits.extend(loser.product_hits)
        for key, value in loser.extra.items():
            winner.extra.setdefault(key, value)
        if winner.redirected_from is None:
            winner.redirected_from = loser.redirected_from
        merged[item.host] = winner
    return list(merged.values())
