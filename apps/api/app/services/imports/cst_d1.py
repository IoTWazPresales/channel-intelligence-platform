"""CPOR U4.5 Phase B — CST D1 helpers (alias, listing seed, period, slots, profiles).

No money math. FLAG ≠ BLOCK. No auto-create of locations/products.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.cst_listing_seed import CstListingSeed
from app.models.customer_article_alias import CustomerArticleAlias
from app.models.customer_cst_report_slot import CustomerCstReportSlot
from app.models.customer_report_config import CustomerReportConfig
from app.models.dimensions import DimCustomer
from app.models.listing_capture import CustomerListing
from app.services.imports.tenant_mapping_scope import effective_tenant_id, tenant_scope_predicate
from app.utils.json_safe import to_jsonable

DEFAULT_VAT_BASIS = "ex_vat"
CONFIRMED_ALIAS_STATUSES = frozenset({"confirmed", "active"})


def normalize_article_token(raw: str | None) -> str:
    if raw is None:
        return ""
    t = str(raw).strip().lower()
    return t if t and t != "nan" else ""


def resolve_customer_article_alias(
    session: Session,
    *,
    customer_id: int,
    article_token: str | None,
    as_of: date | None = None,
) -> int | None:
    """Exact-key lookup of steward-confirmed article aliases. Never fuzzy.

    When ``as_of`` is set, return the confirmed/active era whose half-open
    ``[valid_from, valid_to)`` contains that date (NULL bounds = ±infinity).
    When ``as_of`` is None, prefer the latest open-ended era (valid_to IS NULL),
    else any confirmed row (legacy single-row behaviour).
    """
    key = normalize_article_token(article_token)
    if not key:
        return None
    cust = session.get(DimCustomer, int(customer_id))
    tid = effective_tenant_id(getattr(cust, "tenant_id", None) if cust is not None else None)
    rows = list(
        session.scalars(
            select(CustomerArticleAlias).where(
                CustomerArticleAlias.customer_id == customer_id,
                CustomerArticleAlias.article_no_normalized == key,
                CustomerArticleAlias.status.in_(CONFIRMED_ALIAS_STATUSES),
                tenant_scope_predicate(CustomerArticleAlias, tid),
            )
        ).all()
    )
    if not rows:
        return None

    def _contains(row: CustomerArticleAlias, day: date) -> bool:
        vf = row.valid_from
        vt = row.valid_to
        if vf is not None and day < vf:
            return False
        if vt is not None and day >= vt:
            return False
        return True

    if as_of is not None:
        hits = [r for r in rows if _contains(r, as_of)]
        if len(hits) == 1:
            return int(hits[0].product_id)
        if len(hits) > 1:
            # Exclusion constraint should prevent this for confirmed; FLAG by refusing.
            return None
        return None

    open_ended = [r for r in rows if r.valid_to is None]
    if len(open_ended) == 1:
        return int(open_ended[0].product_id)
    if len(rows) == 1:
        return int(rows[0].product_id)
    # Ambiguous without as_of — do not silent-pick among closed eras.
    return None


def propose_customer_article_alias(
    session: Session,
    *,
    customer_id: int,
    article_token: str | None,
    product_id: int,
    evidence: dict[str, Any] | None = None,
) -> CustomerArticleAlias | None:
    """Learn co-occurrence as status=proposed. Never silent-confirm.

    Dedupes within the same Session before flush — one article can co-occur on
    many sell-through lines (e.g. Game site fan-out); naive add() × N hits
    ``uq_customer_article_alias_customer_article``.
    """
    key = normalize_article_token(article_token)
    if not key:
        return None
    cust = session.get(DimCustomer, int(customer_id))
    tid = effective_tenant_id(getattr(cust, "tenant_id", None) if cust is not None else None)
    existing = session.scalar(
        select(CustomerArticleAlias).where(
            CustomerArticleAlias.customer_id == customer_id,
            CustomerArticleAlias.article_no_normalized == key,
            tenant_scope_predicate(CustomerArticleAlias, tid),
        )
    )
    if existing is not None:
        return existing
    # Pending inserts are invisible to the SELECT above until flush.
    for obj in session.new:
        if (
            isinstance(obj, CustomerArticleAlias)
            and int(obj.customer_id) == int(customer_id)
            and obj.article_no_normalized == key
        ):
            return obj
    row = CustomerArticleAlias(
        tenant_id=tid,
        customer_id=customer_id,
        article_no_normalized=key,
        product_id=int(product_id),
        status="proposed",
        evidence_json=to_jsonable(evidence or {}),
    )
    session.add(row)
    return row


def external_ids_show_compacted_numeric_shape(external_ids: list[str] | tuple[str, ...]) -> bool:
    """True when prior ids are already digits of length >= 5 with no stored spaces.

    A spaced numeric id means this customer kept the spaces, so a later import must
    not strip them. Non-numeric ids are ignored. No numeric history is not evidence.
    """
    numeric: list[str] = []
    for raw in external_ids:
        text = str(raw).strip()
        if not text:
            continue
        compact = re.sub(r"\s+", "", text)
        if compact.isdigit() and len(compact) >= 5:
            numeric.append(text)
    if not numeric:
        return False
    return all(re.search(r"\s", text) is None for text in numeric)


def _prior_external_ids(session: Session, customer_id: int, marketplace: str) -> list[str]:
    """Listing and seed ids for one customer and marketplace, loaded once per session."""
    cache: dict[tuple[int, str], list[str]] = session.info.setdefault("_cst_prior_external_ids", {})
    key = (int(customer_id), marketplace)
    cached = cache.get(key)
    if cached is not None:
        return cached
    listing_ids = session.scalars(
        select(CustomerListing.external_id).where(
            CustomerListing.customer_id == int(customer_id),
            func.lower(func.trim(CustomerListing.marketplace)) == marketplace,
            CustomerListing.external_id.is_not(None),
        )
    ).all()
    seed_ids = session.scalars(
        select(CstListingSeed.external_id).where(
            CstListingSeed.customer_id == int(customer_id),
            func.lower(CstListingSeed.marketplace) == marketplace,
        )
    ).all()
    found = [str(value) for value in (*listing_ids, *seed_ids) if value]
    cache[key] = found
    return found


def _compact_numeric_external_id(row: dict[str, Any]) -> None:
    ext_raw = row.get("listing_external_id")
    if not isinstance(ext_raw, str) or not ext_raw.strip():
        return
    compact = re.sub(r"\s+", "", ext_raw.strip())
    if compact.isdigit() and len(compact) >= 5:
        row["listing_external_id"] = compact


def apply_listing_seed_fields(
    row: dict[str, Any],
    feed_profile: dict[str, Any] | None,
    *,
    session: Session | None = None,
    customer_id: int | None = None,
    prior_external_ids: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Fill listing_external_id / listing_marketplace for LC-U1 seed emission.

    Customer-agnostic via ``feed_profile.listing_seed`` (data, not a layout-family table)::

        {
          "marketplace": "<site key>",            # required constant when the column is absent
          "external_id_from": "raw_product_token", # or "listing_external_id" (default)
          "compact_spaced_numeric_external_id": true
        }

    Column-mapped values always win. A layout family does not imply a marketplace.

    Spaced numeric external ids (digits, length >= 5 once spaces are removed):
    ``compact_spaced_numeric_external_id: true`` always compacts; ``false`` never
    does. When the flag is absent, compact only if this customer's existing
    ``customer_listing`` / ``cst_listing_seed`` ids for the same marketplace are
    already the compacted shape. No history does not compact — the shape has to
    come from data already stored for that customer.
    """
    if not isinstance(row, dict):
        return row
    profile = feed_profile if isinstance(feed_profile, dict) else {}
    seed_cfg = profile.get("listing_seed") if isinstance(profile.get("listing_seed"), dict) else {}

    ext = row.get("listing_external_id")
    if not (isinstance(ext, str) and ext.strip()):
        source_key = str(seed_cfg.get("external_id_from") or "listing_external_id").strip()
        if source_key == "raw_product_token":
            tok = row.get("raw_product_token")
            if isinstance(tok, str) and tok.strip():
                row["listing_external_id"] = tok.strip()
        elif source_key and source_key != "listing_external_id":
            alt = row.get(source_key)
            if isinstance(alt, str) and alt.strip():
                row["listing_external_id"] = alt.strip()

    mkt = row.get("listing_marketplace")
    if not (isinstance(mkt, str) and mkt.strip()):
        cfg_mkt = seed_cfg.get("marketplace") or profile.get("listing_marketplace")
        if isinstance(cfg_mkt, str) and cfg_mkt.strip():
            row["listing_marketplace"] = cfg_mkt.strip().lower()
    elif isinstance(mkt, str):
        row["listing_marketplace"] = mkt.strip().lower()

    flag = seed_cfg.get("compact_spaced_numeric_external_id")
    if flag is True:
        _compact_numeric_external_id(row)
    elif flag is not False:
        marketplace = row.get("listing_marketplace")
        market = marketplace.strip().lower() if isinstance(marketplace, str) else ""
        ids: list[str] | tuple[str, ...] | None
        if prior_external_ids is not None:
            ids = prior_external_ids
        elif session is not None and customer_id is not None and market:
            ids = _prior_external_ids(session, int(customer_id), market)
        else:
            ids = None
        if ids and external_ids_show_compacted_numeric_shape(ids):
            _compact_numeric_external_id(row)
    return row


def upsert_cst_listing_seed(
    session: Session,
    *,
    customer_id: int,
    marketplace: str | None,
    external_id: str | None,
    product_id: int | None,
    import_job_id: int | None,
    raw: dict[str, Any] | None = None,
) -> CstListingSeed | None:
    """Durable LC-U1 handoff capture. No registry / no auto-confirm.

    De-dupes within the current Session flush (week files repeat a product id
    across months) so batched INSERT does not hit uq_cst_listing_seed_*.
    """
    mkt = (marketplace or "").strip().lower()
    ext = (external_id or "").strip()
    if not mkt or not ext:
        return None
    cache: dict[tuple[int, str, str], CstListingSeed] = session.info.setdefault(
        "_cst_listing_seed_cache",
        {},
    )
    key = (int(customer_id), mkt, ext)
    existing = cache.get(key)
    if existing is None:
        existing = session.scalar(
            select(CstListingSeed).where(
                CstListingSeed.customer_id == customer_id,
                CstListingSeed.marketplace == mkt,
                CstListingSeed.external_id == ext,
            )
        )
    if existing is not None:
        if product_id is not None and existing.product_id is None:
            existing.product_id = int(product_id)
        if import_job_id is not None:
            existing.import_job_id = int(import_job_id)
        if raw:
            existing.raw_json = to_jsonable(raw)
        session.add(existing)
        cache[key] = existing
        return existing
    row = CstListingSeed(
        customer_id=customer_id,
        marketplace=mkt,
        external_id=ext,
        product_id=int(product_id) if product_id is not None else None,
        status="proposed",
        import_job_id=int(import_job_id) if import_job_id is not None else None,
        raw_json=to_jsonable(raw) if raw else None,
    )
    session.add(row)
    cache[key] = row
    return row


def feed_profile_vat_basis(cfg: CustomerReportConfig | None) -> str:
    if cfg is None or not isinstance(cfg.feed_profile_json, dict):
        return DEFAULT_VAT_BASIS
    raw = cfg.feed_profile_json.get("vat_basis")
    if isinstance(raw, str) and raw.strip():
        return raw.strip().lower()
    return DEFAULT_VAT_BASIS


def monday_of_week(d: date) -> date:
    """Tenant default week convention: Mon–Sun (ISO weekday Monday=0)."""
    return d - timedelta(days=d.weekday())


def corroborate_period(
    *,
    steward_declared: date | None,
    file_inferred: date | None,
    filename: str | None = None,
) -> dict[str, Any]:
    """Steward-declared + file-corroborated. Conflicts surface; never silently pick file over steward."""
    flags: list[str] = []
    chosen: date | None = None
    source: str | None = None
    if steward_declared is not None and file_inferred is not None:
        if steward_declared == file_inferred:
            chosen, source = steward_declared, "steward_corroborated"
        else:
            chosen, source = steward_declared, "steward_declared"
            flags.append("period_conflict")
    elif steward_declared is not None:
        chosen, source = steward_declared, "steward_declared"
        flags.append("period_uncorroborated")
    elif file_inferred is not None:
        chosen, source = file_inferred, "file_inferred"
        flags.append("period_steward_missing")
    else:
        flags.append("period_unknown")
    return {
        "period_start_date": chosen,
        "source": source,
        "flags": flags,
        "steward_declared": steward_declared.isoformat() if steward_declared else None,
        "file_inferred": file_inferred.isoformat() if file_inferred else None,
        "filename": filename,
    }


def advance_cst_report_slots(
    session: Session,
    *,
    as_of: date | None = None,
    now: datetime | None = None,
) -> dict[str, int]:
    """Create/advance due→late→missing slots for key-account customers with reports_expected.

    Timing (spec §10.4.4.5): slot for prior Mon–Sun week is due Monday; late Tuesday;
    missing thereafter. Notification wiring is left to callers / activity feed.
    """
    today = as_of or date.today()
    clock = now or datetime.now(timezone.utc)
    prior_week_start = monday_of_week(today) - timedelta(days=7)
    due_monday = prior_week_start + timedelta(days=7)  # Monday after that week
    late_tuesday = due_monday + timedelta(days=1)

    configs = list(
        session.scalars(
            select(CustomerReportConfig).where(CustomerReportConfig.reports_expected.is_(True))
        ).all()
    )
    created = advanced_late = advanced_missing = 0
    for cfg in configs:
        cust = session.get(DimCustomer, cfg.customer_id)
        if cust is None:
            continue
        if not bool(getattr(cust, "is_key_account", False)):
            continue
        slot = session.scalar(
            select(CustomerCstReportSlot).where(
                CustomerCstReportSlot.customer_id == cfg.customer_id,
                CustomerCstReportSlot.week_start_date == prior_week_start,
            )
        )
        if slot is None:
            status = "due"
            if today > late_tuesday:
                status = "missing"
            elif today >= late_tuesday:
                status = "late"
            slot = CustomerCstReportSlot(
                customer_id=cfg.customer_id,
                week_start_date=prior_week_start,
                status=status,
                due_at=datetime(due_monday.year, due_monday.month, due_monday.day, tzinfo=timezone.utc),
                late_at=datetime(late_tuesday.year, late_tuesday.month, late_tuesday.day, tzinfo=timezone.utc)
                if status in ("late", "missing")
                else None,
                cadence_snapshot=cfg.expected_cadence,
            )
            session.add(slot)
            created += 1
            continue
        if slot.status == "received":
            continue
        if slot.status == "due" and today >= late_tuesday:
            slot.status = "late"
            slot.late_at = clock
            session.add(slot)
            advanced_late += 1
        if slot.status == "late" and today > late_tuesday:
            # After Tuesday → missing (Wednesday+)
            if today > late_tuesday:
                slot.status = "missing"
                session.add(slot)
                advanced_missing += 1
    return {
        "created": created,
        "advanced_late": advanced_late,
        "advanced_missing": advanced_missing,
        "week_start": prior_week_start.isoformat(),
    }


def mark_cst_report_slot_received(
    session: Session,
    *,
    customer_id: int,
    period_start_date: date | None,
    import_job_id: int | None,
) -> CustomerCstReportSlot | None:
    if period_start_date is None:
        return None
    week_start = monday_of_week(period_start_date)
    slot = session.scalar(
        select(CustomerCstReportSlot).where(
            CustomerCstReportSlot.customer_id == customer_id,
            CustomerCstReportSlot.week_start_date == week_start,
        )
    )
    if slot is None:
        slot = CustomerCstReportSlot(
            customer_id=customer_id,
            week_start_date=week_start,
            status="received",
            received_at=datetime.now(timezone.utc),
            import_job_id=import_job_id,
        )
        session.add(slot)
        return slot
    slot.status = "received"
    slot.received_at = datetime.now(timezone.utc)
    if import_job_id is not None:
        slot.import_job_id = int(import_job_id)
    session.add(slot)
    return slot


def list_cst_report_worklist_slots(
    session: Session,
    *,
    statuses: tuple[str, ...] = ("due", "late", "missing"),
) -> list[CustomerCstReportSlot]:
    """Worklist slots — received is excluded by default (drops off worklist)."""
    return list(
        session.scalars(
            select(CustomerCstReportSlot)
            .where(CustomerCstReportSlot.status.in_(statuses))
            .order_by(CustomerCstReportSlot.week_start_date.desc(), CustomerCstReportSlot.id.desc())
        ).all()
    )


def list_missing_cst_report_slots(session: Session) -> list[CustomerCstReportSlot]:
    return list_cst_report_worklist_slots(session, statuses=("late", "missing"))


def confirm_customer_article_alias(
    session: Session,
    *,
    alias_id: int,
    actor: str | None = None,
) -> CustomerArticleAlias | None:
    """Steward confirm: proposed → confirmed. Never silent."""
    row = session.get(CustomerArticleAlias, alias_id)
    if row is None:
        return None
    if row.status in CONFIRMED_ALIAS_STATUSES:
        return row
    if row.status not in ("proposed", "rejected"):
        return row
    evidence = dict(row.evidence_json or {}) if isinstance(row.evidence_json, dict) else {}
    trail = list(evidence.get("steward_events") or [])
    trail.append(
        {
            "action": "confirm",
            "actor": actor,
            "at": datetime.now(timezone.utc).isoformat(),
            "from_status": row.status,
        }
    )
    evidence["steward_events"] = trail
    row.status = "confirmed"
    row.evidence_json = to_jsonable(evidence)
    session.add(row)
    return row


def reject_customer_article_alias(
    session: Session,
    *,
    alias_id: int,
    actor: str | None = None,
    reason: str | None = None,
) -> CustomerArticleAlias | None:
    """Steward reject. FLAG only — does not delete."""
    row = session.get(CustomerArticleAlias, alias_id)
    if row is None:
        return None
    evidence = dict(row.evidence_json or {}) if isinstance(row.evidence_json, dict) else {}
    trail = list(evidence.get("steward_events") or [])
    trail.append(
        {
            "action": "reject",
            "actor": actor,
            "at": datetime.now(timezone.utc).isoformat(),
            "from_status": row.status,
            "reason": reason,
        }
    )
    evidence["steward_events"] = trail
    row.status = "rejected"
    row.evidence_json = to_jsonable(evidence)
    session.add(row)
    return row
