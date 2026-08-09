"""Listing registry CRUD, CSV import, proposal confirm, scheduler gate (LC-U1)."""

from __future__ import annotations

import csv
import io
import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.cst_listing_seed import CstListingSeed
from app.models.listing_capture import CustomerListing, ListingObservation
from app.services.listing_capture.marketplace_vocab import (
    LISTING_MARKETPLACE_SET,
    LISTING_SOURCE_SET,
    LISTING_STATUS_SET,
    PARSER_VERSION,
)
from app.services.listing_capture.observation import (
    compress_snapshot,
    decompress_snapshot,
    fetch_url_text,
    parse_snapshot_text,
    should_backoff_dead_link,
)


def _listing_capture_schedule_enabled_from_env() -> bool:
    """Live env read — `CIP_LISTING_CAPTURE_SCHEDULE` truthy values: 1/true/on."""
    raw = os.environ.get("CIP_LISTING_CAPTURE_SCHEDULE", "")
    return raw.strip().lower() in ("1", "true", "on")


# Tenant gate — default disabled. Evaluated once at import for callers that read the
# module constant directly; `scheduler_should_run` re-reads the env live so tests
# (monkeypatch) and runtime toggles take effect without a process restart.
LISTING_CAPTURE_SCHEDULE_ENABLED = _listing_capture_schedule_enabled_from_env()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_listing(
    session: Session,
    *,
    customer_id: int,
    url: str,
    marketplace: str,
    product_id: int | None = None,
    source: str = "manual",
    registered_by: str | None = None,
    external_id: str | None = None,
    notes: str | None = None,
) -> CustomerListing:
    mkt = marketplace.strip().lower()
    src = source.strip().lower()
    if mkt not in LISTING_MARKETPLACE_SET:
        raise ValueError(f"unknown marketplace: {marketplace}")
    if src not in LISTING_SOURCE_SET:
        raise ValueError(f"unknown source: {source}")
    url_s = url.strip()
    if not url_s:
        raise ValueError("url required")
    row = CustomerListing(
        customer_id=int(customer_id),
        product_id=int(product_id) if product_id is not None else None,
        url=url_s[:1024],
        marketplace=mkt,
        status="active",
        source=src,
        registered_by=registered_by,
        registered_at=_now(),
        external_id=(external_id or "").strip() or None,
        notes=notes,
    )
    session.add(row)
    session.flush()
    return row


def set_listing_status(
    session: Session,
    listing: CustomerListing,
    *,
    status: str,
    observed_at: datetime | None = None,
) -> CustomerListing:
    st = status.strip().lower()
    if st not in LISTING_STATUS_SET:
        raise ValueError(f"unknown status: {status}")
    listing.status = st
    listing.status_observed_at = observed_at or _now()
    session.add(listing)
    return listing


def import_listings_csv(
    session: Session,
    *,
    csv_text: str,
    registered_by: str | None = None,
) -> dict[str, Any]:
    """Per-row FLAG≠BLOCK — bad rows collected; good rows committed."""
    reader = csv.DictReader(io.StringIO(csv_text))
    created = 0
    flags: list[dict[str, Any]] = []
    for i, row in enumerate(reader):
        try:
            cid = int(str(row.get("customer_id") or "").strip())
            url = str(row.get("url") or "").strip()
            mkt = str(row.get("marketplace") or "").strip()
            pid_raw = str(row.get("product_id") or "").strip()
            pid = int(pid_raw) if pid_raw else None
            create_listing(
                session,
                customer_id=cid,
                url=url,
                marketplace=mkt,
                product_id=pid,
                source="csv_import",
                registered_by=registered_by,
                external_id=str(row.get("external_id") or "").strip() or None,
            )
            created += 1
        except Exception as exc:
            flags.append({"row": i + 1, "error": str(exc), "raw": dict(row)})
    session.flush()
    return {"created": created, "row_flags": flags, "ok": True}


def list_proposals(session: Session, *, status: str = "proposed") -> list[dict[str, Any]]:
    from app.services.listing_capture.auto_finder import enrich_proposal_with_suggested_url

    rows = list(
        session.scalars(
            select(CstListingSeed).where(CstListingSeed.status == status).order_by(CstListingSeed.id)
        ).all()
    )
    return [
        enrich_proposal_with_suggested_url(
            {
                "id": r.id,
                "customer_id": r.customer_id,
                "marketplace": r.marketplace,
                "external_id": r.external_id,
                "product_id": r.product_id,
                "status": r.status,
                "import_job_id": r.import_job_id,
            }
        )
        for r in rows
    ]


def confirm_proposal(
    session: Session,
    *,
    seed_id: int,
    url: str,
    registered_by: str | None = None,
) -> CustomerListing:
    """Steward confirm → create listing source=feed_proposal. Never auto-create."""
    seed = session.get(CstListingSeed, seed_id)
    if seed is None:
        raise ValueError(f"seed {seed_id} not found")
    if seed.status != "proposed":
        raise ValueError(f"seed status is {seed.status}, expected proposed")
    listing = create_listing(
        session,
        customer_id=int(seed.customer_id),
        url=url,
        marketplace=str(seed.marketplace),
        product_id=int(seed.product_id) if seed.product_id is not None else None,
        source="feed_proposal",
        registered_by=registered_by,
        external_id=str(seed.external_id),
    )
    seed.status = "confirmed"
    session.add(seed)
    session.flush()
    return listing


def confirm_suggested_proposals(
    session: Session,
    *,
    registered_by: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Confirm proposed seeds that have an auto-finder URL — skip seeds without a suggestion.

    Still steward-initiated (explicit call / UI button). Never invents a URL when
    ``suggest_listing_url`` returns None (e.g. Evetech).
    """
    from app.services.listing_capture.auto_finder import suggest_listing_url

    rows = list(
        session.scalars(
            select(CstListingSeed)
            .where(CstListingSeed.status == "proposed")
            .order_by(CstListingSeed.id)
        ).all()
    )
    confirmed = 0
    skipped: list[dict[str, Any]] = []
    for seed in rows:
        if limit is not None and confirmed >= int(limit):
            break
        url = suggest_listing_url(str(seed.marketplace), str(seed.external_id))
        if not url:
            skipped.append(
                {
                    "id": int(seed.id),
                    "marketplace": seed.marketplace,
                    "external_id": seed.external_id,
                    "reason": "no_suggested_url",
                }
            )
            continue
        confirm_proposal(
            session,
            seed_id=int(seed.id),
            url=url,
            registered_by=registered_by,
        )
        confirmed += 1
    session.flush()
    return {
        "confirmed": confirmed,
        "skipped": skipped,
        "proposed_remaining": max(0, len(rows) - confirmed - len(skipped)),
    }


def reject_proposal(session: Session, *, seed_id: int) -> CstListingSeed:
    seed = session.get(CstListingSeed, seed_id)
    if seed is None:
        raise ValueError(f"seed {seed_id} not found")
    seed.status = "rejected"
    session.add(seed)
    return seed


def record_observation(
    session: Session,
    listing: CustomerListing,
    *,
    http_get=None,
    consecutive_dead: int = 0,
) -> ListingObservation:
    """Fetch (mocked) + compress + parse. Parse failure retains snapshot."""
    if should_backoff_dead_link(consecutive_dead=consecutive_dead, last_fetch_at=listing.status_observed_at):
        obs = ListingObservation(
            listing_id=listing.id,
            fetched_at=_now(),
            http_status=None,
            raw_snapshot=None,
            parser_version=PARSER_VERSION,
            parse_status="skipped",
            parse_flags={"reason": "dead_link_backoff"},
        )
        session.add(obs)
        session.flush()
        return obs

    status, body = fetch_url_text(listing.url, http_get=http_get)
    blob = compress_snapshot(body)
    parsed = parse_snapshot_text(body, marketplace=listing.marketplace)
    obs = ListingObservation(
        listing_id=listing.id,
        fetched_at=_now(),
        http_status=status,
        raw_snapshot=blob,
        parser_version=PARSER_VERSION,
        extracted_price=parsed.price,
        extracted_availability=parsed.availability,
        extracted_promo_badge=parsed.promo_badge,
        parse_status=parsed.parse_status,
        parse_flags=parsed.flags,
    )
    session.add(obs)
    if status in (404, 410):
        set_listing_status(session, listing, status="dead_link")
    elif parsed.availability and "out" in parsed.availability.lower():
        set_listing_status(session, listing, status="out_of_stock")
    session.flush()
    return obs


def reparse_observation(session: Session, observation: ListingObservation, *, marketplace: str) -> ListingObservation:
    """Re-run parser on stored snapshot — no re-fetch."""
    text = decompress_snapshot(observation.raw_snapshot)
    parsed = parse_snapshot_text(text, marketplace=marketplace)
    observation.parser_version = PARSER_VERSION
    observation.extracted_price = parsed.price
    observation.extracted_availability = parsed.availability
    observation.extracted_promo_badge = parsed.promo_badge
    observation.parse_status = parsed.parse_status
    observation.parse_flags = {**(parsed.flags or {}), "reparsed": True}
    session.add(observation)
    return observation


def scheduler_should_run(session: Session, *, schedule_enabled: bool | None = None) -> dict[str, Any]:
    """Beat gate: no-op unless enabled AND at least one listing exists."""
    enabled = _listing_capture_schedule_enabled_from_env() if schedule_enabled is None else schedule_enabled
    n = session.scalar(select(func.count()).select_from(CustomerListing)) or 0
    run = bool(enabled and int(n) > 0)
    return {"enabled": enabled, "listing_count": int(n), "should_run": run}


def listing_to_dict(row: CustomerListing) -> dict[str, Any]:
    return {
        "id": row.id,
        "customer_id": row.customer_id,
        "product_id": row.product_id,
        "url": row.url,
        "marketplace": row.marketplace,
        "status": row.status,
        "source": row.source,
        "registered_by": row.registered_by,
        "registered_at": row.registered_at.isoformat() if row.registered_at else None,
        "status_observed_at": row.status_observed_at.isoformat() if row.status_observed_at else None,
        "external_id": row.external_id,
        "notes": row.notes,
    }
