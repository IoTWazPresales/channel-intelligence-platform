"""Fill empty listing-site configuration from each reporting customer's own data.

On the customer's own site (the general HTML reader), discovery writes that customer's
name as the first-party seller when the site does not already name one. An existing
first-party name is kept and becomes the seller identity, so own stock stays Own.
It is not typed on Sites & sellers. A buy-box site keeps whatever seller names the seed already has.
A customer's stored seller identity is never re-derived. Each customer's identity comes from
that customer only: on a site where another customer already has one, the site-wide
first-party name is neither reused nor filled.

A reporting customer is ``customer_report_config.reports_expected``. The site key is
``feed_profile_json.listing_seed.marketplace`` when that seed names one, otherwise each
distinct ``customer_listing.marketplace`` for that customer. Nothing here names a site.
Steward-filled columns are left as they are. The beat task and the steward endpoint pass
an HTTP getter; callers that pass none do not fetch. The beat runs this daily at 05:20 UTC.
The listing-capture poll runs every 30 minutes.

A customer whose adapter is still unconfigured and who also has no seller names or ids is
reported with both ``needs_details_pattern`` and ``no_seller_data`` (in both buckets).

Seed shape (all optional, all data)::

    feed_profile_json.listing_seed = {
        "marketplace": "<site key>",
        "seller_names": ["<seller>"],
        "seller_ids": ["<id>"],
        "seller": {"names": ["<seller>"], "ids": ["<id>"]},
        "site": {
            "adapter_key": "html_page" | "rest_buybox_json",
            "product_url_pattern": "https://host/p/{page_id}",
            "page_id_pattern": "...one capture group...",
            "search_url_pattern": "https://host/s?q={query}",
            "details_url_pattern": "https://host/d/{page_id}",
            "first_party_seller": "<seller>",
            "rate_limit_seconds": 5,
            "display_name": "<label used only when the site row is created>"
        }
    }
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Callable

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, selectinload

from app.models.customer_report_config import CustomerReportConfig
from app.models.dimensions import DimCustomer, DimProduct
from app.models.listing_capture import CustomerListing
from app.models.listing_site import ListingSite
from app.services.listing_capture.adapters import SiteConfig, configured_adapter
from app.services.listing_capture.adapters.html_page import ADAPTER_KEY as HTML_PAGE_ADAPTER
from app.services.listing_capture.identity import corroboration, page_facts_from_html
from app.services.listing_capture.registry import POLLED_LISTING_STATUSES, not_configured_reason
from app.services.listing_capture.site_pause import (
    RUN_AUTOCONFIGURE,
    RUN_POLL,
    load_run_state,
    save_run_state,
)
from app.services.listing_capture.sites import (
    INFERRED_SELLER_ACTOR,
    SITE_KEY_RE,
    create_site,
    set_site_seller,
    site_config_from_row,
    update_site,
)
from app.services.listing_capture.url_pattern import derive_listing_url_pattern

logger = logging.getLogger(__name__)

AUTOCONFIG_ACTOR = "listing-autoconfigure"
LOCK_NAMESPACE = "listing_capture.autoconfigure_sites"
REASON_NO_SITE_KEY = "no_site_key"
REASON_NO_SELLER = "no_seller_data"
REASON_NEEDS_PATTERN = "needs_details_pattern"
REASON_SELLER_SEED = "seller_seed_invalid"
REASON_FAILED = "autoconfigure_failed"
OUTCOME_CONFIGURED = "configured"
OUTCOME_EXCLUDED = "excluded"
OUTCOME_NEEDS_PATTERN = "needs_pattern"
NOT_POLLED_NO_READER = "no_reader_configured"

_FILLABLE = (
    "adapter_key",
    "product_url_pattern",
    "page_id_pattern",
    "search_url_pattern",
    "details_url_pattern",
    "first_party_seller",
    "rate_limit_seconds",
)
_HttpGet = Callable[[str], tuple[int, str]]


def autoconfigure_sites(
    session: Session,
    *,
    tenant_id: str | None = None,
    http_get: _HttpGet | None = None,
    run_store=None,
) -> dict[str, Any]:
    """Create or fill listing sites for reporting customers. Idempotent under an advisory lock.

    ``tenant_id`` limits the run to one tenant. The beat task passes none and walks every
    tenant that has a reporting customer, filtering every read and write by that tenant.

    ``run.sites`` in the report is the per-site state after the run (listings the poll will skip
    as not configured, the empty columns, each probe's outcome). A site that still has no
    reader and has due listings is logged at WARNING, and the summary is kept as the
    tenant's latest autoconfigure run for capture health.
    """
    from app.services.listing_capture.observation import listing_live_fetch_enabled

    live = listing_live_fetch_enabled()
    _advisory_lock(session)
    entries: list[dict[str, Any]] = []
    tenants = _tenant_ids(session, tenant_id)
    for tid in tenants:
        entries.extend(_configure_tenant(session, tid, http_get=http_get if live else None))
    report = _bucket(entries)
    report["live_fetch_disabled"] = not live
    # A dict, not a top-level list: the top-level lists are the customer buckets.
    report["run"] = {"sites": []}
    for tid in tenants:
        summary = _site_run_summary(session, tid, entries)
        report["run"]["sites"].extend(summary)
        _warn_unconfigured(summary)
        save_run_state(
            run_state_key_autoconfigure(tid),
            {
                "finished_at": datetime.now(UTC).isoformat(),
                "tenant_id": tid,
                "live_fetch_disabled": not live,
                "sites": summary,
            },
            store=run_store,
        )
    return report


def run_state_key_autoconfigure(tenant_id: str) -> str:
    return f"{RUN_AUTOCONFIGURE}:{tenant_id}"


def _site_run_summary(
    session: Session, tenant_id: str, entries: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Per site after this run: configured, unpolled listings, missing columns, probe outcomes."""
    probes: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        if entry.get("tenant_id") != tenant_id or not entry.get("site_key"):
            continue
        if entry.get("probe") is None:
            continue
        found = {"customer_id": entry["customer_id"], **entry["probe"]}
        probes.setdefault(str(entry["site_key"]), []).append(found)
    return [
        {"tenant_id": tenant_id, **row, "probes": probes.get(row["site_key"], [])}
        for row in _site_health(session, tenant_id)
    ]


def _probe_text(probe: dict[str, Any]) -> str:
    status = probe.get("status")
    suffix = f" (HTTP {status})" if status else ""
    return f"customer {probe.get('customer_id')}: {probe.get('reason')}{suffix}"


def _warn_unconfigured(summary: list[dict[str, Any]]) -> None:
    for site in summary:
        if site["configured"] or int(site["skipped_not_configured"]) <= 0:
            continue
        logger.warning(
            "listing autoconfigure: site %s (tenant %s) still has no reader: "
            "%s listings not polled (missing: %s; probe: %s)",
            site["site_key"],
            site["tenant_id"],
            site["skipped_not_configured"],
            ", ".join(site["missing_fields"]) or "unknown",
            "; ".join(_probe_text(p) for p in site["probes"]) or "not run",
        )


def capture_health(session: Session, *, tenant_id: str, run_store=None) -> dict[str, Any]:
    """Read-only capture posture for one tenant. Does not fetch and does not write.

    ``not_polled`` lists each site whose due listings the poll skips because it has no
    reader (with the empty columns and the latest probe outcome). ``last_poll_run`` and
    ``last_autoconfigure_run`` are the latest run records for this tenant (None when no run
    has been kept yet).
    """
    tid = str(tenant_id)
    entries = _configure_tenant(session, tid, http_get=None, apply=False)
    sites = _site_health(session, tid)
    from app.services.listing_capture.coverage import customer_coverage

    coverage = customer_coverage(session, tid)
    skipped = {
        row["site_key"]: row["skipped_not_configured"]
        for row in sites
        if int(row["skipped_not_configured"]) > 0
    }
    last_poll = _last_poll_run(tid, run_store)
    last_auto = _last_autoconfigure_run(tid, run_store)
    probes = {s["site_key"]: s.get("probes") or [] for s in (last_auto or {}).get("sites") or []}
    not_polled = [
        {
            "site_key": row["site_key"],
            "site_id": row["site_id"],
            "listings": row["skipped_not_configured"],
            "reason": NOT_POLLED_NO_READER,
            "missing_fields": row["missing_fields"],
            "last_probes": probes.get(row["site_key"], []),
        }
        for row in sites
        if int(row["skipped_not_configured"]) > 0
    ]
    return {
        "tenant_id": tid,
        "data_unavailable": False,
        "sites": sites,
        "listings_due": sum(int(row["listings_due"]) for row in sites),
        "skipped_not_configured": skipped,
        "not_polled": not_polled,
        "last_poll_run": last_poll,
        "last_autoconfigure_run": last_auto,
        "exclusions": [entry for entry in entries if entry["outcome"] != OUTCOME_CONFIGURED],
        "configured": [entry for entry in entries if entry["outcome"] == OUTCOME_CONFIGURED],
        "coverage": coverage,
    }


def _last_poll_run(tenant_id: str, run_store) -> dict[str, Any] | None:
    """The latest poll run, cut to this tenant (the poll covers every tenant)."""
    record = load_run_state(RUN_POLL, store=run_store)
    if not record:
        return None
    mine = [e for e in record.get("not_configured_sites") or [] if e.get("tenant_id") == tenant_id]
    return {
        "finished_at": record.get("finished_at"),
        "stopped_reason": record.get("stopped_reason"),
        "not_configured_sites": mine,
        "listings_not_polled": sum(int(e.get("listings") or 0) for e in mine),
    }


def _last_autoconfigure_run(tenant_id: str, run_store) -> dict[str, Any] | None:
    record = load_run_state(run_state_key_autoconfigure(tenant_id), store=run_store)
    if not record or record.get("tenant_id") != tenant_id:
        return None
    return record


def _advisory_lock(session: Session) -> None:
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:namespace), 0)"),
        {"namespace": LOCK_NAMESPACE},
    )


def _tenant_ids(session: Session, tenant_id: str | None) -> list[str]:
    if tenant_id is not None:
        return [str(tenant_id)]
    rows = session.scalars(
        select(DimCustomer.tenant_id)
        .join(CustomerReportConfig, CustomerReportConfig.customer_id == DimCustomer.id)
        .where(CustomerReportConfig.reports_expected.is_(True))
        .distinct()
    ).all()
    return sorted({str(row) for row in rows if row})


def _configure_tenant(
    session: Session,
    tenant_id: str,
    *,
    http_get: _HttpGet | None,
    apply: bool = True,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for config, customer in _reporting_customers(session, tenant_id):
        if str(customer.tenant_id) != tenant_id:
            continue
        try:
            with session.begin_nested():
                customer_entries = _configure_customer(
                    session,
                    tenant_id=tenant_id,
                    customer=customer,
                    seed=_seed(config),
                    http_get=http_get,
                    apply=apply,
                )
        except SellerSeedError as exc:
            logger.info("listing autoconfigure: customer %s rejected seller seed: %s", customer.id, exc)
            entries.append(
                _entry(
                    customer_id=int(customer.id),
                    tenant_id=tenant_id,
                    site_key=None,
                    outcome=OUTCOME_EXCLUDED,
                    reason=REASON_SELLER_SEED,
                    reasons=[REASON_SELLER_SEED],
                )
            )
            continue
        except Exception:
            logger.exception("listing autoconfigure: customer %s failed", customer.id)
            entries.append(
                _entry(
                    customer_id=int(customer.id),
                    tenant_id=tenant_id,
                    site_key=None,
                    outcome=OUTCOME_EXCLUDED,
                    reason=REASON_FAILED,
                    reasons=[REASON_FAILED],
                )
            )
            continue
        entries.extend(customer_entries)
    return entries


def _reporting_customers(session: Session, tenant_id: str) -> list[tuple[CustomerReportConfig, DimCustomer]]:
    rows = session.execute(
        select(CustomerReportConfig, DimCustomer)
        .join(DimCustomer, DimCustomer.id == CustomerReportConfig.customer_id)
        .where(
            CustomerReportConfig.reports_expected.is_(True),
            DimCustomer.tenant_id == tenant_id,
        )
        .order_by(DimCustomer.id)
    ).all()
    return [(cfg, cust) for cfg, cust in rows if isinstance(cust, DimCustomer)]


def _configure_customer(
    session: Session,
    *,
    tenant_id: str,
    customer: DimCustomer,
    seed: dict[str, Any],
    http_get: _HttpGet | None,
    apply: bool,
) -> list[dict[str, Any]]:
    keys = _site_keys(session, tenant_id=tenant_id, customer_id=int(customer.id), seed=seed)
    if not keys:
        return [
            _entry(
                customer_id=int(customer.id),
                tenant_id=tenant_id,
                site_key=None,
                outcome=OUTCOME_EXCLUDED,
                reason=REASON_NO_SITE_KEY,
                reasons=[REASON_NO_SITE_KEY],
            )
        ]
    entries: list[dict[str, Any]] = []
    for key in keys:
        entries.append(
            _configure_site(
                session,
                tenant_id=tenant_id,
                customer=customer,
                site_key=key,
                seed=seed,
                http_get=http_get,
                apply=apply,
            )
        )
    return entries


def _configure_site(
    session: Session,
    *,
    tenant_id: str,
    customer: DimCustomer,
    site_key: str,
    seed: dict[str, Any],
    http_get: _HttpGet | None,
    apply: bool,
) -> dict[str, Any]:
    listings = _listings(session, tenant_id=tenant_id, customer_id=int(customer.id), site_key=site_key)
    urls = [str(row.url).strip() for row in listings if str(row.url or "").strip()]
    derived = derive_listing_url_pattern(urls) if urls else None
    if derived is not None:
        pattern_status = "derived"
    elif len(urls) >= 2:
        pattern_status = "mixed"
    else:
        pattern_status = "none"
    row = _load_site(session, tenant_id, site_key)
    probe: dict[str, Any] | None = None

    if apply:
        if row is None:
            display = _display_name(seed, site_key)
            try:
                row = create_site(
                    session,
                    tenant_id=tenant_id,
                    site_key=site_key,
                    fields={"display_name": display},
                    actor=AUTOCONFIG_ACTOR,
                )
            except ValueError as exc:
                if "already exists" not in str(exc):
                    raise
                row = _load_site(session, tenant_id, site_key)
        if row is not None:
            probe = _html_probe(
                session,
                tenant_id=tenant_id,
                listings=listings,
                http_get=http_get,
                adapter_blank=_is_blank(row.adapter_key),
            )
            probe_ok = bool(probe["corroborated"])
            fill = _fill_fields(row, seed=seed, derived=derived, probe_ok=probe_ok)
            _apply_fill(session, row, fill)
            _ensure_seller(session, row, customer=customer, seed=seed)
            session.refresh(row)

    seller_known = _seller_known(row, customer, seed)
    configured = bool(row is not None and row.is_active and configured_adapter(site_config_from_row(row)) is not None)
    reasons: list[str] = []
    if not configured:
        reasons.append(REASON_NEEDS_PATTERN)
    if not seller_known:
        reasons.append(REASON_NO_SELLER)
    if not reasons:
        outcome, reason = OUTCOME_CONFIGURED, None
    elif reasons == [REASON_NO_SELLER]:
        outcome, reason = OUTCOME_EXCLUDED, REASON_NO_SELLER
    elif reasons == [REASON_NEEDS_PATTERN]:
        outcome, reason = OUTCOME_NEEDS_PATTERN, REASON_NEEDS_PATTERN
    else:
        # Both gaps. ``reason`` stays unset so one field cannot hide the other.
        outcome, reason = OUTCOME_NEEDS_PATTERN, None
    return _entry(
        customer_id=int(customer.id),
        tenant_id=tenant_id,
        site_key=site_key,
        outcome=outcome,
        reason=reason,
        reasons=reasons,
        site_id=int(row.id) if row is not None and row.id is not None else None,
        pattern_status=pattern_status,
        probe=probe,
    )


def _site_keys(session: Session, *, tenant_id: str, customer_id: int, seed: dict[str, Any]) -> list[str]:
    named = seed.get("marketplace")
    if isinstance(named, str) and named.strip():
        key = named.strip().lower()
        return [key] if SITE_KEY_RE.match(key) else []
    found = session.scalars(
        select(func.lower(func.trim(CustomerListing.marketplace)))
        .join(DimCustomer, DimCustomer.id == CustomerListing.customer_id)
        .where(
            DimCustomer.tenant_id == tenant_id,
            CustomerListing.customer_id == int(customer_id),
        )
        .distinct()
    ).all()
    keys = sorted({str(value) for value in found if isinstance(value, str) and SITE_KEY_RE.match(value)})
    return keys


def _listings(session: Session, *, tenant_id: str, customer_id: int, site_key: str) -> list[CustomerListing]:
    rows = session.scalars(
        select(CustomerListing)
        .join(DimCustomer, DimCustomer.id == CustomerListing.customer_id)
        .where(
            DimCustomer.tenant_id == tenant_id,
            CustomerListing.customer_id == int(customer_id),
            func.lower(func.trim(CustomerListing.marketplace)) == site_key,
        )
        .order_by(CustomerListing.id)
    ).all()
    return [row for row in rows if isinstance(row, CustomerListing)]


def _load_site(session: Session, tenant_id: str, site_key: str) -> ListingSite | None:
    row = session.scalar(
        select(ListingSite)
        .where(ListingSite.tenant_id == tenant_id, ListingSite.site_key == site_key)
        .options(selectinload(ListingSite.sellers))
    )
    return row if isinstance(row, ListingSite) else None


PROBE_CORROBORATED = "corroborated"
PROBE_NOT_NEEDED = "adapter_already_set"
PROBE_NO_FETCH = "no_live_fetch"
PROBE_NO_LISTING = "no_listing_with_product_and_url"
PROBE_NO_PRODUCT = "product_not_found"
PROBE_FETCH_ERROR = "fetch_error"
PROBE_HTTP_STATUS = "http_status_not_200"
PROBE_EMPTY_BODY = "empty_body"
PROBE_NO_MATCH = "no_barcode_or_model_match"


def _probe(
    reason: str,
    *,
    status: int | None = None,
    listing_id: int | None = None,
    detail: str | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "corroborated": reason == PROBE_CORROBORATED,
        "reason": reason,
        "status": status,
        "listing_id": listing_id,
    }
    if detail:
        out["detail"] = detail[:200]
    return out


def _html_probe(
    session: Session,
    *,
    tenant_id: str,
    listings: list[CustomerListing],
    http_get: _HttpGet | None,
    adapter_blank: bool,
) -> dict[str, Any]:
    """One stored-URL read plus the same identity corroboration the link learner uses.

    A page corroborates when its gtin/mpn/model equals the product. A stock code does not.
    Returns the outcome (``corroborated``, ``reason``, HTTP ``status``) so a site that stays
    unconfigured says why.
    """
    from app.services.listing_capture.observation import listing_live_fetch_enabled

    if not adapter_blank:
        return _probe(PROBE_NOT_NEEDED)
    if http_get is None or not listing_live_fetch_enabled():
        return _probe(PROBE_NO_FETCH)
    listing = next((row for row in listings if row.product_id and str(row.url or "").strip()), None)
    if listing is None:
        return _probe(PROBE_NO_LISTING)
    lid = int(listing.id) if listing.id is not None else None
    product = session.scalar(
        select(DimProduct).where(
            DimProduct.id == int(listing.product_id),
            DimProduct.tenant_id == tenant_id,
        )
    )
    if not isinstance(product, DimProduct):
        return _probe(PROBE_NO_PRODUCT, listing_id=lid)
    try:
        status, body = http_get(str(listing.url))
    except (OSError, ValueError, RuntimeError) as exc:
        return _probe(PROBE_FETCH_ERROR, listing_id=lid, detail=type(exc).__name__)
    code = int(status or 0)
    if code != 200:
        return _probe(PROBE_HTTP_STATUS, status=code, listing_id=lid)
    if not body:
        return _probe(PROBE_EMPTY_BODY, status=code, listing_id=lid)
    if corroboration(page_facts_from_html(body), product) in {"barcode", "model"}:
        return _probe(PROBE_CORROBORATED, status=code, listing_id=lid)
    return _probe(PROBE_NO_MATCH, status=code, listing_id=lid)


def _fill_fields(
    row: ListingSite,
    *,
    seed: dict[str, Any],
    derived: Any,
    probe_ok: bool,
) -> dict[str, Any]:
    curated = seed.get("site") if isinstance(seed.get("site"), dict) else {}
    fill: dict[str, Any] = {}

    def take(name: str, value: Any) -> None:
        if name in fill or name not in _FILLABLE or not _is_blank(getattr(row, name)):
            return
        if value is None or (isinstance(value, str) and not value.strip()):
            return
        fill[name] = value.strip() if isinstance(value, str) else value

    for name in _FILLABLE:
        if name == "adapter_key":
            continue
        if name in curated:
            take(name, curated.get(name))
    if derived is not None:
        take("product_url_pattern", derived.product_url_pattern)
        take("page_id_pattern", derived.page_id_pattern)
    if _is_blank(row.adapter_key):
        if probe_ok:
            take("adapter_key", HTML_PAGE_ADAPTER)
        else:
            curated_adapter = curated.get("adapter_key")
            if isinstance(curated_adapter, str) and curated_adapter.strip():
                trial = dict(fill)
                trial["adapter_key"] = curated_adapter.strip()
                if _configured_after(row, trial):
                    take("adapter_key", curated_adapter)
    return fill


def _configured_after(row: ListingSite, fill: dict[str, Any]) -> bool:
    def pick(name: str) -> Any:
        if name in fill:
            return fill[name]
        return getattr(row, name)

    rate = pick("rate_limit_seconds")
    try:
        rate_value = float(rate) if rate is not None and str(rate).strip() != "" else None
    except (TypeError, ValueError):
        rate_value = None
    config = SiteConfig(
        site_key=str(row.site_key),
        display_name=str(pick("display_name") or row.site_key),
        adapter_key=(str(pick("adapter_key")).strip() or None) if pick("adapter_key") else None,
        product_url_pattern=_text_or_none(pick("product_url_pattern")),
        page_id_pattern=_text_or_none(pick("page_id_pattern")),
        search_url_pattern=_text_or_none(pick("search_url_pattern")),
        details_url_pattern=_text_or_none(pick("details_url_pattern")),
        first_party_seller=_text_or_none(pick("first_party_seller")),
        rate_limit_seconds=rate_value,
        is_active=bool(row.is_active),
        id=int(row.id) if row.id is not None else None,
        tenant_id=str(row.tenant_id or ""),
    )
    return configured_adapter(config) is not None


def _apply_fill(session: Session, row: ListingSite, fill: dict[str, Any]) -> None:
    if not fill:
        return
    try:
        update_site(session, row, fields=fill, actor=AUTOCONFIG_ACTOR)
        return
    except ValueError:
        logger.info("listing autoconfigure: site %s rejected a combined fill", row.site_key)
    for name, value in fill.items():
        if name == "adapter_key" or not _is_blank(getattr(row, name)):
            continue
        try:
            update_site(session, row, fields={name: value}, actor=AUTOCONFIG_ACTOR)
        except ValueError:
            continue
    if "adapter_key" in fill and _is_blank(row.adapter_key) and _configured_after(row, {"adapter_key": fill["adapter_key"]}):
        try:
            update_site(session, row, fields={"adapter_key": fill["adapter_key"]}, actor=AUTOCONFIG_ACTOR)
        except ValueError:
            return


def _site_adapter(row: ListingSite | None, seed: dict[str, Any]) -> str:
    if row is not None and not _is_blank(row.adapter_key):
        return str(row.adapter_key).strip()
    site = seed.get("site") if isinstance(seed.get("site"), dict) else {}
    raw = site.get("adapter_key")
    return str(raw).strip() if isinstance(raw, str) else ""


def _is_customer_own_site(row: ListingSite | None, seed: dict[str, Any]) -> bool:
    """The general HTML reader is the customer's own site. A buy-box site is not."""
    return _site_adapter(row, seed) == HTML_PAGE_ADAPTER


def _seller_names_for_customer(
    customer: DimCustomer,
    row: ListingSite | None,
    seed: dict[str, Any],
) -> tuple[list[str], list[str], bool]:
    """Seed names win. An existing first-party name wins over the inferred customer name,
    unless another customer already has a seller identity on the site (the first-party name
    is site-wide and may be that customer's)."""
    names, ids = _seed_seller(seed)
    if names or ids:
        return names, ids, False
    if _is_customer_own_site(row, seed):
        existing = str(getattr(row, "first_party_seller", "") or "").strip() if row is not None else ""
        if existing and not _other_seller_present(row, int(customer.id)):
            return [existing], [], False
        name = str(getattr(customer, "name", "") or "").strip()
        if name:
            return [name], [], True
    return [], [], False


def _ensure_seller(session: Session, row: ListingSite, *, customer: DimCustomer, seed: dict[str, Any]) -> None:
    """A stored seller identity for this customer is kept: the seed is not read and nothing
    is inferred or written. The customer name fills a blank first-party name only when no
    other customer has a seller identity on the site."""
    if _seller_present(row, int(customer.id)):
        return
    names, ids, from_customer = _seller_names_for_customer(customer, row, seed)
    if not names and not ids:
        return
    set_site_seller(
        session,
        row,
        customer_id=int(customer.id),
        seller_names=names,
        seller_ids=ids,
        actor=INFERRED_SELLER_ACTOR if from_customer else AUTOCONFIG_ACTOR,
    )
    shared = _other_seller_present(row, int(customer.id))
    if from_customer and _is_blank(row.first_party_seller) and not shared:
        try:
            update_site(session, row, fields={"first_party_seller": names[0]}, actor=AUTOCONFIG_ACTOR)
        except ValueError:
            logger.info("listing autoconfigure: site %s rejected the discovered seller", row.site_key)


def _seller_known(row: ListingSite | None, customer: DimCustomer, seed: dict[str, Any]) -> bool:
    """Stored seller row, seed names, or the customer's own name on their site."""
    if _seller_present(row, int(customer.id)):
        return True
    names, ids, _from_customer = _seller_names_for_customer(customer, row, seed)
    return any(str(value or "").strip() for value in names) or any(str(value or "").strip() for value in ids)


def _seller_present(row: ListingSite | None, customer_id: int) -> bool:
    if row is None:
        return False
    for seller in row.sellers or []:
        if int(seller.customer_id) != int(customer_id):
            continue
        names = [str(value).strip() for value in (seller.seller_names or []) if str(value or "").strip()]
        ids = [str(value).strip() for value in (seller.seller_ids or []) if str(value or "").strip()]
        if names or ids:
            return True
    return False


def _other_seller_present(row: ListingSite | None, customer_id: int) -> bool:
    """Another customer has a seller name or id on this site."""
    if row is None:
        return False
    others = {int(s.customer_id) for s in (row.sellers or [])} - {int(customer_id)}
    return any(_seller_present(row, other) for other in others)


def _seed(config: CustomerReportConfig) -> dict[str, Any]:
    profile = config.feed_profile_json if isinstance(config.feed_profile_json, dict) else {}
    seed = profile.get("listing_seed")
    return dict(seed) if isinstance(seed, dict) else {}


class SellerSeedError(ValueError):
    """Seller names or ids are not a string or a list of strings."""


def _seller_values(value: Any) -> list[str]:
    """A string is one seller value. Lists are stripped. Empty values are dropped."""
    if value is None:
        return []
    if isinstance(value, str):
        items: list[Any] = [value]
    elif isinstance(value, (list, tuple)):
        items = list(value)
    else:
        raise SellerSeedError("seller field must be a string or a list")
    cleaned: list[str] = []
    for item in items:
        if item is None:
            continue
        if not isinstance(item, str):
            raise SellerSeedError("seller field must be a string or a list")
        text = item.strip()
        if text:
            cleaned.append(text)
    return cleaned


def _seed_seller(seed: dict[str, Any]) -> tuple[list[str], list[str]]:
    block = seed.get("seller") if isinstance(seed.get("seller"), dict) else {}
    site = seed.get("site") if isinstance(seed.get("site"), dict) else {}
    names = seed.get("seller_names")
    if names is None:
        names = block.get("names", block.get("seller_names"))
    if names is None:
        names = site.get("seller_names")
    ids = seed.get("seller_ids")
    if ids is None:
        ids = block.get("ids", block.get("seller_ids"))
    if ids is None:
        ids = site.get("seller_ids")
    return _seller_values(names), _seller_values(ids)


def _display_name(seed: dict[str, Any], site_key: str) -> str:
    site = seed.get("site") if isinstance(seed.get("site"), dict) else {}
    label = site.get("display_name")
    if isinstance(label, str) and label.strip():
        return label.strip()[:128]
    return site_key


def _site_health(session: Session, tenant_id: str) -> list[dict[str, Any]]:
    site_rows = list(
        session.scalars(
            select(ListingSite)
            .where(ListingSite.tenant_id == tenant_id)
            .options(selectinload(ListingSite.sellers))
            .order_by(ListingSite.site_key)
        ).all()
    )
    site_rows = [row for row in site_rows if isinstance(row, ListingSite)]
    status_params = {f"status_{index}": status for index, status in enumerate(POLLED_LISTING_STATUSES)}
    status_sql = ", ".join(f":status_{index}" for index in range(len(POLLED_LISTING_STATUSES)))
    due_by_key = {
        str(key): int(count or 0)
        for key, count in session.execute(
            text(
                f"""
                SELECT lower(trim(l.marketplace)) AS site_key,
                       count(*) FILTER (WHERE l.status IN ({status_sql})) AS due
                FROM customer_listing l
                JOIN dim_customer c ON c.id = l.customer_id
                WHERE c.tenant_id = :tenant_id
                GROUP BY 1
                """
            ),
            {"tenant_id": tenant_id, **status_params},
        ).all()
        if key
    }
    newest_by_key: dict[str, Any] = {}
    for key, fetched_at, status, price in session.execute(
        text(
            """
            SELECT DISTINCT ON (lower(trim(l.marketplace)))
                   lower(trim(l.marketplace)) AS site_key,
                   o.fetched_at,
                   o.parse_status,
                   o.extracted_price
            FROM listing_observation o
            JOIN customer_listing l ON l.id = o.listing_id
            JOIN dim_customer c ON c.id = l.customer_id
            WHERE c.tenant_id = :tenant_id
            ORDER BY lower(trim(l.marketplace)), o.fetched_at DESC
            """
        ),
        {"tenant_id": tenant_id},
    ).all():
        if not key:
            continue
        newest_by_key[str(key)] = {
            "fetched_at": fetched_at.isoformat() if fetched_at is not None else None,
            "status": status,
            "price": float(price) if price is not None else None,
        }
    keys = sorted(set(due_by_key) | {row.site_key for row in site_rows} | set(newest_by_key))
    by_key = {row.site_key: row for row in site_rows}
    out: list[dict[str, Any]] = []
    for key in keys:
        row = by_key.get(key)
        config = site_config_from_row(row) if row is not None else None
        configured = bool(
            row is not None and row.is_active and configured_adapter(config) is not None
        )
        due = int(due_by_key.get(key, 0))
        out.append(
            {
                "site_id": int(row.id) if row is not None else None,
                "site_key": key,
                "configured": configured,
                "missing_fields": [] if configured else not_configured_reason(config),
                "newest_observation": newest_by_key.get(key),
                "listings_due": due,
                "skipped_not_configured": 0 if configured else due,
            }
        )
    return out


def _entry(
    *,
    customer_id: int,
    tenant_id: str,
    site_key: str | None,
    outcome: str,
    reason: str | None,
    reasons: list[str] | None = None,
    site_id: int | None = None,
    pattern_status: str | None = None,
    probe: dict[str, Any] | None = None,
) -> dict[str, Any]:
    listed = list(reasons) if reasons is not None else ([reason] if reason else [])
    return {
        "customer_id": customer_id,
        "tenant_id": tenant_id,
        "site_key": site_key,
        "site_id": site_id,
        "outcome": outcome,
        "reason": reason,
        "reasons": listed,
        "pattern_status": pattern_status,
        "probe": probe,
    }


def _bucket(entries: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    ordered = sorted(entries, key=lambda entry: (entry["tenant_id"], entry["customer_id"], entry["site_key"] or ""))
    configured: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    needs_pattern: list[dict[str, Any]] = []
    for entry in ordered:
        reasons = entry.get("reasons") or []
        if entry["outcome"] == OUTCOME_CONFIGURED and not reasons:
            configured.append(entry)
            continue
        if REASON_NO_SELLER in reasons or entry["outcome"] == OUTCOME_EXCLUDED:
            excluded.append(entry)
        if REASON_NEEDS_PATTERN in reasons or entry["outcome"] == OUTCOME_NEEDS_PATTERN:
            needs_pattern.append(entry)
    return {
        "configured": configured,
        "excluded": excluded,
        "needs_pattern": needs_pattern,
    }


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text_value = str(value).strip()
    return text_value or None
