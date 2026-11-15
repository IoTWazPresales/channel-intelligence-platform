"""Steward records a site key and domain for a reporting customer that has neither.

This is the path out of ``no_site_key``. It writes that customer's listing seed and,
when the site row is missing, creates the row. It does not fetch a page, does not
name a customer or a retailer, and does not invent a seller. A page pattern is
derived only from product URLs the steward pastes, and only into columns that are
still empty. A customer that already has a site key is left unchanged. An existing
site is attached only when every stored link host and every other customer's
recorded domain for that key is this domain, or none is recorded yet.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.models.customer_report_config import CustomerReportConfig
from app.models.dimensions import DimCustomer
from app.models.listing_capture import CustomerListing
from app.models.listing_site import ListingSite
from app.services.listing_capture.sites import SITE_KEY_RE, create_site, update_site
from app.services.listing_capture.url_pattern import derive_listing_url_pattern

_HOST = re.compile(
    r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\.(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))+"
)
_MAX_URLS = 8


class SiteOnboardError(ValueError):
    """The steward's site record was refused. ``code`` is stable for tests and the UI."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def normalize_domain(raw: str) -> str:
    """A host name, lower-cased, with no scheme, port, path or user info."""
    text = (raw or "").strip().lower().rstrip(".")
    if (
        not text
        or "://" in text
        or "/" in text
        or "@" in text
        or any(ch.isspace() for ch in text)
        or ":" in text
        or not _HOST.fullmatch(text)
    ):
        raise SiteOnboardError("domain_invalid", "Domain must be a host name, with no scheme or path.")
    return text


def record_customer_site(
    session: Session,
    *,
    tenant_id: str,
    customer_id: int,
    site_key: str,
    domain: str,
    example_urls: list[str] | None,
    actor: str | None,
) -> dict[str, Any]:
    """Attach ``site_key`` and ``domain`` to one reporting customer. Safe to call again."""
    host = normalize_domain(domain)
    key = (site_key or "").strip().lower()
    if not SITE_KEY_RE.match(key):
        raise SiteOnboardError(
            "site_key_invalid",
            "Site key must be 1-32 lowercase letters, digits, '-' or '_'.",
        )
    urls = _product_urls(example_urls or [], host)
    customer = session.scalar(
        select(DimCustomer).where(DimCustomer.id == int(customer_id), DimCustomer.tenant_id == tenant_id)
    )
    if not isinstance(customer, DimCustomer):
        raise SiteOnboardError("customer_not_found", "That customer is not in this tenant.")
    config = session.scalar(
        select(CustomerReportConfig).where(CustomerReportConfig.customer_id == int(customer.id))
    )
    if not isinstance(config, CustomerReportConfig) or not config.reports_expected:
        raise SiteOnboardError(
            "not_reporting",
            "This customer is not a reporting customer, so a site is not attached here.",
        )

    profile = dict(config.feed_profile_json) if isinstance(config.feed_profile_json, dict) else {}
    seed = dict(profile.get("listing_seed")) if isinstance(profile.get("listing_seed"), dict) else {}
    site_block = dict(seed.get("site")) if isinstance(seed.get("site"), dict) else {}
    recorded = _recorded_keys(session, customer_id=int(customer.id), seed=seed)
    if recorded and recorded != [key]:
        raise SiteOnboardError(
            "site_already_recorded",
            "This customer already has a site key. This form is only for a customer with none.",
        )
    stored_domain = site_block.get("domain")
    if isinstance(stored_domain, str) and stored_domain.strip():
        try:
            stored_host = normalize_domain(stored_domain)
        except SiteOnboardError:
            stored_host = stored_domain.strip().lower()
        if stored_host != host:
            raise SiteOnboardError(
                "domain_already_recorded",
                "A different domain is already recorded for this customer.",
            )

    derived = derive_listing_url_pattern(urls) if urls else None
    row = session.scalar(
        select(ListingSite).where(ListingSite.tenant_id == tenant_id, ListingSite.site_key == key)
    )
    if isinstance(row, ListingSite):
        _reject_conflicting_domain(
            session,
            tenant_id=tenant_id,
            site_key=key,
            row=row,
            customer_id=int(customer.id),
            host=host,
        )
    created = False
    if not isinstance(row, ListingSite):
        row = create_site(
            session,
            tenant_id=tenant_id,
            site_key=key,
            fields={"display_name": host[:128]},
            actor=actor,
        )
        created = True

    pattern_status, fill, site_block = _patterns(
        row,
        site_block,
        derived=derived,
        urls=urls,
        host=host,
    )
    if fill:
        try:
            update_site(session, row, fields=fill, actor=actor)
        except ValueError as exc:
            raise SiteOnboardError("pattern_invalid", "The derived page pattern is not usable.") from exc
    elif created:
        row.updated_by = actor

    seed["marketplace"] = key
    seed["site"] = site_block
    profile["listing_seed"] = seed
    config.feed_profile_json = profile
    flag_modified(config, "feed_profile_json")
    session.add(config)
    session.flush()
    return {
        "customer_id": int(customer.id),
        "site_key": key,
        "domain": host,
        "site_id": int(row.id),
        "created_site": created,
        "pattern_status": pattern_status,
        "product_url_pattern": row.product_url_pattern,
        "page_id_pattern": row.page_id_pattern,
    }


def _product_urls(raw: list[str], domain: str) -> list[str]:
    out: list[str] = []
    for item in raw:
        text = (item or "").strip()
        if not text:
            continue
        if len(text) > 1024:
            raise SiteOnboardError("url_invalid", "A product link is too long.")
        parts = urlsplit(text)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise SiteOnboardError("url_invalid", "Each product link must be an http or https URL.")
        if parts.username or parts.password:
            raise SiteOnboardError("url_invalid", "A product link must not include a user name.")
        host = parts.hostname.lower().rstrip(".")
        if host != domain:
            raise SiteOnboardError("url_host_mismatch", "Each product link must use the same domain.")
        out.append(text)
    if len(out) > _MAX_URLS:
        raise SiteOnboardError("too_many_urls", "Paste at most 8 product links.")
    return out


def _recorded_keys(session: Session, *, customer_id: int, seed: dict[str, Any]) -> list[str]:
    """The site key already on this customer: the seed marketplace, else listing marketplaces.

    The customer was already limited to the caller's tenant. A seed marketplace wins, matching
    autoconfigure, so this form cannot hide a second listing marketplace behind a new seed.
    """
    named = seed.get("marketplace")
    if isinstance(named, str) and named.strip():
        key = named.strip().lower()
        return [key] if SITE_KEY_RE.match(key) else []
    found = session.scalars(
        select(func.lower(func.trim(CustomerListing.marketplace)))
        .where(CustomerListing.customer_id == int(customer_id))
        .distinct()
    ).all()
    return sorted({str(value) for value in found if isinstance(value, str) and SITE_KEY_RE.match(value)})


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _host_in_pattern(pattern: Any) -> str | None:
    """Host of a stored link pattern, or None when the pattern is not an http(s) URL."""
    if not isinstance(pattern, str) or not pattern.strip():
        return None
    parts = urlsplit(pattern.strip())
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    host = parts.hostname.lower().rstrip(".")
    if not _HOST.fullmatch(host):
        return None
    return host


def _other_recorded_domains(
    session: Session, *, tenant_id: str, site_key: str, customer_id: int
) -> set[str]:
    """Domains other customers in this tenant already recorded for ``site_key``."""
    profiles = session.scalars(
        select(CustomerReportConfig.feed_profile_json)
        .join(DimCustomer, DimCustomer.id == CustomerReportConfig.customer_id)
        .where(
            DimCustomer.tenant_id == tenant_id,
            CustomerReportConfig.customer_id != int(customer_id),
        )
    ).all()
    hosts: set[str] = set()
    for profile in profiles:
        if not isinstance(profile, dict):
            continue
        seed = profile.get("listing_seed")
        if not isinstance(seed, dict):
            continue
        named = seed.get("marketplace")
        if not isinstance(named, str) or named.strip().lower() != site_key:
            continue
        site = seed.get("site") if isinstance(seed.get("site"), dict) else {}
        raw = site.get("domain")
        if not isinstance(raw, str) or not raw.strip():
            continue
        try:
            hosts.add(normalize_domain(raw))
        except SiteOnboardError:
            continue
    return hosts


def _reject_conflicting_domain(
    session: Session,
    *,
    tenant_id: str,
    site_key: str,
    row: ListingSite,
    customer_id: int,
    host: str,
) -> None:
    """Refuse to attach an existing site to a domain it is not already using.

    A site with no link host and no other recorded domain can take this domain.
    Customers that record the same domain share the site.
    """
    known = {
        found
        for found in (
            _host_in_pattern(row.product_url_pattern),
            _host_in_pattern(row.search_url_pattern),
            _host_in_pattern(row.details_url_pattern),
        )
        if found
    }
    known.update(
        _other_recorded_domains(session, tenant_id=tenant_id, site_key=site_key, customer_id=customer_id)
    )
    if known and known != {host}:
        raise SiteOnboardError(
            "domain_conflict",
            "This site is already configured for a different domain.",
        )


def _patterns(
    row: ListingSite,
    site_block: dict[str, Any],
    *,
    derived: Any,
    urls: list[str],
    host: str,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    block = dict(site_block)
    block["domain"] = host
    if urls:
        block["example_urls"] = urls
    if _blank(block.get("display_name")):
        block["display_name"] = host[:128]

    seed_pattern = block.get("product_url_pattern")
    seed_page = block.get("page_id_pattern")
    site_open = _blank(row.product_url_pattern) and _blank(row.page_id_pattern)
    seed_pair = not _blank(seed_pattern) and not _blank(seed_page)
    seed_open = _blank(seed_pattern) and _blank(seed_page)
    fill: dict[str, Any] = {}

    if not site_open or not seed_open:
        if site_open and seed_pair:
            fill["product_url_pattern"] = str(seed_pattern).strip()
            fill["page_id_pattern"] = str(seed_page).strip()
        return ("kept", fill, block)

    if derived is None:
        return ("not_shared" if urls else "none", fill, block)

    block["product_url_pattern"] = derived.product_url_pattern
    block["page_id_pattern"] = derived.page_id_pattern
    fill["product_url_pattern"] = derived.product_url_pattern
    fill["page_id_pattern"] = derived.page_id_pattern
    return ("derived", fill, block)
