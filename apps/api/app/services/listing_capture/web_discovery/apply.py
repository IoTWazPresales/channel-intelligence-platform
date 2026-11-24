"""Apply: save what the user reviewed in a Preview, and the steward's decisions on site candidates.

Apply loads the stored plan and writes it in one transaction. It does not recompute: it must save
exactly what the user saw, a recompute would repeat minutes of polite network traffic and could
answer differently, and without network it runs quickly inside the API request.

Safeguards:

1. The plan stores a settings fingerprint. A mismatch is ``settings_changed`` (409).
2. Each item is re-validated against the current database before it is written. A stale item is
   skipped and reported as ``changed_since_preview``.
3. The decision is re-derived from the stored evidence with the same pure ``scoring.decide``, after
   the parts the database can answer (the customer's name keys, the domain's name part and
   ending, the country evidence, the product hits) are recomputed. An item whose re-derived
   outcome differs from the stored one is skipped, so an edited plan cannot raise an item to an
   automatic write.
4. An expired plan is ``preview_expired`` (410); one that has not finished is ``preview_not_done``.

A second Apply on the same preview returns the stored result and writes nothing. The advisory lock,
the unique key ``uq_customer_web_site_tenant_customer_domain`` and the re-validation make a race
harmless.

Pages and unlinked listings use the S4 writers in ``link_apply`` in this same transaction.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.customer_web_site import (
    WEB_SITE_CONFIRMED,
    WEB_SITE_PROPOSED,
    WEB_SITE_REJECTED,
    WEB_SOURCE_AUTO,
    WEB_SOURCE_STEWARD,
    WEB_SOURCE_USER,
    CustomerWebSite,
)
from app.models.dimensions import DimCustomer, DimProduct
from app.models.listing_site import ListingSite
from app.services.listing_capture import discovery
from app.services.listing_capture.sites import SITE_KEY_RE, create_site
from app.services.listing_capture.web_discovery.homepage import HomeSignals
from app.services.listing_capture.web_discovery.link_apply import apply_link_items
from app.services.listing_capture.web_discovery.preview import STATUS_DONE, PlanStore
from app.services.listing_capture.web_discovery.scoring import (
    OUTCOME_AUTO,
    OUTCOME_QUEUE,
    OUTCOME_USER,
    SOURCE_USER,
    country_match,
    decide,
    homepage_match,
    matched_ending,
    name_match,
    normalize_host,
)
from app.services.listing_capture.web_discovery.settings import DiscoverySettings, load_discovery_settings
from app.services.steward_audit import record_steward_audit_sync

ACTOR = "listing-discovery-v2"
SKIP_CHANGED = "changed_since_preview"
MAX_SITE_KEY_LENGTH = 32
MAX_DISPLAY_NAME_LENGTH = 128


class ApplyError(Exception):
    """Apply refused. ``code`` is stable for the API; ``status_code`` is the HTTP status."""

    def __init__(self, code: str, status_code: int, message: str = "") -> None:
        self.code = code
        self.status_code = status_code
        super().__init__(message or code)


def empty_counts() -> dict[str, Any]:
    return {
        "sites_confirmed": 0,
        "sites_queued": 0,
        "sites_created": 0,
        "pages_linked": 0,
        "proposals_created": 0,
        "pages_queued": 0,
        "listings_linked": 0,
        "listings_queued": 0,
        "auto_links": [],
        "skipped": [],
    }


def _actor(user: dict | None) -> str:
    if not user:
        return ACTOR
    return str(user.get("email") or user.get("id") or ACTOR)[:256]


# --------------------------------------------------------------------------- site rows


def unique_site_key(base: str, taken: set[str]) -> str:
    """``base``, or ``base-2``, ``base-3``. (within 32 characters) when ``base`` is taken."""
    base = base[:MAX_SITE_KEY_LENGTH].strip("-")
    if base not in taken:
        return base
    n = 2
    while True:
        suffix = f"-{n}"
        candidate = base[: MAX_SITE_KEY_LENGTH - len(suffix)].strip("-") + suffix
        if candidate not in taken:
            return candidate
        n += 1


def find_site_for_host(session: Session, tenant_id: str, host: str) -> ListingSite | None:
    """A listing site whose stored URL patterns use this host (the check ``_site_keys`` makes), else the
    site an earlier confirmed ``customer_web_site`` row for this host already points at (a site made
    here has no URL patterns yet, so a second customer on the same host must reuse it)."""
    for site in session.scalars(
        select(ListingSite).where(ListingSite.tenant_id == tenant_id).order_by(ListingSite.id)
    ).all():
        for field_name in ("product_url_pattern", "search_url_pattern", "details_url_pattern"):
            if normalize_host(discovery._domain(getattr(site, field_name, None))) == host:  # noqa: SLF001
                return site
    return session.scalar(
        select(ListingSite)
        .join(CustomerWebSite, CustomerWebSite.site_id == ListingSite.id)
        .where(
            CustomerWebSite.tenant_id == tenant_id,
            CustomerWebSite.domain == host,
            CustomerWebSite.status == WEB_SITE_CONFIRMED,
            ListingSite.tenant_id == tenant_id,
        )
        .order_by(CustomerWebSite.id)
        .limit(1)
    )


def _display_name(evidence: dict[str, Any], host: str) -> str:
    org = str((evidence.get("homepage") or {}).get("org_name") or "").strip()
    return (org or host)[:MAX_DISPLAY_NAME_LENGTH]


def ensure_site(
    session: Session, *, tenant_id: str, host: str, evidence: dict[str, Any], actor: str
) -> tuple[ListingSite | None, bool]:
    """The listing site for ``host``: an existing one, or a new one. ``(site, created)``; None when
    no valid site key can be made from the host."""
    existing = find_site_for_host(session, tenant_id, host)
    if existing is not None:
        return existing, False
    base = discovery._site_key_from_origin(f"https://{host}")  # noqa: SLF001
    if not base or not SITE_KEY_RE.match(base):
        return None, False
    taken = {
        str(key)
        for key in session.scalars(select(ListingSite.site_key).where(ListingSite.tenant_id == tenant_id)).all()
    }
    site = create_site(
        session,
        tenant_id=tenant_id,
        site_key=unique_site_key(base, taken),
        fields={"display_name": _display_name(evidence, host)},
        actor=actor,
    )
    return site, True


def _existing_row(session: Session, tenant_id: str, customer_id: int, domain: str) -> CustomerWebSite | None:
    return session.scalar(
        select(CustomerWebSite).where(
            CustomerWebSite.tenant_id == tenant_id,
            CustomerWebSite.customer_id == int(customer_id),
            CustomerWebSite.domain == domain,
        )
    )


def confirm_web_site(
    session: Session,
    *,
    tenant_id: str,
    customer_id: int,
    domain: str,
    evidence: dict[str, Any],
    source: str,
    preview_id: str | None,
    actor: str,
    now: datetime,
) -> tuple[CustomerWebSite | None, bool]:
    """Make the site and the confirmed ``customer_web_site`` row. ``(row, site_created)``."""
    site, created = ensure_site(session, tenant_id=tenant_id, host=domain, evidence=evidence, actor=actor)
    if site is None:
        return None, False
    row = _existing_row(session, tenant_id, customer_id, domain)
    if row is None:
        row = CustomerWebSite(tenant_id=tenant_id, customer_id=int(customer_id), domain=domain, evidence={})
    row.site_id = int(site.id)
    row.status = WEB_SITE_CONFIRMED
    row.source = source
    row.evidence = evidence
    row.preview_id = preview_id
    row.decided_by = actor
    row.decided_at = now
    session.add(row)
    session.flush()
    return row, created


# --------------------------------------------------------------------------- re-validation


def rederive_evidence(
    session: Session, tenant_id: str, customer: DimCustomer, entry: dict[str, Any], settings: DiscoverySettings
) -> dict[str, Any]:
    """The stored evidence with every part the database or the settings can answer recomputed."""
    stored = dict(entry.get("evidence") or {})
    host = normalize_host(str(entry.get("domain") or ""))
    home = HomeSignals.from_dict(stored.get("home_signals")) if stored.get("home_signals") else None
    names = name_match(host, customer.name, settings.domain_endings)
    homepage = dict(stored.get("homepage") or {})
    homepage["match"] = homepage_match(home, names["customer_keys"])["match"]
    hit_ids = [
        int(h["product_id"]) for h in stored.get("product_search_hits") or [] if isinstance(h, dict) and h.get("product_id") is not None
    ]
    valid_ids = set()
    if hit_ids:
        valid_ids = {
            int(pid)
            for pid in session.scalars(
                select(DimProduct.id).where(DimProduct.tenant_id == tenant_id, DimProduct.id.in_(hit_ids))
            ).all()
        }
    stored.update(
        {
            "name_match": names,
            "ending_match": matched_ending(host, settings.domain_endings),
            "country_match": country_match(host, settings.domain_endings, settings.country, home),
            "homepage": homepage,
            "product_search_hits": [
                h for h in stored.get("product_search_hits") or [] if isinstance(h, dict) and h.get("product_id") in valid_ids
            ],
        }
    )
    return stored


def _apply_candidate(
    session: Session,
    *,
    tenant_id: str,
    customer: DimCustomer,
    entry: dict[str, Any],
    settings: DiscoverySettings,
    preview_id: str,
    actor: str,
    now: datetime,
    counts: dict[str, Any],
) -> None:
    item_id = str(entry.get("item_id") or "")
    stored_outcome = entry.get("outcome")
    if stored_outcome not in (OUTCOME_AUTO, OUTCOME_USER, OUTCOME_QUEUE):
        return  # nothing to save for monitored, rejected or dropped items
    domain = normalize_host(str(entry.get("domain") or ""))
    if not domain:
        counts["skipped"].append({"item_id": item_id, "reason": SKIP_CHANGED})
        return
    evidence = rederive_evidence(session, tenant_id, customer, entry, settings)
    user_entered = SOURCE_USER in (evidence.get("sources") or [])
    existing = _existing_row(session, tenant_id, int(customer.id), domain)
    rejected = existing is not None and existing.status == WEB_SITE_REJECTED and not user_entered
    monitored = existing is not None and existing.status == WEB_SITE_CONFIRMED
    derived = decide(evidence, user_entered=user_entered, rejected=rejected, already_monitored=monitored)
    if derived != stored_outcome:
        counts["skipped"].append({"item_id": item_id, "reason": SKIP_CHANGED})
        return
    try:
        with session.begin_nested():
            if derived == OUTCOME_USER:
                row, created = confirm_web_site(
                    session,
                    tenant_id=tenant_id,
                    customer_id=int(customer.id),
                    domain=domain,
                    evidence=evidence,
                    source=WEB_SOURCE_USER,
                    preview_id=preview_id,
                    actor=actor,
                    now=now,
                )
                if row is None:
                    counts["skipped"].append({"item_id": item_id, "reason": SKIP_CHANGED})
                    return
                counts["sites_confirmed"] += 1
                counts["sites_created"] += 1 if created else 0
            elif derived in (OUTCOME_AUTO, OUTCOME_QUEUE):
                if existing is not None and existing.status != WEB_SITE_PROPOSED:
                    counts["skipped"].append({"item_id": item_id, "reason": SKIP_CHANGED})
                    return
                row = existing or CustomerWebSite(
                    tenant_id=tenant_id, customer_id=int(customer.id), domain=domain, evidence={}
                )
                row.status = WEB_SITE_PROPOSED
                row.source = WEB_SOURCE_AUTO
                row.evidence = evidence
                row.preview_id = preview_id
                session.add(row)
                session.flush()
                counts["sites_queued"] += 1
    except IntegrityError:
        counts["skipped"].append({"item_id": item_id, "reason": SKIP_CHANGED})


# --------------------------------------------------------------------------- apply a plan


def apply_plan(
    session: Session,
    plan_store: PlanStore,
    *,
    tenant_id: str,
    preview_id: str,
    user: dict | None,
    now: datetime | None = None,
    sites_only: bool = False,
) -> dict[str, Any]:
    """Write the plan. Commits the session, then stores the result in the plan. Raises ``ApplyError``."""
    plan = plan_store.load(tenant_id, preview_id)
    if plan is None:
        raise ApplyError("preview_expired", 410, "This preview has expired. Run it again.")
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"wd_apply:{preview_id}"}
    )
    # Another Apply may have finished while this one waited for the lock.
    plan = plan_store.load(tenant_id, preview_id) or plan
    if plan.get("tenant_id") != tenant_id or plan.get("preview_id") != preview_id:
        raise ApplyError("preview_expired", 410, "This preview is not available.")
    if plan.get("applied"):
        return dict(plan["applied"])
    if plan.get("status") != STATUS_DONE or not isinstance(plan.get("result"), dict):
        raise ApplyError("preview_not_done", 409, "This preview has not finished.")
    settings = load_discovery_settings(session, tenant_id)
    if settings.fingerprint() != plan.get("settings_fingerprint"):
        raise ApplyError("settings_changed", 409, "Discovery settings changed after this preview. Run it again.")

    moment = now or datetime.now(UTC)
    actor = _actor(user)
    counts = empty_counts()
    for block in plan["result"].get("customers") or []:
        customer = session.get(DimCustomer, int(block["customer_id"]))
        if (
            not isinstance(customer, DimCustomer)
            or str(customer.tenant_id) != tenant_id
            or customer.merged_into_customer_id is not None
        ):
            for entry in block.get("candidates") or []:
                if entry.get("outcome") in (OUTCOME_AUTO, OUTCOME_USER, OUTCOME_QUEUE):
                    counts["skipped"].append({"item_id": str(entry.get("item_id") or ""), "reason": SKIP_CHANGED})
            continue
        for entry in block.get("candidates") or []:
            _apply_candidate(
                session,
                tenant_id=tenant_id,
                customer=customer,
                entry=entry,
                settings=settings,
                preview_id=preview_id,
                actor=actor,
                now=moment,
                counts=counts,
            )
    if not sites_only:
        apply_link_items(
            session,
            tenant_id=tenant_id,
            preview_id=preview_id,
            result=plan["result"],
            actor=actor,
            counts=counts,
        )

    record_steward_audit_sync(
        user,
        action="discovery_apply",
        importer="listing_discovery",
        payload={"preview_id": preview_id, "counts": {k: v for k, v in counts.items() if k != "skipped"}, "skipped": len(counts["skipped"])},
        db=session,
    )
    session.commit()
    plan["applied"] = {**counts, "applied_at": moment.isoformat()}
    plan_store.save(tenant_id, preview_id, plan)
    return dict(plan["applied"])


# --------------------------------------------------------------------------- site candidate queue


def list_site_candidates(session: Session, tenant_id: str, status: str = WEB_SITE_PROPOSED) -> list[dict[str, Any]]:
    rows = session.execute(
        select(CustomerWebSite, DimCustomer.name)
        .join(DimCustomer, DimCustomer.id == CustomerWebSite.customer_id)
        .where(CustomerWebSite.tenant_id == tenant_id, CustomerWebSite.status == status)
        .order_by(CustomerWebSite.id)
    ).all()
    return [
        {
            "id": int(row.id),
            "customer_id": int(row.customer_id),
            "customer_name": str(name or ""),
            "domain": row.domain,
            "evidence": row.evidence or {},
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row, name in rows
    ]


def decide_site_candidate(
    session: Session,
    *,
    tenant_id: str,
    candidate_id: int,
    action: str,
    user: dict | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """A steward's confirm or reject. Confirm runs the same site write as Apply (source ``steward``).

    Reject is allowed on a proposed or a confirmed row; it never deletes a listing site or a
    listing, it only stops future proposals and discovery for that customer.
    """
    row = session.scalar(
        select(CustomerWebSite).where(CustomerWebSite.id == int(candidate_id), CustomerWebSite.tenant_id == tenant_id)
    )
    if row is None:
        raise ApplyError("not_found", 404, "That site candidate does not exist.")
    moment = now or datetime.now(UTC)
    actor = _actor(user)
    if action == "confirm":
        if row.status != WEB_SITE_PROPOSED:
            raise ApplyError("not_proposed", 409, "Only a proposed site can be confirmed.")
        confirmed, created = confirm_web_site(
            session,
            tenant_id=tenant_id,
            customer_id=int(row.customer_id),
            domain=row.domain,
            evidence=dict(row.evidence or {}),
            source=WEB_SOURCE_STEWARD,
            preview_id=row.preview_id,
            actor=actor,
            now=moment,
        )
        if confirmed is None:
            raise ApplyError("site_key_invalid", 422, "No valid site key can be made from this domain.")
        result = {"id": int(row.id), "status": WEB_SITE_CONFIRMED, "site_created": created}
    elif action == "reject":
        if row.status not in (WEB_SITE_PROPOSED, WEB_SITE_CONFIRMED):
            raise ApplyError("not_rejectable", 409, "Only a proposed or confirmed site can be rejected.")
        row.status = WEB_SITE_REJECTED
        row.decided_by = actor
        row.decided_at = moment
        session.add(row)
        session.flush()
        result = {"id": int(row.id), "status": WEB_SITE_REJECTED, "site_created": False}
    else:
        raise ApplyError("action_invalid", 422, "action must be confirm or reject")
    record_steward_audit_sync(
        user,
        action=f"site_candidate_{action}",
        importer="listing_discovery",
        payload={"candidate_id": int(row.id), "domain": row.domain},
        db=session,
    )
    return result
