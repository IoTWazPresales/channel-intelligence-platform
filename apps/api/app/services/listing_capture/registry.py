"""Listing registry CRUD, CSV import, proposal confirm, scheduler gate (LC-U1)."""

from __future__ import annotations

import csv
import io
import logging
import os
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, defer

from app.models.cst_listing_seed import CstListingSeed
from app.models.dimensions import DimProduct
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
from app.services.listing_capture.takealot_fetch import extract_plid

# Takealot fetch reasons meaning "the REST details call 404'd and EAN recovery failed".
_TAKEALOT_UNRESOLVED_REASONS = frozenset({"plid_not_found", "ean_not_unique_or_missing"})

_log = logging.getLogger(__name__)

# Snapshot policy (Warren, 2026-10-08, N-0101; all retailers): store the raw page
# snapshot only when the extracted fields changed versus the listing's previous
# successful observation (HTTP 200 + parse ok), on its first observation, or when the
# fetch or parse failed. An unchanged observation is stored without a payload and says
# so in ``parse_flags.snapshot_skipped`` (re-parse then has nothing to read).
# Snapshots older than 90 days are cleared by ``snapshot_retention`` (payload only).
SNAPSHOT_SKIPPED_UNCHANGED = "unchanged"


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

    q = (status or "proposed").strip().lower()
    stmt = select(CstListingSeed).order_by(CstListingSeed.id)
    if q not in {"all", "*"}:
        stmt = stmt.where(CstListingSeed.status == q)
    rows = list(session.scalars(stmt).all())
    labels = product_labels(session, [r.product_id for r in rows])
    out: list[dict[str, Any]] = []
    for r in rows:
        sku, name = labels.get(int(r.product_id), (None, None)) if r.product_id is not None else (None, None)
        out.append(
            enrich_proposal_with_suggested_url(
                {
                    "id": r.id,
                    "customer_id": r.customer_id,
                    "marketplace": r.marketplace,
                    "external_id": r.external_id,
                    "product_id": r.product_id,
                    "product_sku": sku,
                    "product_name": name,
                    "status": r.status,
                    "source": "CST feed",
                    "import_job_id": r.import_job_id,
                }
            )
        )
    return out


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
    ``suggest_listing_url`` returns None.
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
        reason = None if url else "no_suggested_url"
        if url and str(seed.marketplace).strip().lower() == "takealot" and not extract_plid(url):
            # Defence in depth: a Takealot seed is bulk-confirmed only with a real PLID.
            reason = "takealot_plid_unresolved"
        if reason:
            skipped.append(
                {
                    "id": int(seed.id),
                    "marketplace": seed.marketplace,
                    "external_id": seed.external_id,
                    "reason": reason,
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


def _takealot_url_for(plid: str, parse_flags: dict[str, Any] | None) -> str:
    from app.services.listing_capture.auto_finder import takealot_product_url

    canon = (parse_flags or {}).get("canonical_url")
    return takealot_product_url(plid, canonical_url=str(canon) if canon else None)


def _write_back_verified_url(
    session: Session,
    listing: CustomerListing,
    *,
    url: str | None,
    verified_at: datetime,
) -> None:
    """Stamp ``meta_json.url_verified_at``; optionally rewrite ``url`` to the resolved one.

    The first replaced value is kept in ``meta_json.original_url`` (never overwritten).
    If another listing of the same customer already holds the resolved URL (two report
    SKUs resolving to one PLID; ``uq_customer_listing_customer_url``), nothing is
    rewritten or stamped: the id is recorded in ``meta_json.url_conflict_listing_id``
    and the URL stays unverified. Listings are never merged here.
    """
    meta = listing.meta_json if isinstance(getattr(listing, "meta_json", None), dict) else {}
    meta = dict(meta)
    new_url = (url or "").strip()[:1024]
    if new_url and new_url != listing.url:
        other = session.scalar(
            select(CustomerListing.id).where(
                CustomerListing.customer_id == listing.customer_id,
                CustomerListing.url == new_url,
                CustomerListing.id != listing.id,
            )
        )
        if other is not None:
            meta["url_conflict_listing_id"] = int(other)
            meta.pop("url_verified_at", None)
            listing.meta_json = meta
            return
        meta.setdefault("original_url", listing.url)
        listing.url = new_url
    meta.pop("url_conflict_listing_id", None)
    meta["url_verified_at"] = verified_at.isoformat()
    listing.meta_json = meta


def listing_url_verified_at(
    listing: CustomerListing,
    *,
    last_ok_fetch_at: datetime | None = None,
) -> str | None:
    """When the stored URL was last verified to open the product page, else None.

    Definition ("verified"):
    - ``meta_json.url_verified_at`` is set (stamped by ``record_observation`` when the
      stored URL was fetched/resolved successfully, or by the N-0039 repair); or
    - non-Takealot only: an observation of this URL with HTTP 200 and parse ``ok``
      (``last_ok_fetch_at``). Takealot prices come from the REST API / EAN search, not
      the stored URL, so a Takealot price observation does NOT verify the URL.
    A ``dead_link`` status overrides this in the UI.
    """
    meta = listing.meta_json if isinstance(getattr(listing, "meta_json", None), dict) else {}
    stamped = meta.get("url_verified_at")
    if stamped:
        return str(stamped)
    if (listing.marketplace or "").strip().lower() != "takealot" and last_ok_fetch_at is not None:
        return last_ok_fetch_at.isoformat()
    return None


def last_ok_fetch_by_listing(session: Session, listing_ids: list[int]) -> dict[int, datetime]:
    """Latest HTTP-200 + parse-ok observation time per listing (for URL verification)."""
    ids = sorted({int(i) for i in listing_ids})
    if not ids:
        return {}
    rows = session.execute(
        select(ListingObservation.listing_id, func.max(ListingObservation.fetched_at))
        .where(
            ListingObservation.listing_id.in_(ids),
            ListingObservation.http_status == 200,
            ListingObservation.parse_status == "ok",
        )
        .group_by(ListingObservation.listing_id)
    ).all()
    return {int(lid): at for lid, at in rows if at is not None}


def _listing_meta(listing: Any) -> dict[str, Any]:
    meta = getattr(listing, "meta_json", None)
    return dict(meta) if isinstance(meta, dict) else {}


def listing_consecutive_failures(listing: Any) -> int:
    """Consecutive dead (404/410) results, kept in ``meta_json`` until U2's M4 column."""
    try:
        return max(0, int(_listing_meta(listing).get("consecutive_failures") or 0))
    except (TypeError, ValueError):
        return 0


def _listing_last_failure_at(listing: Any) -> datetime | None:
    raw = _listing_meta(listing).get("last_failure_at")
    if raw:
        try:
            at = datetime.fromisoformat(str(raw))
            return at if at.tzinfo else at.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return getattr(listing, "status_observed_at", None)


def listing_in_dead_link_backoff(listing: Any, *, now: datetime | None = None) -> bool:
    return should_backoff_dead_link(
        consecutive_dead=listing_consecutive_failures(listing),
        last_fetch_at=_listing_last_failure_at(listing),
        now=now,
    )


def _seen_in_stock(availability: str | None) -> bool:
    a = (availability or "").strip().lower().replace("_", " ")
    return "out" not in a and ("in stock" in a or a == "instock")


def previous_successful_observation(session: Session, listing_id: int | None) -> ListingObservation | None:
    """The listing's latest HTTP-200 + parse-ok observation (snapshot payload not loaded)."""
    if listing_id is None:
        return None
    stmt = (
        select(ListingObservation)
        .options(defer(ListingObservation.raw_snapshot))
        .where(
            ListingObservation.listing_id == listing_id,
            ListingObservation.http_status == 200,
            ListingObservation.parse_status == "ok",
        )
        .order_by(ListingObservation.fetched_at.desc(), ListingObservation.id.desc())
        .limit(1)
    )
    prev = session.scalars(stmt).first()
    # Anything that is not a stored observation (e.g. a mocked session) counts as "no
    # previous observation", which keeps the snapshot: the safe direction.
    return prev if isinstance(prev, ListingObservation) else None


def _price_key(value: Any) -> str | None:
    """Price as stored (Numeric(18, 4)), so a float parse and a DB Decimal compare equal."""
    if value is None:
        return None
    try:
        return str(Decimal(str(value)).quantize(Decimal("0.0001")))
    except (InvalidOperation, ValueError):
        return str(value)


def extraction_unchanged(prev: ListingObservation | None, *, parsed: Any, parser_version: str) -> bool:
    """True when ``parsed`` extracts exactly what ``prev`` holds.

    Compared: parser version, price, availability, promo badge, and every key the parser
    put in its own flags (method, VAT basis, Takealot PLID/TSIN/SKU, RRP, canonical URL,
    SKU match, ...). Fetch-side flags, CPOR activation and status transitions are not
    extracted fields and are not compared.
    """
    if prev is None or getattr(parsed, "parse_status", None) != "ok":
        return False
    if (prev.parser_version or "") != (parser_version or ""):
        return False
    if _price_key(prev.extracted_price) != _price_key(parsed.price):
        return False
    if (prev.extracted_availability or None) != (parsed.availability or None):
        return False
    if (prev.extracted_promo_badge or None) != (parsed.promo_badge or None):
        return False
    prev_flags = prev.parse_flags if isinstance(prev.parse_flags, dict) else {}
    for key, value in (parsed.flags or {}).items():
        if prev_flags.get(key) != value:
            return False
    return True


def record_observation(
    session: Session,
    listing: CustomerListing,
    *,
    http_get=None,
    consecutive_dead: int | None = None,
) -> ListingObservation:
    """Fetch (mocked) + compress + parse. Parse failure retains snapshot.

    Snapshot policy (2026-10-08): the payload is kept on the first observation, when the
    fetch or parse failed, when the extracted fields changed versus the previous
    successful observation, or on a status transition; otherwise the row is stored with
    ``raw_snapshot=None`` and ``parse_flags.snapshot_skipped='unchanged'``. Kept rows say
    why in ``parse_flags.snapshot_stored``.

    ``consecutive_dead`` defaults to the listing's tracked ``meta_json.consecutive_failures``.
    Status transitions are written on the observation as ``parse_flags.status_transition``.
    """
    if consecutive_dead is None:
        consecutive_dead = listing_consecutive_failures(listing)
        backoff_from = _listing_last_failure_at(listing)
    else:
        backoff_from = listing.status_observed_at
    if should_backoff_dead_link(consecutive_dead=consecutive_dead, last_fetch_at=backoff_from):
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

    fetch_flags: dict[str, Any] = {}
    preferred_sku = getattr(listing, "external_id", None)
    marketplace = (listing.marketplace or "").strip().lower()
    if marketplace == "takealot":
        from app.services.listing_capture.takealot_fetch import fetch_takealot_listing

        if http_get is None:
            raise RuntimeError("Live HTTP disabled in LC-U1 — inject http_get mock")

        ean = None
        known_plid = None
        meta = listing.meta_json if isinstance(listing.meta_json, dict) else {}
        known_plid = str(meta.get("takealot_plid") or "") or None
        if listing.product_id is not None:
            product = session.get(DimProduct, listing.product_id)
            if product is not None:
                ean = getattr(product, "ean", None) or getattr(product, "upc", None)
        status, body, fetch_flags = fetch_takealot_listing(
            url=listing.url,
            http_get=http_get,
            external_id=preferred_sku,
            ean=ean,
            known_plid=known_plid,
        )
        resolved = fetch_flags.get("resolved_plid")
        if resolved:
            listing.meta_json = {**meta, "takealot_plid": resolved}
            session.add(listing)
    else:
        status, body = fetch_url_text(listing.url, http_get=http_get)
    blob = compress_snapshot(body)
    parsed = parse_snapshot_text(
        body, marketplace=listing.marketplace, preferred_sku=preferred_sku
    )
    flags = {**fetch_flags, **dict(parsed.flags or {})}
    if fetch_flags.get("reason"):
        # Parser flags overwrite ``reason``; keep the fetch-side reason for diagnosis.
        flags["fetch_reason"] = fetch_flags["reason"]
    from app.services.listing_capture.cpor_activation import (
        as_of_from_fetched_at,
        evaluate_cpor_activation,
    )

    fetched_at = _now()
    activation = evaluate_cpor_activation(
        session,
        listing,
        listing_price=parsed.price,
        as_of=as_of_from_fetched_at(fetched_at),
    )
    flags["cpor_activation"] = activation

    # Snapshot policy: look up the previous successful observation BEFORE this one is
    # added (autoflush would otherwise let the query find this observation itself).
    fetch_ok = status == 200 and not fetch_flags.get("reason")
    prev_ok = None
    if fetch_ok and parsed.parse_status == "ok":
        prev_ok = previous_successful_observation(session, getattr(listing, "id", None))
    if not fetch_ok:
        snapshot_reason = "fetch_failed"
    elif parsed.parse_status != "ok":
        snapshot_reason = "parse_failed"
    elif prev_ok is None:
        snapshot_reason = "first_observation"
    elif extraction_unchanged(prev_ok, parsed=parsed, parser_version=PARSER_VERSION):
        snapshot_reason = None
    else:
        snapshot_reason = "changed"

    obs = ListingObservation(
        listing_id=listing.id,
        fetched_at=fetched_at,
        http_status=status,
        raw_snapshot=blob,
        parser_version=PARSER_VERSION,
        extracted_price=parsed.price,
        extracted_availability=parsed.availability,
        extracted_promo_badge=parsed.promo_badge,
        parse_status=parsed.parse_status,
        parse_flags=flags,
    )
    session.add(obs)
    if marketplace == "takealot":
        if (
            fetch_flags.get("plid_source")
            and not fetch_flags.get("reason")
            and parsed.parse_status == "ok"
            and fetch_flags.get("resolved_plid")
        ):
            _write_back_verified_url(
                session,
                listing,
                url=_takealot_url_for(fetch_flags["resolved_plid"], parsed.flags),
                verified_at=fetched_at,
            )
        # Dead: the REST details call for the URL's PLID 404'd AND EAN recovery failed
        # (no EAN, or the EAN search did not give exactly one hit) — or, as before,
        # a resolved PLID itself 404s.
        link_dead = (
            fetch_flags.get("details_status") in (404, 410)
            and fetch_flags.get("reason") in _TAKEALOT_UNRESOLVED_REASONS
        ) or (status in (404, 410) and bool(fetch_flags.get("plid_source")))
    else:
        link_dead = status in (404, 410)
        if status == 200 and parsed.parse_status == "ok":
            _write_back_verified_url(session, listing, url=None, verified_at=fetched_at)
    prev_status = (getattr(listing, "status", None) or "").strip().lower()
    new_status: str | None = None
    reason: str | None = None
    dead = bool(link_dead and parsed.parse_status != "ok")
    if dead:
        new_status, reason = "dead_link", "dead_link"
    elif parsed.availability and "out" in parsed.availability.lower():
        new_status, reason = "out_of_stock", "out_of_stock"
    elif parsed.parse_status == "ok" and prev_status == "out_of_stock" and _seen_in_stock(parsed.availability):
        new_status, reason = "active", "restocked"
    elif parsed.parse_status == "ok" and prev_status == "dead_link":
        new_status, reason = "active", "link_recovered"
    transitioned = False
    if new_status is not None:
        if new_status != prev_status:
            transitioned = True
            obs.parse_flags = {
                **flags,
                "status_transition": {"from": prev_status or None, "to": new_status, "reason": reason},
            }
        set_listing_status(session, listing, status=new_status, observed_at=fetched_at)

    # A status transition keeps the page even when the extracted fields match (e.g. a
    # dead link that recovers with the same price): it is the evidence for the change.
    if snapshot_reason is None and transitioned:
        snapshot_reason = "status_transition"
    obs_flags = dict(obs.parse_flags or {})
    if snapshot_reason is None:
        obs.raw_snapshot = None
        obs_flags["snapshot_skipped"] = SNAPSHOT_SKIPPED_UNCHANGED
        obs_flags["unchanged_since_observation_id"] = getattr(prev_ok, "id", None)
    else:
        obs_flags["snapshot_stored"] = snapshot_reason
    obs.parse_flags = obs_flags

    # Consecutive dead results drive the dead-link back-off (should_backoff_dead_link).
    meta = _listing_meta(listing)
    if dead:
        meta["consecutive_failures"] = listing_consecutive_failures(listing) + 1
        meta["last_failure_at"] = fetched_at.isoformat()
        listing.meta_json = meta
    elif parsed.parse_status == "ok" and ("consecutive_failures" in meta or "last_failure_at" in meta):
        meta.pop("consecutive_failures", None)
        meta.pop("last_failure_at", None)
        listing.meta_json = meta
    session.flush()
    return obs


def reparse_observation(session: Session, observation: ListingObservation, *, marketplace: str) -> ListingObservation:
    """Re-run parser on stored snapshot — no re-fetch. Re-evaluate CPOR activation.

    An observation without a payload (stored unchanged, or cleared after 90 days) is
    skipped: it is returned as it is, so its extracted fields are never overwritten by a
    parse of nothing.
    """
    if not getattr(observation, "raw_snapshot", None):
        flags = observation.parse_flags if isinstance(getattr(observation, "parse_flags", None), dict) else {}
        _log.info(
            "listing capture: reparse skipped for observation %s (no stored snapshot: %s)",
            getattr(observation, "id", None),
            flags.get("snapshot_skipped") or ("cleared" if flags.get("snapshot_cleared") else "none"),
        )
        return observation
    text = decompress_snapshot(observation.raw_snapshot)
    listing_id = getattr(observation, "listing_id", None)
    listing_for_sku = session.get(CustomerListing, listing_id) if listing_id is not None else None
    parsed = parse_snapshot_text(
        text,
        marketplace=marketplace,
        preferred_sku=getattr(listing_for_sku, "external_id", None),
    )
    listing = listing_for_sku
    flags = {**(parsed.flags or {}), "reparsed": True}
    if listing is not None:
        from app.services.listing_capture.cpor_activation import (
            as_of_from_fetched_at,
            evaluate_cpor_activation,
        )

        flags["cpor_activation"] = evaluate_cpor_activation(
            session,
            listing,
            listing_price=parsed.price,
            as_of=as_of_from_fetched_at(getattr(observation, "fetched_at", None)),
        )
    observation.parser_version = PARSER_VERSION
    observation.extracted_price = parsed.price
    observation.extracted_availability = parsed.availability
    observation.extracted_promo_badge = parsed.promo_badge
    observation.parse_status = parsed.parse_status
    observation.parse_flags = flags
    session.add(observation)
    return observation


def scheduler_should_run(session: Session, *, schedule_enabled: bool | None = None) -> dict[str, Any]:
    """Beat gate: no-op unless enabled AND at least one listing exists."""
    enabled = _listing_capture_schedule_enabled_from_env() if schedule_enabled is None else schedule_enabled
    n = session.scalar(select(func.count()).select_from(CustomerListing)) or 0
    run = bool(enabled and int(n) > 0)
    return {"enabled": enabled, "listing_count": int(n), "should_run": run}


def product_labels(session: Session, product_ids: list[int | None]) -> dict[int, tuple[str | None, str | None]]:
    wanted = {int(i) for i in product_ids if i is not None}
    if not wanted:
        return {}
    rows = list(session.scalars(select(DimProduct).where(DimProduct.id.in_(wanted))).all())
    return {int(p.id): (p.sku, p.name) for p in rows}


def listing_to_dict(
    row: CustomerListing,
    *,
    products: dict[int, tuple[str | None, str | None]] | None = None,
    last_ok_fetch: dict[int, datetime] | None = None,
) -> dict[str, Any]:
    sku: str | None = None
    name: str | None = None
    if row.product_id is not None and products:
        sku, name = products.get(int(row.product_id), (None, None))
    meta = row.meta_json if isinstance(getattr(row, "meta_json", None), dict) else {}
    return {
        "id": row.id,
        "customer_id": row.customer_id,
        "product_id": row.product_id,
        "product_sku": sku,
        "product_name": name,
        "url": row.url,
        "marketplace": row.marketplace,
        "status": row.status,
        "source": row.source,
        "registered_by": row.registered_by,
        "registered_at": row.registered_at.isoformat() if row.registered_at else None,
        "status_observed_at": row.status_observed_at.isoformat() if row.status_observed_at else None,
        "external_id": row.external_id,
        "notes": row.notes,
        "url_verified_at": listing_url_verified_at(
            row, last_ok_fetch_at=(last_ok_fetch or {}).get(int(row.id)) if row.id is not None else None
        ),
        "original_url": meta.get("original_url"),
    }


def observation_to_dict(obs: ListingObservation, listing: CustomerListing | None = None) -> dict[str, Any]:
    flags = obs.parse_flags if isinstance(obs.parse_flags, dict) else {}
    activation = flags.get("cpor_activation") if isinstance(flags.get("cpor_activation"), dict) else {}
    return {
        "id": obs.id,
        "listing_id": obs.listing_id,
        "fetched_at": obs.fetched_at.isoformat() if obs.fetched_at else None,
        "http_status": obs.http_status,
        "parse_status": obs.parse_status,
        "extracted_price": float(obs.extracted_price) if obs.extracted_price is not None else None,
        "extracted_availability": obs.extracted_availability,
        "extracted_promo_badge": obs.extracted_promo_badge,
        "parser_version": obs.parser_version,
        "cpor_activation_status": activation.get("status"),
        "cpor_activation_message": activation.get("message"),
        "cpor_case_id": activation.get("case_id"),
        "cpor_case_price": activation.get("case_price"),
        "marketplace": listing.marketplace if listing else None,
        "listing_url": listing.url if listing else None,
        "external_id": listing.external_id if listing else None,
        "product_id": listing.product_id if listing else None,
        "customer_id": listing.customer_id if listing else None,
    }


def list_recent_observations(
    session: Session,
    *,
    marketplace: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Latest observations (newest first), optionally filtered by marketplace."""
    stmt = (
        select(ListingObservation, CustomerListing)
        .join(CustomerListing, CustomerListing.id == ListingObservation.listing_id)
        .order_by(ListingObservation.fetched_at.desc(), ListingObservation.id.desc())
        .limit(int(limit))
    )
    if marketplace:
        stmt = stmt.where(CustomerListing.marketplace == marketplace.strip().lower())
    rows = list(session.execute(stmt).all())
    return [observation_to_dict(obs, listing) for obs, listing in rows]


# Statuses the poller checks (N-0085 design "Registry"). dead_link listings are retried
# until the back-off (3 consecutive dead results, then 24 h) holds them to once a day.
POLLED_LISTING_STATUSES: tuple[str, ...] = ("active", "out_of_stock", "dead_link")


def _interleave_by_marketplace(listings: list[CustomerListing]) -> list[CustomerListing]:
    """Round-robin across marketplaces, keeping each marketplace's oldest-due order."""
    lanes: dict[str, list[CustomerListing]] = {}
    for listing in listings:
        lanes.setdefault((listing.marketplace or "").strip().lower(), []).append(listing)
    out: list[CustomerListing] = []
    depth = max((len(v) for v in lanes.values()), default=0)
    for i in range(depth):
        for lane in lanes.values():
            if i < len(lane):
                out.append(lane[i])
    return out


def poll_active_listings(
    session: Session,
    *,
    marketplaces: list[str] | None = None,
    http_get=None,
    limit: int | None = None,
    time_limit_seconds: float | None = None,
    pause_store=None,
    clock=None,
    sleep=None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Synchronous poll — used by API + Celery task.

    - Checks ``active``, ``out_of_stock`` and ``dead_link`` listings (dead links in
      back-off are skipped without writing a row).
    - Oldest-due first (oldest last real observation, never-checked first), then
      round-robin across marketplaces.
    - Spacing is per marketplace (time since that site's previous request).
    - A 403/429 from a site pauses that site (``site_pause``): no more requests to it
      this run, and later runs skip it until the pause ends.
    - Stops starting new fetches after ``time_limit_seconds`` (default 10 min).
    """
    import logging
    import time

    from app.services.listing_capture import site_pause
    from app.services.listing_capture.observation import (
        DEFAULT_RATE_LIMIT_SECONDS,
        POLL_RUN_TIME_LIMIT_SECONDS,
        RATE_LIMIT_SECONDS,
        SITE_PAUSE_HTTP_STATUSES,
        default_http_get,
    )

    log = logging.getLogger(__name__)
    getter = http_get or default_http_get
    clock = clock or time.monotonic
    sleep = sleep or time.sleep
    store = pause_store if pause_store is not None else site_pause.default_site_pause_store()
    run_now = now or _now()
    limit_s = POLL_RUN_TIME_LIMIT_SECONDS if time_limit_seconds is None else float(time_limit_seconds)

    last_seen = (
        select(func.max(ListingObservation.fetched_at))
        .where(
            ListingObservation.listing_id == CustomerListing.id,
            ListingObservation.parse_status != "skipped",
        )
        .correlate(CustomerListing)
        .scalar_subquery()
    )
    stmt = (
        select(CustomerListing)
        .where(CustomerListing.status.in_(POLLED_LISTING_STATUSES))
        .order_by(last_seen.asc().nulls_first(), CustomerListing.id)
    )
    if marketplaces:
        want = {m.strip().lower() for m in marketplaces if m and m.strip()}
        if want:
            stmt = stmt.where(CustomerListing.marketplace.in_(want))
    listings = _interleave_by_marketplace(list(session.scalars(stmt).all()))
    if limit is not None:
        listings = listings[: int(limit)]

    started = clock()
    polled = 0
    failed = 0
    skipped_backoff = 0
    skipped_paused: dict[str, int] = {}
    paused_sites: dict[str, dict[str, Any]] = {}
    stopped_reason: str | None = None
    last_fetch_at: dict[str, float] = {}
    pause_checked: set[str] = set()
    had_pause_record: set[str] = set()

    for listing in listings:
        if clock() - started >= limit_s:
            stopped_reason = "time_limit"
            break
        mkt = (listing.marketplace or "").strip().lower()
        if mkt not in pause_checked:
            pause_checked.add(mkt)
            until = site_pause.paused_until(store, mkt, now=run_now)
            if until is not None:
                paused_sites[mkt] = {"until": until.isoformat(), "paused_this_run": False}
            elif site_pause.has_pause_record(store, mkt):
                had_pause_record.add(mkt)
        if mkt in paused_sites:
            skipped_paused[mkt] = skipped_paused.get(mkt, 0) + 1
            continue
        if listing_in_dead_link_backoff(listing, now=run_now):
            skipped_backoff += 1
            continue

        spacing = float(RATE_LIMIT_SECONDS.get(mkt, DEFAULT_RATE_LIMIT_SECONDS))
        if mkt in last_fetch_at and spacing > 0:
            wait = spacing - (clock() - last_fetch_at[mkt])
            if wait > 0:
                if clock() - started + wait >= limit_s:
                    stopped_reason = "time_limit"
                    break
                sleep(wait)

        refused: list[int] = []

        def guarded_get(url: str, _refused: list[int] = refused) -> tuple[int, str]:
            # After a refusal, send nothing more to this site (a Takealot check makes 2-3 calls).
            if _refused:
                return _refused[0], ""
            status, body = getter(url)
            if status in SITE_PAUSE_HTTP_STATUSES:
                # A refusal page is not a product page: never parse a price from it.
                _refused.append(int(status))
                return status, ""
            return status, body

        obs = None
        try:
            # Back-off was decided above (consecutive_dead=0 stops a second, clock-skewed check).
            obs = record_observation(session, listing, http_get=guarded_get, consecutive_dead=0)
            polled += 1
        except Exception:  # noqa: BLE001
            failed += 1
            log.warning("listing capture: listing %s poll failed", getattr(listing, "id", None), exc_info=True)
        last_fetch_at[mkt] = clock()

        if refused:
            record = site_pause.pause_site(store, mkt, http_status=refused[0], now=_now())
            paused_sites[mkt] = {**record, "paused_this_run": True}
            if obs is not None:
                flags = obs.parse_flags if isinstance(getattr(obs, "parse_flags", None), dict) else {}
                obs.parse_flags = {**flags, "site_paused": record}
        elif mkt in had_pause_record and obs is not None and getattr(obs, "http_status", None) == 200:
            site_pause.clear_site_pause(store, mkt)
            had_pause_record.discard(mkt)

    session.flush()
    result = {
        "polled": polled,
        "failed": failed,
        "listing_count": len(listings),
        "skipped_backoff": skipped_backoff,
        "skipped_paused": skipped_paused,
        "paused_sites": paused_sites,
        "stopped_reason": stopped_reason,
        "duration_seconds": round(clock() - started, 3),
    }
    log.info("listing capture poll: %s", result)
    return result
