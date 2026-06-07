"""Distributor sales & inventory import: staging, resolution, aggregated mapping candidates, fact apply."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import pandas as pd
from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.models.dimensions import DimCustomer, DimDistributor, DimProduct
from app.models.facts import FactInventoryDistributor, FactReturns, FactSalesSellout
from app.services.imports.dsi_fact_source_keys import (
    dsi_inventory_source_key,
    dsi_return_source_key,
    dsi_sellout_source_key,
    normalize_dsi_invoice_no,
)
from app.models.import_distributor_si import (
    CustomerSourceTokenAlias,
    DistributorSourceTokenAlias,
    ImportDistributorSiStagingLine,
    ImportEntityMappingCandidate,
)
from app.models.ingestion import ImportJob, ImportRowResult
from app.models.mapping import ProductAlias
from app.services.commercial_planner.open_channel_customer import OPEN_CHANNEL_CUSTOMER_CODE
from app.services.imports.dsi_customer_intelligence import (
    annotate_dsi_customer_candidate_duplicates,
    annotate_dsi_customer_distributor_name_collisions,
)
from app.services.imports.dsi_customer_name_normalization import normalize_customer_name_token
from app.services.imports.dsi_shipment_corroboration import (
    shipment_corroboration_for_customer,
    shipment_corroboration_for_product,
)
from app.utils.json_safe import to_jsonable, verify_json_serializable

CANONICAL = (
    "distributor_token",
    "product_identifier",
    "transaction_date",
    "invoice_no",
    "snapshot_date",
    "quantity_sold",
    "stock_on_hand",
    "customer_dealer_token",
    "dealer_group_token",
    "unit_sellout_price_ex_tax_amount",
    "reported_revenue_amount",
    "currency_code",
    "channel_key_token",
    "region_or_province_token",
    "open_channel_evidence",
    "ignored_shipping_evidence",
)

CHANNEL_OPEN_SUBSTRINGS = ("open channel", "open_channel", "open-channel")

SENTINEL_CUSTOMER_TOKENS = frozenset(
    {
        "cash sale",
        "end user",
        "consumer",
        "walk-in",
        "walk in",
        "unknown",
        "dealer",
        "misc",
        "n/a",
        "na",
        "tbd",
    }
)

DEALER_GROUP_PLACEHOLDER_SUBSTRINGS = ("to be mapped", "tbd", "unknown", "pending mapping")

CUSTOMER_TOKEN_PLACEHOLDER_SUBSTRINGS = DEALER_GROUP_PLACEHOLDER_SUBSTRINGS


def _customer_token_is_placeholder(norm: str, raw: str | None) -> bool:
    """True when the source customer/dealer cell is blank, a sentinel token, or a workbook placeholder."""
    if not norm:
        return True
    if norm in SENTINEL_CUSTOMER_TOKENS:
        return True
    r = (raw or "").strip().lower()
    return any(p in r for p in CUSTOMER_TOKEN_PLACEHOLDER_SUBSTRINGS)


def _dealer_group_is_placeholder(dg_raw: str | None) -> bool:
    dg = _clean_str(dg_raw)
    if not dg:
        return True
    return any(x in dg.lower() for x in DEALER_GROUP_PLACEHOLDER_SUBSTRINGS)


def effective_dsi_customer_primary_for_resolution(
    customer_dealer_raw: str | None, dealer_group_raw: str | None
) -> tuple[str | None, list[str]]:
    """Pick the token used for dim_customer / steward-alias resolution.

    Business rule (RAW / DSI): **Dealer Name Group** is the primary account grouping. The customer/dealer
    name column is alias/source evidence and is used for resolution only when the dealer group cell is
    blank or a workbook placeholder. Original columns remain on staging (`raw_customer_dealer_token`,
    `raw_dealer_group_token`) and in `raw_row_payload`.
    """
    notes: list[str] = []
    if not _dealer_group_is_placeholder(dealer_group_raw):
        notes.append("customer_resolution_primary_dealer_name_group")
        cu_nt = _norm_key(customer_dealer_raw)
        if not _customer_token_is_placeholder(cu_nt, customer_dealer_raw):
            notes.append("customer_name_evidence_for_group")
        return (_clean_str(dealer_group_raw), notes)
    cu_nt = _norm_key(customer_dealer_raw)
    if not _customer_token_is_placeholder(cu_nt, customer_dealer_raw):
        return (_clean_str(customer_dealer_raw), notes)
    return (None, notes)


def _customer_candidate_identity_norm(customer_dealer_raw: str | None, dealer_group_raw: str | None) -> str:
    """Stable key for ``ImportEntityMappingCandidate`` rows: must match DB uniqueness (job + entity + normalized_key).

    Dealer Name Group wins when present/non-placeholder; otherwise non-placeholder customer column; otherwise
    a single blank bucket.
    """
    if not _dealer_group_is_placeholder(dealer_group_raw):
        return _norm_key(dealer_group_raw)
    if not _customer_token_is_placeholder(_norm_key(customer_dealer_raw), customer_dealer_raw):
        return _norm_key(customer_dealer_raw)
    return "__blank__"


# Channel / marketplace hints for steward review (generic; not region-specific).
STRATEGIC_CHANNEL_HINT_SUBSTRINGS = (
    "amazon",
    "takealot",
    "makro",
    "massmart",
    "game ",
    " game",
    "incredible connection",
    "walmart",
    "ebay",
    "alibaba",
    "shopify",
    "marketplace",
    "etail",
    "e-tail",
)


def _norm_key(s: str | None) -> str:
    if s is None:
        return ""
    t = str(s).strip().lower()
    t = re.sub(r"\s+", " ", t)
    return t


def _col(mapping: dict[str, str], key: str) -> str | None:
    for src, tgt in mapping.items():
        if tgt == key:
            return src
    return None


def _channel_raw_for_dsi(row: pd.Series, mapping: dict[str, str]) -> str | None:
    """Prefer channel_key_token; fall back to channel_code-mapped column (alias collision with other templates)."""
    c = _col(mapping, "channel_key_token")
    if c:
        v = _clean_str(row.get(c))
        if v:
            return v
    c2 = _col(mapping, "channel_code")
    if c2:
        return _clean_str(row.get(c2))
    return None


REGION_CHANNEL_EVIDENCE_SENTINELS = frozenset(
    {
        "unknown",
        "n/a",
        "na",
        "tbd",
        "pending",
        "pending mapping",
        "to be mapped",
    }
)


def _region_channel_evidence_norm_usable(norm: str, raw: str | None) -> bool:
    """True when a mapped region/channel cell is non-empty and not a workbook placeholder."""
    if not norm:
        return False
    if norm in REGION_CHANNEL_EVIDENCE_SENTINELS:
        return False
    r = (raw or "").strip().lower()
    if any(p in r for p in DEALER_GROUP_PLACEHOLDER_SUBSTRINGS):
        return False
    return True


def _region_raw_for_dsi(row: pd.Series, mapping: dict[str, str]) -> str | None:
    """Prefer region_or_province_token; fall back to region_code when mapped."""
    c = _col(mapping, "region_or_province_token")
    if c:
        v = _clean_str(row.get(c))
        if v:
            return v
    c2 = _col(mapping, "region_code")
    if c2:
        return _clean_str(row.get(c2))
    return None


def _clean_str(v: Any) -> str | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    t = str(v).strip()
    if not t or t.lower() == "nan":
        return None
    return t


def _channel_raw_from_mapped(mapped: dict[str, Any] | None) -> str | None:
    if not mapped or not isinstance(mapped, dict):
        return None
    for k in ("channel_key_token", "channel_code"):
        v = _clean_str(mapped.get(k))
        if v:
            return v
    return None


def _region_raw_from_mapped(mapped: dict[str, Any] | None) -> str | None:
    if not mapped or not isinstance(mapped, dict):
        return None
    for k in ("region_or_province_token", "region_code"):
        v = _clean_str(mapped.get(k))
        if v:
            return v
    return None


def _parse_date(v: Any) -> date | None:
    s = _clean_str(v)
    if not s:
        return None
    try:
        ts = pd.to_datetime(s, errors="coerce")
        if pd.isna(ts):
            return None
        if isinstance(ts, pd.Timestamp):
            return ts.date()
    except (ValueError, TypeError):
        return None
    return None


DSI_HISTORICAL_SELL_OUT_DAY_THRESHOLD = 90


def dsi_historical_workflow_from_import_job(job: ImportJob) -> bool:
    """True when this DSI job runs in **historical** workflow (relaxed steward gates, optional auto-apply)."""

    sm = job.staged_metadata
    if not isinstance(sm, dict):
        return False
    return str(sm.get("dsi_workflow_mode") or "").strip().lower() == "historical"


def dsi_historical_product_eligibility_relaxed_from_import_job(job: ImportJob) -> bool:
    """True when the last DSI validation run classified the job as historical workflow (or legacy relaxed flag).

    Used by staging refresh and the steward resolution plan so inactive Product Master rows stay
    auto-eligible for the same job session.
    """
    sm = job.staged_metadata
    if not isinstance(sm, dict):
        return False
    if dsi_historical_workflow_from_import_job(job):
        return True
    return bool(sm.get("dsi_historical_product_eligibility_relaxed"))


def _dsi_import_predominantly_historical_by_evidence_dates(
    df: pd.DataFrame,
    mapping: dict[str, str],
    *,
    day_threshold: int = DSI_HISTORICAL_SELL_OUT_DAY_THRESHOLD,
) -> bool:
    """Majority of rows with a parsed evidence date are older than ``today - day_threshold`` days."""
    if df is None or df.empty:
        return False
    cutoff = date.today() - timedelta(days=max(0, int(day_threshold)))
    dates: list[date] = []
    tx_col = _col(mapping, "transaction_date")
    snap_col = _col(mapping, "snapshot_date")
    for _, row in df.iterrows():
        tx_date = _parse_date(row.get(tx_col)) if tx_col else None
        snap_date = _parse_date(row.get(snap_col)) if snap_col else None
        if tx_date is None and snap_date is not None:
            tx_date = snap_date
        if snap_date is None and tx_date is not None:
            snap_date = tx_date
        ev = tx_date or snap_date
        if ev is not None:
            dates.append(ev)
    if not dates:
        return False
    old_n = sum(1 for d in dates if d < cutoff)
    return old_n * 2 >= len(dates)


def _parse_decimal(v: Any) -> Decimal | None:
    s = _clean_str(v)
    if not s:
        return None
    try:
        return Decimal(s.replace(",", ""))
    except (InvalidOperation, ValueError):
        return None


def _product_token_key(raw: str | None) -> str:
    """Normalize a distributor-reported product token for identity lookup (matches legacy SKU path: strip + lower)."""
    if raw is None:
        return ""
    t = str(raw).strip().lower()
    return t if t and t != "nan" else ""


_LIFECYCLE_INELIGIBLE_EXACT = frozenset(
    {
        "inactive",
        "disabled",
        "cancelled",
        "canceled",
        "discarded",
        "retired",
        "eol",
        "end of life",
        "obsolete",
        "discontinued",
    }
)


def _product_eligible_for_dsi_auto(
    p: DimProduct,
    evidence_date: date | None,
    *,
    relax_inactive_for_historical_dsi: bool = False,
) -> bool:
    """Whether a Product Master row may receive **automatic** DSI resolution (never silent pick).

    Inactive / clearly retired-lifecycle strings / outside launch–retire window for the evidence date
    are ineligible. Empty ``lifecycle_status`` does not alone disqualify if ``is_active`` is true.

    When ``relax_inactive_for_historical_dsi`` is true (predominantly historical DSI file), any row
    present in Product Master is treated as eligible for automatic resolution: inactive, lifecycle
    strings, and launch/retire **date** windows are not applied (historical sell-out can predate
    current master dates).
    """
    if not relax_inactive_for_historical_dsi:
        if not bool(getattr(p, "is_active", True)):
            return False
        ls = (getattr(p, "lifecycle_status", None) or "").strip().lower()
        if ls:
            if ls in _LIFECYCLE_INELIGIBLE_EXACT:
                return False
            for frag in ("cancel", "discard", "retire", "obsolete", "inactive", "disabled", "discontinued"):
                if frag in ls:
                    return False
        if evidence_date is not None:
            rd = getattr(p, "retired_date", None)
            if rd is not None and rd < evidence_date:
                return False
            ld = getattr(p, "launch_date", None)
            if ld is not None and ld > evidence_date:
                return False
    return True


def _product_snapshot_for_dsi_context(p: DimProduct) -> dict[str, Any]:
    """Compact, JSON-safe row snapshot for mapping-queue / steward context."""
    ld = getattr(p, "launch_date", None)
    rd = getattr(p, "retired_date", None)
    return {
        "product_id": int(p.id),
        "sku": (p.sku or "")[:128],
        "part_number": (p.part_number or "")[:128] if p.part_number else None,
        "sales_model_name": (p.sales_model_name or "")[:160] if p.sales_model_name else None,
        "is_active": bool(p.is_active),
        "lifecycle_status": (p.lifecycle_status or "")[:64] if p.lifecycle_status else None,
        "launch_date": ld.isoformat() if ld else None,
        "retired_date": rd.isoformat() if rd else None,
    }


@dataclass
class ProductResolutionEvidence:
    """Merged onto ``ImportEntityMappingCandidate.context`` for unresolved product tokens."""

    ambiguous_eligible: dict[str, Any] | None = None
    inactive_hits: list[dict[str, Any]] = field(default_factory=list)


def _merge_product_resolution_evidence(bucket: dict[str, Any], ev: ProductResolutionEvidence | None) -> None:
    """Accumulate per-token evidence across staging rows (same normalized product_identifier)."""
    if ev is None or (not ev.inactive_hits and ev.ambiguous_eligible is None):
        return
    acc = bucket.setdefault("_pe_acc", {"inh": [], "amb": None, "seen": set()})
    seen: set[tuple[str, int]] = acc["seen"]
    if ev.ambiguous_eligible:
        acc["amb"] = ev.ambiguous_eligible
    for hit in ev.inactive_hits:
        sid = (str(hit.get("tier") or ""), int(hit.get("product_id") or 0))
        if sid[1] <= 0:
            continue
        if sid in seen:
            continue
        seen.add(sid)
        acc["inh"].append(hit)
        if len(acc["inh"]) >= 20:
            break


def _multimap_from_pairs(pairs: list[tuple[str, int]]) -> dict[str, tuple[int, ...]]:
    """Build key -> sorted unique product ids (empty keys dropped)."""
    buckets: dict[str, list[int]] = defaultdict(list)
    for k, pid in pairs:
        if k:
            buckets[k].append(pid)
    return {k: tuple(sorted(set(v))) for k, v in buckets.items()}


@dataclass(frozen=True)
class ProductResolutionIndex:
    """Precomputed DSI product identity lookups (DimProduct + ProductAlias)."""

    sku_to_id: dict[str, int]
    part_number_to_ids: dict[str, tuple[int, ...]]
    sales_model_name_to_ids: dict[str, tuple[int, ...]]
    model_name_to_ids: dict[str, tuple[int, ...]]
    marketing_name_to_ids: dict[str, tuple[int, ...]]
    ean_to_ids: dict[str, tuple[int, ...]]
    upc_to_ids: dict[str, tuple[int, ...]]
    alias_value_to_ids: dict[str, tuple[int, ...]]
    products_by_id: dict[int, DimProduct]
    #: Token key → product_id for steward-approved import aliases (``confidence == "steward_approved"``).
    #: Applied before automatic tiers so explicit steward bindings survive inactive SKU collisions,
    #: ambiguous identity tiers, and historical (inactive) Product Master targets.
    steward_alias_by_key: dict[str, int]


def _load_product_resolution_index(db: Session) -> ProductResolutionIndex:
    """Load Product Master identity fields + ProductAlias (cached, narrow SELECT — no specs_json)."""
    from app.services.imports.product_resolution_index_cache import get_product_resolution_index

    return get_product_resolution_index(db)


@dataclass
class DSIResolutionCache:
    """Pre-loaded master data for O(1) per-row entity resolution.

    Replaces 4–6 per-row DB round-trips (distributor alias scan, DimDistributor
    table scan, customer alias scan, DimCustomer code lookup, DimCustomer name
    lookup) with in-memory lookups built from a single pre-load before the row
    loop.

    Build via ``_build_resolution_cache`` before calling the processing loop.
    """

    # Distributors
    all_distributors: list  # list[DimDistributor]
    dist_aliases: list  # list[DistributorSourceTokenAlias], status == "approved"
    # Customers
    all_customers: list  # list[DimCustomer] — for AI candidate slice without per-row SELECT
    customer_code_to_id: dict  # lower_strip(code) → customer_id
    customer_name_to_ids: dict  # lower_strip(name) → [customer_id, …]
    cust_aliases: list  # list[CustomerSourceTokenAlias], status == "approved"
    open_channel_cid: int | None  # DimCustomer.id where code == OPEN_CHANNEL_CUSTOMER_CODE


def _build_resolution_cache(db: Session, source_def_id: int | None) -> "DSIResolutionCache":
    """Load all DSI entity-resolution reference tables in one pass before the row loop."""
    all_distributors = list(db.scalars(select(DimDistributor)).all())
    dist_aliases = list(
        db.scalars(
            select(DistributorSourceTokenAlias).where(DistributorSourceTokenAlias.status == "approved")
        ).all()
    )

    all_customers = list(db.scalars(select(DimCustomer)).all())
    customer_code_to_id: dict[str, int] = {}
    customer_name_to_ids: dict[str, list[int]] = {}
    for c in all_customers:
        ck = (c.code or "").strip().lower()
        if ck:
            customer_code_to_id[ck] = int(c.id)
        nk = (c.name or "").strip().lower()
        if nk:
            customer_name_to_ids.setdefault(nk, []).append(int(c.id))

    cust_aliases = list(
        db.scalars(
            select(CustomerSourceTokenAlias).where(CustomerSourceTokenAlias.status == "approved")
        ).all()
    )

    open_channel_cid = db.scalar(
        select(DimCustomer.id).where(DimCustomer.code == OPEN_CHANNEL_CUSTOMER_CODE)
    )

    logger.info(
        "_build_resolution_cache: distributors=%d dist_aliases=%d customers=%d cust_aliases=%d",
        len(all_distributors),
        len(dist_aliases),
        len(all_customers),
        len(cust_aliases),
    )
    return DSIResolutionCache(
        all_distributors=all_distributors,
        dist_aliases=dist_aliases,
        all_customers=all_customers,
        customer_code_to_id=customer_code_to_id,
        customer_name_to_ids=customer_name_to_ids,
        cust_aliases=cust_aliases,
        open_channel_cid=int(open_channel_cid) if open_channel_cid is not None else None,
    )


def _build_distributor_resolution_cache(db: Session, source_def_id: int | None = None) -> "DSIResolutionCache":
    """Distributor-only resolution cache — loads ``dim_distributor`` + approved aliases only.

    Shipment evidence import resolves products via an in-memory index and defers customer
    resolution to the steward step, so it never needs the (potentially large) customer tables.
    Loading only distributors keeps the one-time pre-load cheap.
    """
    _ = source_def_id  # alias rows are filtered per-token at resolve time
    all_distributors = list(db.scalars(select(DimDistributor)).all())
    dist_aliases = list(
        db.scalars(
            select(DistributorSourceTokenAlias).where(DistributorSourceTokenAlias.status == "approved")
        ).all()
    )
    return DSIResolutionCache(
        all_distributors=all_distributors,
        dist_aliases=dist_aliases,
        all_customers=[],
        customer_code_to_id={},
        customer_name_to_ids={},
        cust_aliases=[],
        open_channel_cid=None,
    )


def _shipment_disambiguate_product_id(
    db: Session | None,
    distributor_id: int | None,
    evidence_date: date | None,
    raw: str | None,
    candidate_ids: list[int],
    corr_cache: Any = None,
) -> tuple[int | None, str | None]:
    """If shipment evidence points at exactly one product in ``candidate_ids``, return (id, scope).

    ``scope`` is ``distinct_ids_scope`` from :func:`shipment_corroboration_for_product` when a match
    was used (``distributor_specific`` | ``cross_distributor``), else ``None``.

    When ``corr_cache`` (a ``ShipmentCorroborationCache``) is supplied, uses in-memory lookups
    instead of per-row DB queries.
    """
    if (db is None and corr_cache is None) or distributor_id is None or evidence_date is None or not candidate_ids:
        return None, None
    if corr_cache is not None:
        sc = corr_cache.product_corroboration(
            int(distributor_id),
            evidence_date,
            raw_product_token=raw,
            resolved_product_id=None,
        )
    else:
        sc = shipment_corroboration_for_product(
            db,
            distributor_id=int(distributor_id),
            evidence_date=evidence_date,
            raw_product_token=raw,
            resolved_product_id=None,
        )
    if not sc:
        return None, None
    dps = sc.get("distinct_resolved_product_ids")
    if not isinstance(dps, list) or not dps:
        return None, None
    scope = sc.get("distinct_ids_scope") if isinstance(sc.get("distinct_ids_scope"), str) else None
    elig = {int(x) for x in candidate_ids if int(x) > 0}
    inter = elig & {int(x) for x in dps if x is not None}
    if len(inter) == 1:
        return int(next(iter(inter))), scope
    return None, None


def _resolve_product(
    raw: str | None,
    idx: ProductResolutionIndex,
    evidence_date: date | None = None,
    *,
    relax_inactive_dim_product_for_historical_dsi: bool = False,
    db: Session | None = None,
    distributor_id: int | None = None,
    corr_cache: Any = None,
) -> tuple[int | None, str | None, str | None, ProductResolutionEvidence | None]:
    """Resolve RAW product_identifier to dim_product.id with lifecycle-aware eligibility.

    **Steward-approved aliases** (``ProductAlias.confidence == "steward_approved"``), keyed like other
    lookups via ``_product_token_key``, are evaluated **first**. They bind distributor-reported tokens to
    Product Master rows chosen by a human and must survive revalidation even when an inactive SKU or
    ambiguous identity tier would otherwise block automatic resolution (including inactive targets for
    historical DSI evidence).

    Automatic tier order: SKU → part_number → sales_model_name → model_name → marketing_name → ean → upc
    → non-steward ProductAlias. Within a tier: **only eligible** rows may auto-resolve; multiple eligible
    hits defer ambiguity until lower tiers (e.g. a clarifying alias) are tried. When multiple eligible
    hits remain, **shipment evidence** (same distributor + calendar month, ``resolved_unique`` lines) may
    disambiguate if exactly one distinct shipment ``product_id`` intersects the eligible id set.
    Ineligible-only hits at a tier are recorded and the walk **continues**.

    Returns ``(product_id, error_code, success_diagnostic, evidence)``. ``evidence`` is populated when
    returning ``ambiguous_product_match`` or ``unresolved_product_inactive_only`` for mapping-queue context.
    """
    key = _product_token_key(raw)
    if not key:
        return None, "missing_product_token", None, None

    sid = idx.steward_alias_by_key.get(key)
    if sid is not None:
        p_st = idx.products_by_id.get(int(sid))
        if p_st is not None:
            return int(sid), None, "product_resolved_steward_alias", None

    def _eligible_ids(ids: tuple[int, ...]) -> list[int]:
        out: list[int] = []
        for i in ids:
            p = idx.products_by_id.get(int(i))
            if p is not None and _product_eligible_for_dsi_auto(
                p,
                evidence_date,
                relax_inactive_for_historical_dsi=relax_inactive_dim_product_for_historical_dsi,
            ):
                out.append(int(i))
        return out

    def _inactive_snapshots(tier: str, ids: tuple[int, ...]) -> list[dict[str, Any]]:
        snaps: list[dict[str, Any]] = []
        for i in ids:
            p = idx.products_by_id.get(int(i))
            if p is None:
                continue
            if _product_eligible_for_dsi_auto(
                p,
                evidence_date,
                relax_inactive_for_historical_dsi=relax_inactive_dim_product_for_historical_dsi,
            ):
                continue
            s = _product_snapshot_for_dsi_context(p)
            s["tier"] = tier
            snaps.append(s)
        return snaps

    accumulated = ProductResolutionEvidence()
    pending_ambiguous: ProductResolutionEvidence | None = None

    pid = idx.sku_to_id.get(key)
    if pid is not None:
        p0 = idx.products_by_id.get(int(pid))
        if p0 is not None and _product_eligible_for_dsi_auto(
            p0,
            evidence_date,
            relax_inactive_for_historical_dsi=relax_inactive_dim_product_for_historical_dsi,
        ):
            return int(pid), None, "product_resolved_sku", None
        if p0 is not None:
            accumulated.inactive_hits.extend(_inactive_snapshots("sku", (pid,)))

    tier_maps: tuple[tuple[dict[str, tuple[int, ...]], str], ...] = (
        (idx.part_number_to_ids, "part_number"),
        (idx.sales_model_name_to_ids, "sales_model_name"),
        (idx.model_name_to_ids, "model_name"),
        (idx.marketing_name_to_ids, "marketing_name"),
        (idx.ean_to_ids, "ean"),
        (idx.upc_to_ids, "upc"),
    )
    tag_for_tier = {
        "part_number": "product_resolved_part_number",
        "sales_model_name": "product_resolved_sales_model_name",
        "model_name": "product_resolved_model_name",
        "marketing_name": "product_resolved_marketing_name",
        "ean": "product_resolved_ean",
        "upc": "product_resolved_upc",
    }
    for mmap, tier in tier_maps:
        ids = mmap.get(key)
        if not ids:
            continue
        elig = _eligible_ids(ids)
        if len(elig) == 1:
            return int(elig[0]), None, tag_for_tier[tier], None
        if len(elig) > 1:
            pick, ship_scope = _shipment_disambiguate_product_id(db, distributor_id, evidence_date, raw, elig, corr_cache=corr_cache)
            if pick is not None:
                tag = f"{tag_for_tier[tier]}_shipment_disambiguated"
                if ship_scope == "cross_distributor":
                    tag = f"{tag}_cross_distributor"
                return int(pick), None, tag, None
            snaps = [_product_snapshot_for_dsi_context(idx.products_by_id[i]) for i in sorted(set(elig))]
            amb: dict[str, Any] = {
                "tier": tier,
                "product_ids": sorted(set(elig)),
                "eligible_products": snaps[:12],
            }
            pending_ambiguous = ProductResolutionEvidence(ambiguous_eligible=amb)
            continue
        in_sn = _inactive_snapshots(tier, ids)
        accumulated.inactive_hits.extend(in_sn)

    a_ids = idx.alias_value_to_ids.get(key)
    if a_ids:
        elig_a: list[int] = []
        for aid in a_ids:
            p = idx.products_by_id.get(int(aid))
            if p is not None and _product_eligible_for_dsi_auto(
                p,
                evidence_date,
                relax_inactive_for_historical_dsi=relax_inactive_dim_product_for_historical_dsi,
            ):
                elig_a.append(int(aid))
        if len(elig_a) == 1:
            return int(elig_a[0]), None, "product_resolved_alias", None
        if len(elig_a) > 1:
            pick, ship_scope = _shipment_disambiguate_product_id(db, distributor_id, evidence_date, raw, elig_a, corr_cache=corr_cache)
            if pick is not None:
                tag = "product_resolved_alias_shipment_disambiguated"
                if ship_scope == "cross_distributor":
                    tag = f"{tag}_cross_distributor"
                return int(pick), None, tag, None
            snaps = [_product_snapshot_for_dsi_context(idx.products_by_id[i]) for i in sorted(set(elig_a))]
            amb = {
                "tier": "product_alias",
                "product_ids": sorted(set(elig_a)),
                "eligible_products": snaps[:12],
            }
            return None, "ambiguous_product_alias", None, ProductResolutionEvidence(ambiguous_eligible=amb)
        in_sn = _inactive_snapshots("product_alias", a_ids)
        accumulated.inactive_hits.extend(in_sn)

    if pending_ambiguous is not None and pending_ambiguous.ambiguous_eligible:
        amb = pending_ambiguous.ambiguous_eligible
        pids: list[int] = []
        for x in (amb.get("product_ids") or []):
            try:
                v = int(x)
            except (TypeError, ValueError):
                continue
            if v > 0:
                pids.append(v)
        if len(pids) > 1:
            pick, ship_scope = _shipment_disambiguate_product_id(db, distributor_id, evidence_date, raw, pids, corr_cache=corr_cache)
            if pick is not None:
                tier = str(amb.get("tier") or "unknown_tier")
                tag = f"product_resolved_{tier}_shipment_disambiguated"
                if ship_scope == "cross_distributor":
                    tag = f"{tag}_cross_distributor"
                return int(pick), None, tag, None
        return None, "ambiguous_product_match", None, pending_ambiguous
    if accumulated.inactive_hits:
        return None, "unresolved_product_inactive_only", None, accumulated
    return None, "unresolved_product", None, None


def _alias_distributor_id(db: Session, source_id: int | None, normalized_token: str) -> int | None:
    if not normalized_token:
        return None
    q = select(DistributorSourceTokenAlias.distributor_id).where(
        DistributorSourceTokenAlias.normalized_token == normalized_token,
        DistributorSourceTokenAlias.status == "approved",
    )
    if source_id is not None:
        q = q.where(
            or_(
                DistributorSourceTokenAlias.source_definition_id.is_(None),
                DistributorSourceTokenAlias.source_definition_id == source_id,
            )
        )
    rows = list(dict.fromkeys(db.scalars(q).all()))
    if len(rows) == 1:
        return int(rows[0])
    return None


def _resolve_distributor(db: Session, raw: str | None, source_id: int | None = None) -> tuple[int | None, str | None]:
    if not raw or not str(raw).strip():
        return None, "missing_distributor_cell_value"
    token = raw.strip().lower()
    nt = _norm_key(raw)
    alias_id = _alias_distributor_id(db, source_id, nt)
    if alias_id is not None:
        return alias_id, None
    for d in db.scalars(select(DimDistributor)).all():
        if d.code.strip().lower() == token or d.name.strip().lower() == token:
            return d.id, None
        if token in d.name.strip().lower() or d.name.strip().lower() in token:
            # avoid loose substring false positives for very short tokens
            if len(token) >= 4:
                return d.id, None
    return None, "unresolved_distributor_token"


def _resolve_distributor_from_cache(
    raw: str | None,
    source_id: int | None,
    res_cache: "DSIResolutionCache",
) -> tuple[int | None, str | None]:
    """In-memory equivalent of ``_resolve_distributor`` — zero DB queries.

    Replaces two per-row round-trips (alias query + DimDistributor table scan)
    with lookups against pre-loaded lists from ``DSIResolutionCache``.
    """
    if not raw or not str(raw).strip():
        return None, "missing_distributor_cell_value"
    token = raw.strip().lower()
    nt = _norm_key(raw)

    # Alias lookup (in memory)
    if nt:
        matches: list[int] = []
        for a in res_cache.dist_aliases:
            if a.normalized_token != nt:
                continue
            if (
                source_id is not None
                and a.source_definition_id is not None
                and a.source_definition_id != source_id
            ):
                continue
            matches.append(int(a.distributor_id))
        unique = list(dict.fromkeys(matches))
        if len(unique) == 1:
            return unique[0], None

    # DimDistributor scan (in memory)
    for d in res_cache.all_distributors:
        if d.code.strip().lower() == token or d.name.strip().lower() == token:
            return d.id, None
        if token in d.name.strip().lower() or d.name.strip().lower() in token:
            if len(token) >= 4:
                return d.id, None

    return None, "unresolved_distributor_token"


def _resolve_distributor_strict_from_cache(
    raw: str | None,
    source_id: int | None,
    res_cache: "DSIResolutionCache",
) -> tuple[int | None, str | None]:
    """In-memory equivalent of ``_resolve_distributor_strict`` — zero DB queries.

    Mirrors the shipment-evidence strict resolver: **approved aliases** (unique match) then
    **exact** code/name equality only. No substring heuristics (governance: shipment evidence
    must not mis-bind tokens). Replaces the per-row alias query + full ``DimDistributor`` table
    scan with lookups against the pre-loaded ``DSIResolutionCache``.
    """
    if not raw or not str(raw).strip():
        return None, "missing_distributor_cell_value"
    token = raw.strip().lower()
    nt = _norm_key(raw)

    if nt:
        matches: list[int] = []
        for a in res_cache.dist_aliases:
            if a.normalized_token != nt:
                continue
            if (
                source_id is not None
                and a.source_definition_id is not None
                and a.source_definition_id != source_id
            ):
                continue
            matches.append(int(a.distributor_id))
        unique = list(dict.fromkeys(matches))
        if len(unique) == 1:
            return unique[0], None

    for d in res_cache.all_distributors:
        if d.code.strip().lower() == token or d.name.strip().lower() == token:
            return d.id, None

    return None, "unresolved_distributor_token"


def _resolve_distributor_strict(db: Session, raw: str | None, source_id: int | None = None) -> tuple[int | None, str | None]:
    """Resolve distributor using **approved aliases** and **exact** code/name equality only.

    Used by shipment evidence imports so steward-approved aliases drive resolution without
    substring heuristics that can mis-bind tokens.
    """
    if not raw or not str(raw).strip():
        return None, "missing_distributor_cell_value"
    token = raw.strip().lower()
    nt = _norm_key(raw)
    alias_id = _alias_distributor_id(db, source_id, nt)
    if alias_id is not None:
        return alias_id, None
    for d in db.scalars(select(DimDistributor)).all():
        if d.code.strip().lower() == token or d.name.strip().lower() == token:
            return d.id, None
    return None, "unresolved_distributor_token"


def _open_channel_customer_id(db: Session) -> int | None:
    return db.scalar(select(DimCustomer.id).where(DimCustomer.code == OPEN_CHANNEL_CUSTOMER_CODE))


def _alias_customer_id(
    db: Session,
    source_id: int | None,
    distributor_id: int | None,
    normalized_customer: str,
    dealer_group: str | None,
) -> int | None:
    if not normalized_customer:
        return None
    q = select(CustomerSourceTokenAlias.customer_id).where(
        CustomerSourceTokenAlias.normalized_token == normalized_customer,
        CustomerSourceTokenAlias.status == "approved",
    )
    if source_id is not None:
        q = q.where(
            or_(
                CustomerSourceTokenAlias.source_definition_id.is_(None),
                CustomerSourceTokenAlias.source_definition_id == source_id,
            )
        )
    if distributor_id is not None:
        q = q.where(
            or_(
                CustomerSourceTokenAlias.distributor_id.is_(None),
                CustomerSourceTokenAlias.distributor_id == distributor_id,
            )
        )
    rows = list(dict.fromkeys(db.scalars(q).all()))
    if len(rows) == 1:
        return int(rows[0])
    return None


def _resolve_customer(
    db: Session,
    *,
    source_id: int | None,
    distributor_id: int | None,
    customer_raw: str | None,
    dealer_group_raw: str | None,
    channel_raw: str | None,
    open_flag_raw: Any,
) -> tuple[int | None, list[str]]:
    """Returns (customer_id, diagnostic_codes)."""
    _ = channel_raw  # reserved; open-channel auto-assign uses explicit evidence column only
    diagnostics: list[str] = []
    nt = _norm_key(customer_raw)
    dg = _clean_str(dealer_group_raw)

    if dg and any(x in dg.lower() for x in DEALER_GROUP_PLACEHOLDER_SUBSTRINGS):
        diagnostics.append("dealer_group_placeholder")

    alias_id: int | None = None
    if not _customer_token_is_placeholder(nt, customer_raw):
        alias_id = _alias_customer_id(db, source_id, distributor_id, nt, dg)
        if alias_id is not None:
            diagnostics.append("customer_resolved_alias")
            return alias_id, diagnostics
    elif nt or (customer_raw and str(customer_raw).strip()):
        diagnostics.append("customer_token_placeholder")
        nt = ""

    open_from_col = False
    if open_flag_raw is not None:
        s = str(open_flag_raw).strip().lower()
        open_from_col = s in ("1", "true", "yes", "y", "x")

    # Open Channel assignment requires **explicit** workbook evidence (`open_channel_evidence` column).
    # Channel-key text alone must not imply OPEN_CHANNEL when the customer token is blank.
    if (not nt) and open_from_col:
        oc = _open_channel_customer_id(db)
        if oc:
            diagnostics.append("customer_open_channel")
            return oc, diagnostics
        diagnostics.append("open_channel_missing_dim")
        return None, diagnostics

    if not nt:
        diagnostics.append("missing_customer_token")
        return None, diagnostics

    if nt in SENTINEL_CUSTOMER_TOKENS:
        diagnostics.append("customer_sentinel_unresolved")
        return None, diagnostics

    stmt = select(DimCustomer.id).where(func.lower(DimCustomer.code) == nt)
    cid = db.scalar(stmt)
    if cid:
        diagnostics.append("customer_resolved_code")
        return int(cid), diagnostics

    stmt2 = select(DimCustomer.id).where(func.lower(DimCustomer.name) == nt)
    ids = list(db.scalars(stmt2).all())
    if len(ids) == 1:
        diagnostics.append("customer_resolved_exact_name")
        return int(ids[0]), diagnostics
    if len(ids) > 1:
        diagnostics.append("ambiguous_customer_name")
        return None, diagnostics

    # Open Channel **evidence column** only: after dim/alias could not resolve a non-empty token,
    # treat explicit workbook evidence as intent to post to OPEN_CHANNEL (report profile).
    # Channel-key text alone must not override a named dealer/customer token (historical RAW rows).
    if open_from_col:
        oc_force = _open_channel_customer_id(db)
        if oc_force:
            diagnostics.append("customer_open_channel_evidence_override")
            return int(oc_force), diagnostics

    diagnostics.append("customer_unresolved")
    return None, diagnostics


def _resolve_customer_from_cache(
    *,
    source_id: int | None,
    distributor_id: int | None,
    customer_raw: str | None,
    dealer_group_raw: str | None,
    channel_raw: str | None,
    open_flag_raw: Any,
    res_cache: "DSIResolutionCache",
) -> tuple[int | None, list[str]]:
    """In-memory equivalent of ``_resolve_customer`` — zero DB queries.

    Replaces up to four per-row round-trips (alias query, OPEN_CHANNEL lookup,
    code lookup, name lookup) with dict/list lookups against ``DSIResolutionCache``.
    """
    _ = channel_raw
    diagnostics: list[str] = []
    nt = _norm_key(customer_raw)
    dg = _clean_str(dealer_group_raw)

    if dg and any(x in dg.lower() for x in DEALER_GROUP_PLACEHOLDER_SUBSTRINGS):
        diagnostics.append("dealer_group_placeholder")

    if not _customer_token_is_placeholder(nt, customer_raw):
        if nt:
            matches: list[int] = []
            for a in res_cache.cust_aliases:
                if a.normalized_token != nt:
                    continue
                if (
                    source_id is not None
                    and a.source_definition_id is not None
                    and a.source_definition_id != source_id
                ):
                    continue
                if (
                    distributor_id is not None
                    and a.distributor_id is not None
                    and a.distributor_id != distributor_id
                ):
                    continue
                matches.append(int(a.customer_id))
            unique = list(dict.fromkeys(matches))
            if len(unique) == 1:
                diagnostics.append("customer_resolved_alias")
                return unique[0], diagnostics
    elif nt or (customer_raw and str(customer_raw).strip()):
        diagnostics.append("customer_token_placeholder")
        nt = ""

    open_from_col = False
    if open_flag_raw is not None:
        s = str(open_flag_raw).strip().lower()
        open_from_col = s in ("1", "true", "yes", "y", "x")

    if (not nt) and open_from_col:
        if res_cache.open_channel_cid:
            diagnostics.append("customer_open_channel")
            return res_cache.open_channel_cid, diagnostics
        diagnostics.append("open_channel_missing_dim")
        return None, diagnostics

    if not nt:
        diagnostics.append("missing_customer_token")
        return None, diagnostics

    if nt in SENTINEL_CUSTOMER_TOKENS:
        diagnostics.append("customer_sentinel_unresolved")
        return None, diagnostics

    cid = res_cache.customer_code_to_id.get(nt)
    if cid is not None:
        diagnostics.append("customer_resolved_code")
        return cid, diagnostics

    ids = res_cache.customer_name_to_ids.get(nt, [])
    if len(ids) == 1:
        diagnostics.append("customer_resolved_exact_name")
        return ids[0], diagnostics
    if len(ids) > 1:
        diagnostics.append("ambiguous_customer_name")
        return None, diagnostics

    if open_from_col:
        if res_cache.open_channel_cid:
            diagnostics.append("customer_open_channel_evidence_override")
            return res_cache.open_channel_cid, diagnostics

    diagnostics.append("customer_unresolved")
    return None, diagnostics


def _build_mapped_canonical(
    row: pd.Series,
    mapping: dict[str, str],
    ignored_cols: list[str],
) -> dict[str, Any]:
    """Build JSON-serializable canonical snapshot (Excel/pandas cells may be Timestamp, numpy, Decimal)."""
    out: dict[str, Any] = {}
    for src, tgt in mapping.items():
        if tgt in CANONICAL and tgt != "ignored_shipping_evidence":
            v = row.get(src)
            if v is not None and not (isinstance(v, float) and pd.isna(v)):
                out[tgt] = to_jsonable(v)
    if ignored_cols:
        ship: dict[str, Any] = {}
        for c in ignored_cols:
            if c in row.index:
                v = row.get(c)
                if v is not None and not (isinstance(v, float) and pd.isna(v)):
                    ship[str(c)] = to_jsonable(v)
        if ship:
            out["ignored_shipping_evidence"] = ship
    return out


_DSI_STAGING_INSERT_CHUNK = 2000  # pg_insert param cap (~25 cols × 2000 < 65535)
_DSI_VALIDATE_COMMIT_INTERVAL = 50000


@dataclass
class _DsiValidateProfile:
    enabled: bool = False
    upfront_s: float = 0.0
    row_loop_s: float = 0.0
    bulk_insert_s: float = 0.0
    commit_s: float = 0.0
    bulk_insert_rows: int = 0
    commit_count: int = 0
    chunk_row_loop_s: float = 0.0
    chunk_bulk_insert_s: float = 0.0
    chunk_commit_s: float = 0.0
    chunk_start_row: int = 0
    chunk_end_row: int = 0

    def start_chunk(self, start_row: int) -> None:
        self.chunk_row_loop_s = 0.0
        self.chunk_bulk_insert_s = 0.0
        self.chunk_commit_s = 0.0
        self.chunk_start_row = start_row

    def finish_chunk(self, end_row: int) -> None:
        self.chunk_end_row = end_row
        if not self.enabled:
            return
        rows = max(1, end_row - self.chunk_start_row + 1)
        logger.info(
            "DSI validate profile chunk rows %d-%d: row_loop=%.2fs bulk_insert=%.2fs commit=%.2fs (%.1f rows/s)",
            self.chunk_start_row,
            end_row,
            self.chunk_row_loop_s,
            self.chunk_bulk_insert_s,
            self.chunk_commit_s,
            rows / max(0.001, self.chunk_row_loop_s + self.chunk_bulk_insert_s + self.chunk_commit_s),
        )

    def log_summary(self, *, total_rows: int, total_s: float) -> None:
        if not self.enabled:
            return
        logger.info(
            "DSI validate profile summary job rows=%d total=%.2fs upfront=%.2fs row_loop=%.2fs "
            "bulk_insert=%.2fs (%d rows) commit=%.2fs (%d commits) overall=%.1f rows/s",
            total_rows,
            total_s,
            self.upfront_s,
            self.row_loop_s,
            self.bulk_insert_s,
            self.bulk_insert_rows,
            self.commit_s,
            self.commit_count,
            total_rows / max(0.001, total_s),
        )


def _dsi_validate_profile_enabled() -> bool:
    return os.environ.get("CIP_DSI_VALIDATE_PROFILE", "").strip() == "1"


def _evidence_months_from_df(df: pd.DataFrame, date_col: str | None) -> set[str]:
    """Vectorized evidence-month extraction (avoids Python loop over 169k cells)."""
    if not date_col or date_col not in df.columns:
        return set()
    parsed = pd.to_datetime(df[date_col], errors="coerce")
    months = parsed.dropna().dt.strftime("%Y-%m").unique()
    return {str(m) for m in months if m}


def _raw_payload_at_index(df: pd.DataFrame, row_index: int) -> dict[str, Any]:
    return {str(c): to_jsonable(df.iat[row_index, j]) for j, c in enumerate(df.columns)}


def _build_mapped_canonical_at_index(
    df: pd.DataFrame,
    row_index: int,
    mapping: dict[str, str],
    ignored_cols: list[str],
    col_index: dict[str, int],
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for src, tgt in mapping.items():
        if tgt in CANONICAL and tgt != "ignored_shipping_evidence":
            if src not in col_index:
                continue
            v = df.iat[row_index, col_index[src]]
            if v is not None and not (isinstance(v, float) and pd.isna(v)):
                out[tgt] = to_jsonable(v)
    if ignored_cols:
        ship: dict[str, Any] = {}
        for c in ignored_cols:
            if c in col_index:
                v = df.iat[row_index, col_index[c]]
                if v is not None and not (isinstance(v, float) and pd.isna(v)):
                    ship[str(c)] = to_jsonable(v)
        if ship:
            out["ignored_shipping_evidence"] = ship
    return out


def _cell_str(df: pd.DataFrame, row_index: int, col: str | None, col_index: dict[str, int]) -> str | None:
    if not col or col not in col_index:
        return None
    return _clean_str(df.iat[row_index, col_index[col]])


def _cell_raw(df: pd.DataFrame, row_index: int, col: str | None, col_index: dict[str, int]) -> Any:
    if not col or col not in col_index:
        return None
    return df.iat[row_index, col_index[col]]


def _staging_line_row_dict(
    *,
    job_id: int,
    source_row_number: int,
    raw_payload: dict[str, Any],
    mapped: dict[str, Any],
    dist_raw: str | None,
    cust_raw: str | None,
    dg_raw: str | None,
    prod_raw: str | None,
    rdistributor_id: int | None,
    rcustomer_id: int | None,
    rpid: int | None,
    tx_date: date | None,
    invoice_no_val: str | None,
    snap_date: date | None,
    qty_sold: Decimal | None,
    soh: Decimal | None,
    unit_price: Decimal | None,
    reported_rev: Decimal | None,
    computed_rev: Decimal | None,
    cur: str | None,
    res_status: str,
    diag: list[str],
    sev: str,
) -> dict[str, Any]:
    return {
        "import_job_id": job_id,
        "source_row_number": source_row_number,
        "raw_row_payload": raw_payload,
        "mapped_canonical": mapped,
        "raw_distributor_token": dist_raw,
        "raw_customer_dealer_token": cust_raw,
        "raw_dealer_group_token": dg_raw,
        "raw_product_token": prod_raw,
        "resolved_distributor_id": rdistributor_id,
        "resolved_customer_id": rcustomer_id,
        "resolved_product_id": rpid,
        "transaction_date": tx_date,
        "invoice_no": invoice_no_val,
        "snapshot_date": snap_date,
        "quantity_sold": float(qty_sold) if qty_sold is not None else None,
        "stock_on_hand": float(soh) if soh is not None else None,
        "unit_sellout_price_ex_tax_amount": float(unit_price) if unit_price is not None else None,
        "reported_revenue_amount": float(reported_rev) if reported_rev is not None else None,
        "computed_revenue_amount": float(computed_rev) if computed_rev is not None else None,
        "currency_code": (cur[:8] if cur else None),
        "resolution_status": res_status,
        "diagnostic_codes": diag,
        "severity": sev,
        "apply_status": "pending",
    }


def _flush_dsi_staging_batch(db: Session, rows: list[dict[str, Any]]) -> None:
    """Bulk insert staging lines in one statement (validate deletes job lines first)."""
    if not rows:
        return
    t = ImportDistributorSiStagingLine.__table__
    with db.begin_nested():
        db.execute(pg_insert(t).values(rows))


def _update_dsi_validate_checkpoint_metadata(
    db: Session,
    job: ImportJob,
    *,
    rows_committed: int,
    phase: str,
) -> None:
    """In-session checkpoint metadata (no commit) for progress between durable commits."""
    from sqlalchemy.orm.attributes import flag_modified

    meta = dict(job.staged_metadata or {})
    meta["dsi_validate_rows_committed"] = int(rows_committed)
    meta["dsi_validate_phase"] = phase
    meta["dsi_validate_checkpoint_at"] = datetime.now(timezone.utc).isoformat()
    job.staged_metadata = to_jsonable(meta)
    flag_modified(job, "staged_metadata")
    db.add(job)
    db.flush()


def _persist_dsi_validate_checkpoint(
    db: Session,
    job: ImportJob,
    *,
    rows_committed: int,
    phase: str,
    profile: _DsiValidateProfile | None = None,
) -> None:
    """Commit staged rows + checkpoint metadata so pooler drops do not lose prior chunks."""
    t0 = time.monotonic() if profile and profile.enabled else 0.0
    _update_dsi_validate_checkpoint_metadata(
        db, job, rows_committed=rows_committed, phase=phase
    )
    db.commit()
    if profile and profile.enabled:
        profile.commit_s += time.monotonic() - t0
        profile.commit_count += 1
        profile.chunk_commit_s += time.monotonic() - t0


def _flush_dsi_staging_buffer(
    db: Session,
    job: ImportJob,
    buffer: list[dict[str, Any]],
    *,
    last_row_number: int,
    phase: str = "processing_rows",
    commit_checkpoint: bool = True,
    profile: _DsiValidateProfile | None = None,
) -> None:
    """Flush buffer to DB; commit only when ``commit_checkpoint`` (durability vs throughput)."""
    if not buffer:
        if commit_checkpoint:
            _persist_dsi_validate_checkpoint(
                db, job, rows_committed=last_row_number, phase=phase, profile=profile
            )
        return
    row_count = len(buffer)
    t0 = time.monotonic() if profile and profile.enabled else 0.0
    _flush_dsi_staging_batch(db, buffer)
    if profile and profile.enabled:
        elapsed = time.monotonic() - t0
        profile.bulk_insert_s += elapsed
        profile.bulk_insert_rows += row_count
        profile.chunk_bulk_insert_s += elapsed
    buffer.clear()
    if commit_checkpoint:
        _persist_dsi_validate_checkpoint(
            db, job, rows_committed=last_row_number, phase=phase, profile=profile
        )
    else:
        _update_dsi_validate_checkpoint_metadata(
            db, job, rows_committed=last_row_number, phase=phase
        )


def process_distributor_sales_inventory(
    db: Session,
    job: ImportJob,
    df: pd.DataFrame,
    mapping: dict[str, str],
    on_progress: Any = None,
) -> int:
    """Validate + stage (+ apply if job.import_mode == 'apply'). Returns blocking error count."""
    if "distributor_token" not in mapping.values():
        db.add(
            ImportRowResult(
                job_id=job.id,
                row_number=0,
                severity="error",
                code="missing_distributor_token_mapping",
                message="Required column mapping missing: Distributor.",
            )
        )
        return 1
    if "product_identifier" not in mapping.values():
        db.add(
            ImportRowResult(
                job_id=job.id,
                row_number=0,
                severity="error",
                code="missing_product_identifier_mapping",
                message="Required column mapping missing: product identifier (SKU / part number / model / product code).",
            )
        )
        return 1

    if job.source and isinstance(job.source.column_mapping_memory, dict):
        from app.services.imports.ai_resolver_wiring import record_format_drift_on_job

        record_format_drift_on_job(
            job,
            current_headers=[str(c) for c in df.columns],
            column_mapping_memory=job.source.column_mapping_memory,
            field_mapping=mapping,
        )

    preserved_candidate_steward: dict[tuple[str, str], dict[str, Any]] = {}
    for existing in db.scalars(
        select(ImportEntityMappingCandidate).where(ImportEntityMappingCandidate.import_job_id == job.id)
    ).all():
        ex_ctx = existing.context if isinstance(existing.context, dict) else {}
        preserved: dict[str, Any] = {}
        if isinstance(ex_ctx.get("duplicate_review"), dict):
            preserved["duplicate_review"] = dict(ex_ctx["duplicate_review"])
        if (existing.status or "").strip() == "acknowledged_unique":
            preserved["status"] = "acknowledged_unique"
        if preserved:
            preserved_candidate_steward[(existing.entity_type, existing.normalized_key)] = preserved

    db.execute(delete(ImportDistributorSiStagingLine).where(ImportDistributorSiStagingLine.import_job_id == job.id))
    db.execute(delete(ImportEntityMappingCandidate).where(ImportEntityMappingCandidate.import_job_id == job.id))
    db.flush()

    date_majority_historical = _dsi_import_predominantly_historical_by_evidence_dates(df, mapping)
    meta = dict(job.staged_metadata or {})
    explicit = str(meta.get("dsi_workflow_mode_explicit") or "auto").strip().lower()
    if explicit not in ("auto", "historical", "weekly"):
        explicit = "auto"
    if explicit == "historical":
        workflow_mode = "historical"
    elif explicit == "weekly":
        workflow_mode = "weekly"
    else:
        workflow_mode = "historical" if date_majority_historical else "weekly"
    meta["dsi_workflow_mode"] = workflow_mode
    meta["dsi_historical_product_eligibility_relaxed"] = workflow_mode == "historical"
    meta["dsi_predominantly_old_sellout_dates"] = date_majority_historical
    meta["dsi_validate_total_rows"] = len(df)
    meta["dsi_validate_rows_committed"] = 0
    meta["dsi_validate_phase"] = "loading_caches"
    meta.pop("dsi_validate_checkpoint_at", None)
    from sqlalchemy.orm.attributes import flag_modified

    job.staged_metadata = to_jsonable(meta)
    flag_modified(job, "staged_metadata")
    db.add(job)
    db.flush()

    historical_relaxed = dsi_historical_product_eligibility_relaxed_from_import_job(job)

    ignored_src_cols = [k for k, v in mapping.items() if v == "ignored_shipping_evidence"]

    prod_idx = _load_product_resolution_index(db)
    source = job.source
    source_def_id = source.id if source else None

    profile = _DsiValidateProfile(enabled=_dsi_validate_profile_enabled())
    process_t0 = time.monotonic()
    upfront_t0 = time.monotonic()

    # --- Pre-load shipment corroboration cache (2 batch queries vs N×6 per-row) ---
    from app.services.imports.dsi_shipment_corroboration import ShipmentCorroborationCache

    _date_col_for_months = _col(mapping, "transaction_date") or _col(mapping, "snapshot_date")
    _evidence_months = _evidence_months_from_df(df, _date_col_for_months)
    logger.info(
        "process_distributor_sales_inventory: job_id=%s rows=%d evidence_months=%s",
        job.id,
        len(df),
        sorted(_evidence_months),
    )

    if on_progress is not None:
        on_progress("loading_caches", "Loading resolution caches", 0, len(df))

    corr_cache = ShipmentCorroborationCache.load(db, _evidence_months)

    # Pre-load distributor + customer master data (eliminates 4–6 per-row DB round-trips)
    res_cache = _build_resolution_cache(db, source_def_id)
    # -------------------------------------------------------------------------

    from app.services.imports.dsi_import_state_awareness import (
        check_dsi_import_state,
        persist_intelligence_state_on_job,
        resolve_primary_distributor_id_from_dataframe,
    )

    primary_dist_id = resolve_primary_distributor_id_from_dataframe(db, df, mapping, source_def_id)
    intel_state = check_dsi_import_state(db, job.id, primary_dist_id)
    persist_intelligence_state_on_job(db, job, intel_state)
    db.flush()

    weekly_historical_customers: dict[tuple[int | None, str], Any] = {}
    if not dsi_historical_workflow_from_import_job(job) and source_def_id is not None:
        from app.services.imports.dsi_customer_intelligence import load_historical_customer_resolutions

        weekly_historical_customers = load_historical_customer_resolutions(
            db,
            source_definition_id=int(source_def_id),
            current_job_id=int(job.id),
        )

    if profile.enabled:
        profile.upfront_s = time.monotonic() - upfront_t0
        logger.info(
            "DSI validate profile upfront: %.2fs (corr_cache + resolution_cache + intel)",
            profile.upfront_s,
        )

    if on_progress is not None:
        on_progress("processing_rows", "Processing rows", 0, len(df))

    staging_buffer: list[dict[str, Any]] = []

    def _maybe_flush_staging(last_rn: int, *, force_commit: bool = False) -> None:
        at_commit_boundary = force_commit or (
            last_rn > 0 and last_rn % _DSI_VALIDATE_COMMIT_INTERVAL == 0
        )
        if len(staging_buffer) >= _DSI_STAGING_INSERT_CHUNK and not at_commit_boundary:
            _flush_dsi_staging_buffer(
                db,
                job,
                staging_buffer,
                last_row_number=last_rn,
                phase="processing_rows",
                commit_checkpoint=False,
                profile=profile,
            )
        elif at_commit_boundary:
            _flush_dsi_staging_buffer(
                db,
                job,
                staging_buffer,
                last_row_number=last_rn,
                phase="processing_rows",
                commit_checkpoint=True,
                profile=profile,
            )
            if profile.enabled:
                profile.finish_chunk(last_rn)
                profile.start_chunk(last_rn + 1)

    # Pre-compute reverse column lookups (mapping is immutable over the loop)
    _c_dist = _col(mapping, "distributor_token")
    _c_prod = _col(mapping, "product_identifier")
    _c_cust = _col(mapping, "customer_dealer_token")
    _c_dg = _col(mapping, "dealer_group_token")
    _c_open = _col(mapping, "open_channel_evidence")
    _c_tx = _col(mapping, "transaction_date")
    _c_inv = _col(mapping, "invoice_no")
    _c_snap = _col(mapping, "snapshot_date")
    _c_qty = _col(mapping, "quantity_sold")
    _c_soh = _col(mapping, "stock_on_hand")
    _c_price = _col(mapping, "unit_sellout_price_ex_tax_amount")
    _c_rev = _col(mapping, "reported_revenue_amount")
    _c_cur = _col(mapping, "currency_code")
    _c_channel = _col(mapping, "channel_key_token") or _col(mapping, "channel_code")
    _c_region = _col(mapping, "region_or_province_token") or _col(mapping, "region_code")
    col_index = {str(c): i for i, c in enumerate(df.columns)}

    agg: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {
            "row_count": 0,
            "total_units": Decimal(0),
            "total_value": Decimal(0),
            "samples": [],
            "strategic_channel_hint": False,
            "customer_evidence_norms": [],
            "source_customer_evidence_norms": [],
            "primary_source": None,
            "dealer_group_raw": None,
            "source_customer_raw_samples": [],
            "source_region_raw_samples": [],
            "source_channel_raw_samples": [],
            "region_evidence_norms": [],
            "channel_evidence_norms": [],
            "provisional_region_conflict": False,
            "provisional_channel_conflict": False,
        }
    )

    blocking = 0
    warnings = 0
    first_unresolved_dist_raw: str | None = None
    dsi_sellout_issue_rows = 0
    dsi_inv_ready_with_sellout_issue_rows = 0

    total_rows = len(df)
    _progress_next = time.monotonic()  # fire immediately on first eligible check
    _PROGRESS_INTERVAL = 3.0

    _memo_dist: dict[str, tuple[int | None, str | None, list[str]]] = {}
    _memo_prod: dict[
        tuple[str, str | None],
        tuple[int | None, str | None, list[str], str | None, ProductResolutionEvidence | None],
    ] = {}
    _memo_cust: dict[
        tuple[Any, ...],
        tuple[int | None, list[str], dict[str, Any] | None, list[str]],
    ] = {}

    if profile.enabled:
        profile.start_chunk(1)

    for i in range(total_rows):
        row_t0 = time.monotonic() if profile.enabled else 0.0
        rn = i + 1
        if rn == 1 or rn % 10000 == 0:
            logger.info(
                "process_distributor_sales_inventory: job_id=%s processing row %d / %d",
                job.id,
                rn,
                total_rows,
            )
        _now = time.monotonic()
        if on_progress is not None and _now >= _progress_next:
            on_progress("processing_rows", "Processing rows", rn, total_rows)
            _progress_next = _now + _PROGRESS_INTERVAL
        raw_payload = _raw_payload_at_index(df, i)
        mapped = _build_mapped_canonical_at_index(df, i, mapping, ignored_src_cols, col_index)
        verify_json_serializable("raw_row_payload", raw_payload)
        verify_json_serializable("mapped_canonical", mapped)

        dist_raw = _cell_str(df, i, _c_dist, col_index)
        prod_raw = _cell_str(df, i, _c_prod, col_index)
        cust_raw = _cell_str(df, i, _c_cust, col_index)
        dg_raw = _cell_str(df, i, _c_dg, col_index)
        ch_raw = _cell_str(df, i, _c_channel, col_index)
        reg_raw = _cell_str(df, i, _c_region, col_index)
        open_raw = _cell_raw(df, i, _c_open, col_index)

        tx_date = _parse_date(_cell_raw(df, i, _c_tx, col_index)) if _c_tx else None
        snap_date = _parse_date(_cell_raw(df, i, _c_snap, col_index)) if _c_snap else None
        if tx_date is None and snap_date is not None:
            tx_date = snap_date
        if snap_date is None and tx_date is not None:
            snap_date = tx_date

        qty_sold = _parse_decimal(_cell_raw(df, i, _c_qty, col_index)) if _c_qty else None
        soh = _parse_decimal(_cell_raw(df, i, _c_soh, col_index)) if _c_soh else None
        unit_price = (
            _parse_decimal(_cell_raw(df, i, _c_price, col_index))
            if _c_price
            else None
        )
        reported_rev = (
            _parse_decimal(_cell_raw(df, i, _c_rev, col_index))
            if _c_rev
            else None
        )
        cur = _cell_str(df, i, _c_cur, col_index)
        inv_raw = _cell_str(df, i, _c_inv, col_index)
        invoice_no_val = normalize_dsi_invoice_no(inv_raw)

        computed_rev: Decimal | None = None
        if qty_sold is not None and unit_price is not None:
            computed_rev = qty_sold * unit_price

        diag: list[str] = []
        customer_auto_conflict: dict[str, Any] | None = None

        dist_memo_key = _norm_key(dist_raw) if dist_raw else ""
        evidence_date = tx_date or snap_date
        ev_month_key = evidence_date.isoformat() if evidence_date else None

        if dist_memo_key and dist_memo_key in _memo_dist:
            rdid, derr, dist_diag = _memo_dist[dist_memo_key]
            diag.extend(dist_diag)
        else:
            rdid, derr = _resolve_distributor_from_cache(dist_raw, source_def_id, res_cache)
            dist_diag: list[str] = []
            if derr:
                dist_diag.append(derr)
                diag.append(derr)
            if rdid is None and dist_raw:
                from app.services.imports.dsi_weekly_auto_resolution import (
                    check_distributor_auto_resolution_at_validate,
                )

                dist_auto = check_distributor_auto_resolution_at_validate(
                    db,
                    job=job,
                    source_definition_id=source_def_id,
                    normalized_key=_norm_key(dist_raw),
                    resolved_distributor_id=rdid,
                )
                if dist_auto.outcome == "resolved" and dist_auto.entity_id is not None:
                    rdid = int(dist_auto.entity_id)
                    dist_diag.append("distributor_resolved_weekly_auto")
                    diag.append("distributor_resolved_weekly_auto")

            if rdid is None and dist_raw:
                from app.services.imports.ai_resolver_wiring import (
                    append_ai_diagnostic,
                    distributor_candidates_from_cache,
                    try_ai_token_resolution,
                )

                ai_id, ai_tag, ai_suggestion = try_ai_token_resolution(
                    raw_token=dist_raw,
                    token_type="distributor",
                    candidates=distributor_candidates_from_cache(res_cache, dist_raw),
                    import_type="distributor_sales_inventory",
                    job_id=int(job.id),
                )
                if ai_id is not None:
                    rdid = ai_id
                    dist_diag.append("distributor_ai_auto_resolved")
                    diag.append("distributor_ai_auto_resolved")
                elif ai_suggestion is not None and ai_tag == "ai_suggested":
                    diag = append_ai_diagnostic(diag, token_type="distributor", suggestion=ai_suggestion)

            if dist_memo_key:
                _memo_dist[dist_memo_key] = (rdid, derr, list(dist_diag))

        prod_memo_key = (_norm_key(prod_raw) if prod_raw else "", ev_month_key)
        pev: ProductResolutionEvidence | None = None
        presolve_tag: str | None = None
        perr: str | None = None
        if prod_memo_key[0] and prod_memo_key in _memo_prod:
            rpid, perr, prod_diag, presolve_tag, pev = _memo_prod[prod_memo_key]
            diag.extend(prod_diag)
        else:
            rpid, perr, presolve_tag, pev = _resolve_product(
                prod_raw,
                prod_idx,
                evidence_date,
                relax_inactive_dim_product_for_historical_dsi=historical_relaxed,
                db=db,
                distributor_id=rdid,
                corr_cache=corr_cache,
            )
            prod_diag: list[str] = []
            if perr:
                prod_diag.append(perr)
                diag.append(perr)
            elif presolve_tag:
                prod_diag.append(presolve_tag)
                diag.append(presolve_tag)
            if rpid is None and prod_raw:
                from app.services.imports.dsi_weekly_auto_resolution import (
                    check_product_auto_resolution_at_validate,
                )

                prod_auto = check_product_auto_resolution_at_validate(
                    db,
                    job=job,
                    source_definition_id=source_def_id,
                    distributor_id=rdid,
                    normalized_key=_norm_key(prod_raw),
                )
                if prod_auto.outcome == "resolved" and prod_auto.entity_id is not None:
                    rpid = int(prod_auto.entity_id)
                    prod_diag.append("product_resolved_weekly_auto")
                    diag.append("product_resolved_weekly_auto")
                elif prod_auto.outcome == "conflict":
                    pev = pev or {}
                    pev["weekly_auto_conflict"] = True
                    pev["prior_resolution_conflict"] = prod_auto.conflict_prior

            if rpid is None and prod_raw:
                from app.services.imports.ai_resolver_wiring import (
                    append_ai_diagnostic,
                    product_candidates_from_index,
                    try_ai_token_resolution,
                )

                ai_id, ai_tag, ai_suggestion = try_ai_token_resolution(
                    raw_token=prod_raw,
                    token_type="product",
                    candidates=product_candidates_from_index(prod_idx, prod_raw),
                    import_type="distributor_sales_inventory",
                    job_id=int(job.id),
                )
                if ai_id is not None:
                    rpid = ai_id
                    prod_diag.append("product_ai_auto_resolved")
                    diag.append("product_ai_auto_resolved")
                elif ai_suggestion is not None and ai_tag == "ai_suggested":
                    diag = append_ai_diagnostic(diag, token_type="product", suggestion=ai_suggestion)

            if prod_memo_key[0]:
                _memo_prod[prod_memo_key] = (rpid, perr, list(prod_diag), presolve_tag, pev)

        rdistributor_id = rdid
        rcustomer_id: int | None = None

        qty_f = float(qty_sold) if qty_sold is not None else None
        sellout_attempt = qty_f is not None and tx_date is not None and qty_f > 0
        return_attempt = qty_f is not None and tx_date is not None and qty_f < 0
        sellout_or_return_attempt = sellout_attempt or return_attempt
        inv_attempt = soh is not None

        cust_res_raw: str | None = None
        cust_res_notes: list[str] = []
        if sellout_or_return_attempt:
            cust_res_raw, cust_res_notes = effective_dsi_customer_primary_for_resolution(cust_raw, dg_raw)

        if sellout_or_return_attempt:
            cust_memo_key = (
                rdistributor_id,
                _norm_key(cust_res_raw or ""),
                _norm_key(dg_raw or ""),
                _norm_key(ch_raw or ""),
                str(open_raw),
            )
            if cust_memo_key in _memo_cust:
                rcustomer_id, cust_diag, customer_auto_conflict, cust_res_notes = _memo_cust[cust_memo_key]
                diag.extend(cust_diag)
                diag.extend(cust_res_notes)
            else:
                rcustomer_id, cd = _resolve_customer_from_cache(
                    source_id=source_def_id,
                    distributor_id=rdistributor_id,
                    customer_raw=cust_res_raw,
                    dealer_group_raw=dg_raw,
                    channel_raw=ch_raw,
                    open_flag_raw=open_raw,
                    res_cache=res_cache,
                )
                cust_diag = list(cd)
                diag.extend(cust_diag)
                if rcustomer_id is None:
                    from app.services.imports.dsi_weekly_auto_resolution import (
                        check_customer_auto_resolution_at_validate,
                    )

                    ckey_probe = _customer_candidate_identity_norm(cust_raw, dg_raw)
                    cust_auto = check_customer_auto_resolution_at_validate(
                        db,
                        job=job,
                        source_definition_id=source_def_id,
                        distributor_id=rdistributor_id,
                        normalized_key=ckey_probe,
                        customer_raw=cust_res_raw,
                        dealer_group_raw=dg_raw,
                        historical_index=weekly_historical_customers or None,
                    )
                    if cust_auto.outcome == "resolved" and cust_auto.entity_id is not None:
                        rcustomer_id = int(cust_auto.entity_id)
                        cust_diag.append("customer_resolved_weekly_auto")
                        diag.append("customer_resolved_weekly_auto")
                    elif cust_auto.outcome == "conflict":
                        customer_auto_conflict = {
                            "conflict_flag": True,
                            "prior_resolution_conflict": cust_auto.conflict_prior,
                        }
                if rcustomer_id is None and cust_res_raw:
                    from app.services.imports.ai_resolver_wiring import (
                        append_ai_diagnostic,
                        customer_candidates_from_cache,
                        try_ai_token_resolution,
                    )

                    ai_id, ai_tag, ai_suggestion = try_ai_token_resolution(
                        raw_token=cust_res_raw,
                        token_type="customer",
                        candidates=customer_candidates_from_cache(res_cache, cust_res_raw),
                        import_type="distributor_sales_inventory",
                        job_id=int(job.id),
                    )
                    if ai_id is not None:
                        rcustomer_id = ai_id
                        cust_diag.append("customer_ai_auto_resolved")
                        diag.append("customer_ai_auto_resolved")
                    elif ai_suggestion is not None and ai_tag == "ai_suggested":
                        diag = append_ai_diagnostic(diag, token_type="customer", suggestion=ai_suggestion)
                diag.extend(cust_res_notes)
                _memo_cust[cust_memo_key] = (
                    rcustomer_id,
                    list(cust_diag),
                    customer_auto_conflict,
                    list(cust_res_notes),
                )

        hard_row = bool((derr and rdid is None) or (perr and rpid is None))
        sellout_blocked_no_customer = bool(sellout_or_return_attempt and rcustomer_id is None)
        sellout_blocked_no_tx = bool(
            qty_f is not None and qty_f != 0 and tx_date is None
        )
        inv_ready = bool(inv_attempt and snap_date is not None and soh is not None)
        inv_soft_fail = bool(inv_attempt and not inv_ready)
        sellout_ready = bool(
            sellout_attempt
            and tx_date is not None
            and rcustomer_id is not None
            and qty_sold is not None
        )

        if sellout_blocked_no_customer or sellout_blocked_no_tx:
            dsi_sellout_issue_rows += 1
        if (
            not hard_row
            and inv_ready
            and (sellout_blocked_no_customer or sellout_blocked_no_tx)
        ):
            dsi_inv_ready_with_sellout_issue_rows += 1

        sev: str = "info"
        if hard_row:
            sev = "error"
        elif (sellout_blocked_no_customer or sellout_blocked_no_tx) and inv_ready:
            sev = "warning"
            if sellout_blocked_no_customer:
                diag.append("sellout_blocked_missing_customer")
            if sellout_blocked_no_tx:
                diag.append("sellout_blocked_missing_transaction_date")
        elif inv_soft_fail and sellout_ready:
            sev = "warning"
            if snap_date is None:
                diag.append("inventory_blocked_missing_snapshot_date")
            if soh is None:
                diag.append("inventory_blocked_missing_stock_on_hand")
        elif sellout_blocked_no_customer or sellout_blocked_no_tx or inv_soft_fail:
            sev = "error"
            if sellout_blocked_no_customer:
                diag.append("sellout_blocked_missing_customer")
            if sellout_blocked_no_tx:
                diag.append("sellout_blocked_missing_transaction_date")
            if inv_soft_fail:
                if snap_date is None:
                    diag.append("inventory_blocked_missing_snapshot_date")
                if soh is None:
                    diag.append("inventory_blocked_missing_stock_on_hand")

        mismatch = False
        if reported_rev is not None and computed_rev is not None:
            if abs(reported_rev - computed_rev) > Decimal("0.01") * max(Decimal(1), abs(reported_rev)):
                mismatch = True
                diag.append("reported_vs_computed_revenue_mismatch")
                if sev != "error":
                    sev = "warning"

        if qty_sold is not None and qty_sold < 0:
            diag.append("return_or_credit_suspected_qty")
            if sev == "info":
                sev = "warning"
        if reported_rev is not None and reported_rev < 0:
            diag.append("return_or_credit_suspected_revenue")
            if sev == "info":
                sev = "warning"

        can_sellout = (
            not hard_row
            and bool(rdistributor_id)
            and bool(rpid)
            and tx_date is not None
            and qty_f is not None
            and qty_f > 0
            and bool(rcustomer_id)
        )
        can_return = (
            not hard_row
            and bool(rdistributor_id)
            and bool(rpid)
            and tx_date is not None
            and qty_f is not None
            and qty_f < 0
            and bool(rcustomer_id)
        )
        can_inv = (
            not hard_row
            and bool(rdistributor_id)
            and bool(rpid)
            and snap_date is not None
            and soh is not None
        )
        if sev == "error":
            res_status = "blocked"
        elif (can_sellout or can_return) and can_inv:
            res_status = "ready_both"
        elif can_sellout or can_return:
            res_status = "ready_sellout"
        elif can_inv:
            res_status = "ready_inventory"
        else:
            res_status = "staged_only"

        _append_shipment_corroboration_signals_dsi(
            db,
            diag,
            rdistributor_id=rdistributor_id,
            evidence_date=evidence_date,
            prod_raw=prod_raw,
            rpid=rpid,
            cust_raw=cust_raw,
            dg_raw=dg_raw,
            rcustomer_id=rcustomer_id,
            cache=corr_cache,
        )

        staging_buffer.append(
            _staging_line_row_dict(
                job_id=int(job.id),
                source_row_number=rn,
                raw_payload=raw_payload,
                mapped=mapped,
                dist_raw=dist_raw,
                cust_raw=cust_raw,
                dg_raw=dg_raw,
                prod_raw=prod_raw,
                rdistributor_id=rdistributor_id,
                rcustomer_id=rcustomer_id,
                rpid=rpid,
                tx_date=tx_date,
                invoice_no_val=invoice_no_val,
                snap_date=snap_date,
                qty_sold=qty_sold,
                soh=soh,
                unit_price=unit_price,
                reported_rev=reported_rev,
                computed_rev=computed_rev,
                cur=cur,
                res_status=res_status,
                diag=diag,
                sev=sev,
            )
        )

        if sev == "error":
            blocking += 1
        elif sev == "warning":
            warnings += 1

        if rdistributor_id is None and dist_raw:
            k = ("distributor_token", _norm_key(dist_raw))
            a = agg[k]
            a["row_count"] += 1
            if len(a["samples"]) < 5:
                a["samples"].append(dist_raw)
        if rpid is None and prod_raw:
            k = ("product_identifier", _norm_key(prod_raw))
            a = agg[k]
            _merge_product_resolution_evidence(a, pev)
            if rdistributor_id is not None:
                ds = a.setdefault("_dist_ids_unresolved", set())
                if not isinstance(ds, set):
                    ds = set()
                    a["_dist_ids_unresolved"] = ds
                ds.add(int(rdistributor_id))
            a["row_count"] += 1
            if qty_sold is not None:
                a["total_units"] += abs(qty_sold)
            if reported_rev is not None:
                a["total_value"] += abs(reported_rev)
            if len(a["samples"]) < 5:
                a["samples"].append(prod_raw)
            if isinstance(pev, dict) and pev.get("weekly_auto_conflict"):
                a["conflict_flag"] = True
                a["prior_resolution_conflict"] = pev.get("prior_resolution_conflict")
            if rdistributor_id and evidence_date:
                cp = corr_cache.product_corroboration(
                    int(rdistributor_id),
                    evidence_date,
                    raw_product_token=prod_raw,
                    resolved_product_id=None,
                )
                if cp:
                    a["shipment_corr_hit"] = True
                    a["shipment_corr_best"] = max(int(a.get("shipment_corr_best") or 0), int(cp.get("match_count") or 0))
                    dps = cp.get("distinct_resolved_product_ids")
                    if isinstance(dps, list):
                        sid_set = a.setdefault("shipment_distinct_product_ids", set())
                        if not isinstance(sid_set, set):
                            sid_set = set()
                            a["shipment_distinct_product_ids"] = sid_set
                        for x in dps:
                            try:
                                sid_set.add(int(x))
                            except (TypeError, ValueError):
                                pass
                    em = evidence_date.strftime("%Y-%m")
                    mc = a.setdefault("shipment_evidence_month_counts", {})
                    if isinstance(mc, dict):
                        mc[em] = int(mc.get(em) or 0) + 1
        if sellout_or_return_attempt and rcustomer_id is None:
            ckey = _customer_candidate_identity_norm(cust_raw, dg_raw)
            k = ("customer_dealer_token", ckey)
            a = agg[k]
            if customer_auto_conflict:
                a["conflict_flag"] = True
                a["prior_resolution_conflict"] = customer_auto_conflict.get("prior_resolution_conflict")
            if a.get("primary_source") is None:
                if not _dealer_group_is_placeholder(dg_raw):
                    a["primary_source"] = "dealer_name_group"
                elif not _customer_token_is_placeholder(_norm_key(cust_raw), cust_raw):
                    a["primary_source"] = "customer_column"
                else:
                    a["primary_source"] = "blank"
            a["row_count"] += 1
            if qty_sold is not None:
                a["total_units"] += abs(qty_sold)
            if reported_rev is not None:
                a["total_value"] += abs(reported_rev)
            if cust_raw and not _customer_token_is_placeholder(_norm_key(cust_raw), cust_raw):
                cu_ev = normalize_customer_name_token(cust_raw)
                if cu_ev:
                    lst = a["customer_evidence_norms"]
                    if cu_ev not in lst and len(lst) < 8:
                        lst.append(cu_ev)
                    src_lst = a["source_customer_evidence_norms"]
                    if cu_ev not in src_lst and len(src_lst) < 8:
                        src_lst.append(cu_ev)
            if rdistributor_id is not None:
                dist_set = a.setdefault("sellout_distributor_ids", set())
                if isinstance(dist_set, set):
                    dist_set.add(int(rdistributor_id))
            if dg_raw and not _dealer_group_is_placeholder(dg_raw):
                if a.get("dealer_group_raw") is None:
                    a["dealer_group_raw"] = dg_raw.strip()[:512]
                dg_norm = normalize_customer_name_token(dg_raw)
                if dg_norm:
                    lst_dg = a["customer_evidence_norms"]
                    if dg_norm not in lst_dg and len(lst_dg) < 8:
                        lst_dg.append(dg_norm)
            if cust_raw and not _customer_token_is_placeholder(_norm_key(cust_raw), cust_raw):
                scs: list[str] = a["source_customer_raw_samples"]
                t = cust_raw.strip()[:512]
                if t and t not in scs and len(scs) < 8:
                    scs.append(t)
            if len(a["samples"]) < 5:
                parts: list[str] = []
                if cust_raw and not _customer_token_is_placeholder(_norm_key(cust_raw), cust_raw):
                    parts.append(f"customer={cust_raw.strip()[:160]}")
                if dg_raw and not _dealer_group_is_placeholder(dg_raw):
                    parts.append(f"dealer_group={dg_raw.strip()[:160]}")
                elif dg_raw:
                    parts.append(f"dealer_group(raw)={dg_raw.strip()[:80]}")
                sample = " | ".join(parts) if parts else (cust_raw or dg_raw or "").strip()[:200]
                if sample:
                    a["samples"].append(sample)
            if rdistributor_id and evidence_date:
                cc = corr_cache.customer_corroboration(
                    int(rdistributor_id),
                    evidence_date,
                    customer_primary_raw=cust_raw,
                    dealer_group_raw=dg_raw,
                    resolved_customer_id=None,
                )
                if cc:
                    a["shipment_cust_corr_hit"] = True
                    a["shipment_cust_corr_best"] = max(
                        int(a.get("shipment_cust_corr_best") or 0), int(cc.get("match_count") or 0)
                    )
            chv = (ch_raw or "").strip().lower()
            if chv and any(h in chv for h in STRATEGIC_CHANNEL_HINT_SUBSTRINGS):
                a["strategic_channel_hint"] = True

            if reg_raw:
                rn = _norm_key(reg_raw)
                if _region_channel_evidence_norm_usable(rn, reg_raw):
                    norms_r: list[str] = a["region_evidence_norms"]
                    if rn not in norms_r and len(norms_r) < 8:
                        norms_r.append(rn)
                    if len(set(norms_r)) > 1:
                        a["provisional_region_conflict"] = True
                    srs: list[str] = a["source_region_raw_samples"]
                    treg = reg_raw.strip()[:512]
                    if treg and treg not in srs and len(srs) < 8:
                        srs.append(treg)
            if ch_raw:
                cn = _norm_key(ch_raw)
                if _region_channel_evidence_norm_usable(cn, ch_raw):
                    norms_c: list[str] = a["channel_evidence_norms"]
                    if cn not in norms_c and len(norms_c) < 8:
                        norms_c.append(cn)
                    if len(set(norms_c)) > 1:
                        a["provisional_channel_conflict"] = True
                    sch: list[str] = a["source_channel_raw_samples"]
                    tch = ch_raw.strip()[:512]
                    if tch and tch not in sch and len(sch) < 8:
                        sch.append(tch)

        _maybe_flush_staging(rn)
        if profile.enabled:
            elapsed = time.monotonic() - row_t0
            profile.row_loop_s += elapsed
            profile.chunk_row_loop_s += elapsed

    if profile.enabled:
        profile.finish_chunk(total_rows)
    _maybe_flush_staging(total_rows, force_commit=True)

    if profile.enabled:
        profile.log_summary(total_rows=total_rows, total_s=time.monotonic() - process_t0)

    if on_progress is not None:
        on_progress("building_candidates", "Building candidates", total_rows, total_rows)

    from sqlalchemy.orm.attributes import flag_modified

    meta_phase = dict(job.staged_metadata or {})
    meta_phase["dsi_validate_phase"] = "building_candidates"
    job.staged_metadata = to_jsonable(meta_phase)
    flag_modified(job, "staged_metadata")
    db.add(job)
    db.flush()

    annotate_dsi_customer_candidate_duplicates(agg, distributors=res_cache.all_distributors)
    annotate_dsi_customer_distributor_name_collisions(agg, res_cache.all_distributors)

    for (etype, nkey), data in agg.items():
        ctx: dict[str, Any] = {"aggregated": True}
        dealer_token_col: str | None = None
        nkey_clean = nkey
        if etype == "customer_dealer_token":
            ps = data.get("primary_source")
            if ps:
                ctx["primary_source"] = ps
            evs = data.get("customer_evidence_norms") or []
            if evs:
                ctx["customer_name_evidence_norms"] = evs[:8]
            src_evs = data.get("source_customer_evidence_norms") or []
            if src_evs:
                ctx["source_customer_name_evidence_norms"] = src_evs[:8]
            dup_hints = data.get("possible_duplicate_of")
            if isinstance(dup_hints, list) and dup_hints:
                ctx["possible_duplicate_of"] = dup_hints[:16]
            dist_collision = data.get("distributor_master_collision")
            if isinstance(dist_collision, dict) and dist_collision.get("distributor_id"):
                ctx["distributor_master_collision"] = {
                    "distributor_id": int(dist_collision["distributor_id"]),
                    "distributor_name": str(dist_collision.get("distributor_name") or "")[:256],
                }
            dist_ids = data.get("sellout_distributor_ids")
            if isinstance(dist_ids, set) and len(dist_ids) == 1:
                ctx["dominant_distributor_id"] = int(next(iter(dist_ids)))
            elif isinstance(dist_ids, set) and len(dist_ids) > 1:
                ctx["sellout_distributor_ids"] = sorted(int(x) for x in dist_ids)[:8]
            dgr_store = data.get("dealer_group_raw")
            if isinstance(dgr_store, str) and dgr_store.strip():
                ctx["dealer_group_account_raw"] = dgr_store.strip()[:512]
            src_raw = data.get("source_customer_raw_samples") or []
            if src_raw:
                ctx["source_customer_name_raw_samples"] = src_raw[:8]
            reg_samples = data.get("source_region_raw_samples") or []
            if reg_samples:
                ctx["source_region_raw_samples"] = reg_samples[:8]
            ch_samples_ctx = data.get("source_channel_raw_samples") or []
            if ch_samples_ctx:
                ctx["source_channel_raw_samples"] = ch_samples_ctx[:8]
            ren = data.get("region_evidence_norms") or []
            if ren:
                ctx["source_region_evidence_norms"] = ren[:8]
            cen = data.get("channel_evidence_norms") or []
            if cen:
                ctx["source_channel_evidence_norms"] = cen[:8]
            if data.get("provisional_region_conflict"):
                ctx["provisional_region_conflict"] = True
            if data.get("provisional_channel_conflict"):
                ctx["provisional_channel_conflict"] = True
            if data.get("conflict_flag"):
                ctx["conflict_flag"] = True
                if data.get("prior_resolution_conflict") is not None:
                    ctx["prior_resolution_conflict"] = data.get("prior_resolution_conflict")
            if ps == "dealer_name_group":
                if isinstance(dgr_store, str) and dgr_store.strip():
                    dealer_token_col = dgr_store.strip()[:512]
                elif nkey_clean and nkey_clean != "__blank__":
                    dealer_token_col = nkey_clean[:512]
        if etype == "product_identifier":
            if data.get("conflict_flag"):
                ctx["conflict_flag"] = True
                if data.get("prior_resolution_conflict") is not None:
                    ctx["prior_resolution_conflict"] = data.get("prior_resolution_conflict")
            dist_unresolved = data.pop("_dist_ids_unresolved", None)
            if isinstance(dist_unresolved, set) and len(dist_unresolved) == 1:
                ctx["dominant_unresolved_distributor_id"] = int(next(iter(dist_unresolved)))
            ship_ids = data.pop("shipment_distinct_product_ids", None)
            if isinstance(ship_ids, set) and ship_ids:
                ctx["shipment_distinct_product_ids"] = sorted(int(x) for x in ship_ids if int(x) > 0)[:32]
            month_counts = data.pop("shipment_evidence_month_counts", None)
            if isinstance(month_counts, dict) and month_counts:
                dom_month = max(month_counts.items(), key=lambda kv: int(kv[1] or 0))[0]
                if isinstance(dom_month, str) and dom_month.strip():
                    ctx["dominant_evidence_month"] = dom_month.strip()[:7]
            acc = data.pop("_pe_acc", None)
            if isinstance(acc, dict):
                amb = acc.get("amb")
                inh = [x for x in (acc.get("inh") or []) if isinstance(x, dict)]
                if amb:
                    ctx["product_match_status"] = "ambiguous_eligible"
                    ctx["product_ambiguous_eligible"] = amb
                    ids = amb.get("product_ids") or []
                    tier = amb.get("tier") or ""
                    ctx["product_match_summary"] = (
                        f"Ambiguous: {len(ids)} eligible Product Master rows in tier "
                        f"{tier}; auto-resolve blocked."
                    )
                elif inh:
                    ctx["product_match_status"] = "inactive_only"
                    ctx["product_inactive_matches"] = inh[:16]
                    ctx["product_match_summary"] = (
                        f"{len(inh)} inactive/ineligible Product Master row(s) matched this token "
                        f"(see lifecycle fields below)."
                    )
                else:
                    ctx["product_match_status"] = "no_match"
                    ctx["product_match_summary"] = (
                        "No Product Master or approved-alias match for this token."
                    )
            else:
                ctx["product_match_status"] = "no_match"
                ctx["product_match_summary"] = (
                    "No Product Master or approved-alias match for this token."
                )
        if data.get("strategic_channel_hint"):
            ctx["strategic_channel_hint"] = True
        if etype == "product_identifier" and data.get("shipment_corr_hit"):
            ctx["shipment_evidence_corroboration"] = {
                "best_match_count": int(data.get("shipment_corr_best") or 0),
                "signal_only": True,
                "summary": "Resolved shipment evidence lines in the same calendar month may corroborate this token (no auto-resolve).",
            }
            ctx.setdefault("corroboration_markers", []).append("shipment_evidence_product")
        if etype == "customer_dealer_token" and data.get("shipment_cust_corr_hit"):
            ctx["shipment_evidence_corroboration"] = {
                "best_match_count": int(data.get("shipment_cust_corr_best") or 0),
                "signal_only": True,
                "summary": "Resolved shipment evidence lines in the same calendar month may corroborate this bucket (no auto-resolve).",
            }
            ctx.setdefault("corroboration_markers", []).append("shipment_evidence_customer")
        cand_status = "needs_review"
        pres = preserved_candidate_steward.get((etype, nkey_clean[:512]))
        if pres:
            if isinstance(pres.get("duplicate_review"), dict):
                ctx["duplicate_review"] = pres["duplicate_review"]
            if pres.get("status") == "acknowledged_unique":
                cand_status = "acknowledged_unique"
        cand = ImportEntityMappingCandidate(
            import_job_id=job.id,
            source_definition_id=source_def_id,
            entity_type=etype,
            normalized_key=nkey_clean[:512],
            dealer_group_token=dealer_token_col if etype == "customer_dealer_token" else None,
            row_count=int(data["row_count"]),
            total_units=float(data["total_units"]) if data["total_units"] else None,
            total_reported_value=float(data["total_value"]) if data["total_value"] else None,
            sample_raw_values=to_jsonable(data["samples"][:5]),
            status=cand_status,
            context=to_jsonable(ctx),
        )
        db.add(cand)

    logger.info(
        "process_distributor_sales_inventory: job_id=%s row loop complete — "
        "blocking=%d warnings=%d candidates=%d",
        job.id,
        blocking,
        warnings,
        len(agg),
    )

    if first_unresolved_dist_raw:
        db.add(
            ImportRowResult(
                job_id=job.id,
                row_number=0,
                severity="error",
                code="unresolved_distributor_token",
                message=(
                    f"Distributor token '{first_unresolved_dist_raw}' could not be matched to an existing distributor."
                ),
            )
        )

    eff_rev_note = ""
    if job.import_mode == "apply":
        db.flush()
        applied_sell, applied_inv, applied_ret, apply_errors = upsert_dsi_facts_for_staging_job(db, job)
        if apply_errors:
            db.add(
                ImportRowResult(
                    job_id=job.id,
                    row_number=0,
                    severity="error",
                    code="distributor_si_fact_apply_errors",
                    message=json.dumps(apply_errors)[:4000],
                )
            )
        eff_rev_note = (
            f" Applied sell-out facts={applied_sell}, return facts={applied_ret}, "
            f"inventory facts={applied_inv} (upsert by source_key)."
        )

    summary = {
        "staging_rows": int(len(df)),
        "blocking_rows": blocking,
        "warning_rows": warnings,
        "aggregated_candidates": len(agg),
        "import_mode": job.import_mode,
        "sellout_issue_rows": dsi_sellout_issue_rows,
        "rows_inventory_ready_with_sellout_warnings": dsi_inv_ready_with_sellout_issue_rows,
        "historical_product_eligibility_relaxed": historical_relaxed,
    }
    db.add(
        ImportRowResult(
            job_id=job.id,
            row_number=0,
            severity="info" if blocking == 0 else "warning",
            code="distributor_si_summary",
            message=json.dumps(summary) + eff_rev_note,
        )
    )
    # Re-persist after row loop so JSONB metadata survives pipeline commit/clear.
    intel_state = check_dsi_import_state(db, job.id, primary_dist_id)
    persist_intelligence_state_on_job(db, job, intel_state)
    return 1 if blocking else 0


SHIP_CORR_JSON_PREFIX = "shipment_corroboration_json:"


def _append_shipment_corroboration_signals_dsi(
    db: Session,
    diag: list[str],
    *,
    rdistributor_id: int | None,
    evidence_date: date | None,
    prod_raw: str | None,
    rpid: int | None,
    cust_raw: str | None,
    dg_raw: str | None,
    rcustomer_id: int | None,
    cache: Any = None,
) -> None:
    """Append shipment-evidence corroboration JSON tokens to ``diag``.

    When ``cache`` (a ``ShipmentCorroborationCache``) is provided, uses in-memory
    lookups instead of per-row DB queries.  The cache is preferred for bulk
    validation; per-row DB queries are used for single-row steward refresh.
    """
    if not rdistributor_id or not evidence_date:
        return
    if cache is not None:
        pc = cache.product_corroboration(
            int(rdistributor_id),
            evidence_date,
            raw_product_token=prod_raw,
            resolved_product_id=rpid,
        )
        cc = cache.customer_corroboration(
            int(rdistributor_id),
            evidence_date,
            customer_primary_raw=cust_raw,
            dealer_group_raw=dg_raw,
            resolved_customer_id=rcustomer_id,
        )
    else:
        pc = shipment_corroboration_for_product(
            db,
            distributor_id=int(rdistributor_id),
            evidence_date=evidence_date,
            raw_product_token=prod_raw,
            resolved_product_id=rpid,
        )
        cc = shipment_corroboration_for_customer(
            db,
            distributor_id=int(rdistributor_id),
            evidence_date=evidence_date,
            customer_primary_raw=cust_raw,
            dealer_group_raw=dg_raw,
            resolved_customer_id=rcustomer_id,
        )
    if pc:
        diag.append(SHIP_CORR_JSON_PREFIX + json.dumps(to_jsonable(pc))[:900])
    if cc:
        diag.append(SHIP_CORR_JSON_PREFIX + json.dumps(to_jsonable(cc))[:900])


def refresh_dsi_staging_line_resolution(
    db: Session,
    job: ImportJob,
    line: ImportDistributorSiStagingLine,
    prod_idx: ProductResolutionIndex,
) -> None:
    """Recompute resolution fields from persisted staging row (canonical JSON + raw tokens)."""
    source = job.source
    source_def_id = source.id if source else None
    historical_relaxed = dsi_historical_product_eligibility_relaxed_from_import_job(job)
    mapped = line.mapped_canonical if isinstance(line.mapped_canonical, dict) else {}
    dist_raw = line.raw_distributor_token
    prod_raw = line.raw_product_token
    cust_raw = line.raw_customer_dealer_token
    dg_raw = line.raw_dealer_group_token
    ch_raw = _channel_raw_from_mapped(mapped)
    reg_raw = _region_raw_from_mapped(mapped)
    open_raw = mapped.get("open_channel_evidence")

    tx_date = line.transaction_date
    snap_date = line.snapshot_date
    if tx_date is None and snap_date is not None:
        tx_date = snap_date
    if snap_date is None and tx_date is not None:
        snap_date = tx_date

    qty_sold = Decimal(str(line.quantity_sold)) if line.quantity_sold is not None else None
    soh = Decimal(str(line.stock_on_hand)) if line.stock_on_hand is not None else None
    unit_price = (
        Decimal(str(line.unit_sellout_price_ex_tax_amount))
        if line.unit_sellout_price_ex_tax_amount is not None
        else None
    )
    reported_rev = (
        Decimal(str(line.reported_revenue_amount)) if line.reported_revenue_amount is not None else None
    )
    cur = line.currency_code

    computed_rev: Decimal | None = None
    if qty_sold is not None and unit_price is not None:
        computed_rev = qty_sold * unit_price

    diag: list[str] = []

    rdid, derr = _resolve_distributor(db, dist_raw, source_def_id)
    if derr:
        diag.append(derr)

    evidence_date = tx_date or snap_date
    rpid, perr, presolve_tag, pev = _resolve_product(
        prod_raw,
        prod_idx,
        evidence_date,
        relax_inactive_dim_product_for_historical_dsi=historical_relaxed,
        db=db,
        distributor_id=rdid,
    )
    if perr:
        diag.append(perr)
    elif presolve_tag:
        diag.append(presolve_tag)

    rdistributor_id = rdid
    rcustomer_id: int | None = None

    sellout_attempt = bool(qty_sold is not None and tx_date is not None and qty_sold != 0)
    inv_attempt = soh is not None

    cust_res_raw: str | None = None
    cust_res_notes: list[str] = []
    if sellout_attempt:
        cust_res_raw, cust_res_notes = effective_dsi_customer_primary_for_resolution(cust_raw, dg_raw)

    if sellout_attempt:
        rcustomer_id, cd = _resolve_customer(
            db,
            source_id=source_def_id,
            distributor_id=rdistributor_id,
            customer_raw=cust_res_raw,
            dealer_group_raw=dg_raw,
            channel_raw=ch_raw,
            open_flag_raw=open_raw,
        )
        diag.extend(cd)
        diag.extend(cust_res_notes)

    hard_row = bool(derr or perr)
    sellout_blocked_no_customer = bool(sellout_attempt and rcustomer_id is None)
    sellout_blocked_no_tx = bool(qty_sold is not None and qty_sold != 0 and tx_date is None)
    inv_ready = bool(inv_attempt and snap_date is not None and soh is not None)
    inv_soft_fail = bool(inv_attempt and not inv_ready)
    sellout_ready = bool(
        sellout_attempt and tx_date is not None and rcustomer_id is not None and qty_sold is not None
    )

    sev: str = "info"
    if hard_row:
        sev = "error"
    elif (sellout_blocked_no_customer or sellout_blocked_no_tx) and inv_ready:
        sev = "warning"
        if sellout_blocked_no_customer:
            diag.append("sellout_blocked_missing_customer")
        if sellout_blocked_no_tx:
            diag.append("sellout_blocked_missing_transaction_date")
    elif inv_soft_fail and sellout_ready:
        sev = "warning"
        if snap_date is None:
            diag.append("inventory_blocked_missing_snapshot_date")
        if soh is None:
            diag.append("inventory_blocked_missing_stock_on_hand")
    elif sellout_blocked_no_customer or sellout_blocked_no_tx or inv_soft_fail:
        sev = "error"
        if sellout_blocked_no_customer:
            diag.append("sellout_blocked_missing_customer")
        if sellout_blocked_no_tx:
            diag.append("sellout_blocked_missing_transaction_date")
        if inv_soft_fail:
            if snap_date is None:
                diag.append("inventory_blocked_missing_snapshot_date")
            if soh is None:
                diag.append("inventory_blocked_missing_stock_on_hand")

    if reported_rev is not None and computed_rev is not None:
        if abs(reported_rev - computed_rev) > Decimal("0.01") * max(Decimal(1), abs(reported_rev)):
            diag.append("reported_vs_computed_revenue_mismatch")
            if sev != "error":
                sev = "warning"

    if qty_sold is not None and qty_sold < 0:
        diag.append("return_or_credit_suspected_qty")
        if sev == "info":
            sev = "warning"
    if reported_rev is not None and reported_rev < 0:
        diag.append("return_or_credit_suspected_revenue")
        if sev == "info":
            sev = "warning"

    can_sellout = (
        not hard_row
        and bool(rdistributor_id)
        and bool(rpid)
        and tx_date is not None
        and qty_sold is not None
        and qty_sold != 0
        and bool(rcustomer_id)
    )
    can_inv = (
        not hard_row
        and bool(rdistributor_id)
        and bool(rpid)
        and snap_date is not None
        and soh is not None
    )
    if sev == "error":
        res_status = "blocked"
    elif can_sellout and can_inv:
        res_status = "ready_both"
    elif can_sellout:
        res_status = "ready_sellout"
    elif can_inv:
        res_status = "ready_inventory"
    else:
        res_status = "staged_only"

    _append_shipment_corroboration_signals_dsi(
        db,
        diag,
        rdistributor_id=rdistributor_id,
        evidence_date=evidence_date,
        prod_raw=prod_raw,
        rpid=rpid,
        cust_raw=cust_raw,
        dg_raw=dg_raw,
        rcustomer_id=rcustomer_id,
    )

    line.resolved_distributor_id = rdistributor_id
    line.resolved_customer_id = rcustomer_id
    line.resolved_product_id = rpid
    line.resolution_status = res_status
    line.diagnostic_codes = diag
    line.severity = sev
    line.computed_revenue_amount = float(computed_rev) if computed_rev is not None else None
    line.currency_code = (cur[:8] if cur else None)
    db.add(line)


def refresh_dsi_staging_lines_for_job(db: Session, job: ImportJob) -> None:
    """Re-resolve every DSI staging line for a job (after steward-side mapping changes)."""

    prod_idx = _load_product_resolution_index(db)
    lines = list(
        db.scalars(
            select(ImportDistributorSiStagingLine)
            .where(ImportDistributorSiStagingLine.import_job_id == job.id)
            .order_by(ImportDistributorSiStagingLine.source_row_number)
        ).all()
    )
    for line in lines:
        refresh_dsi_staging_line_resolution(db, job, line, prod_idx)


def _invoice_no_for_staging_line(line: ImportDistributorSiStagingLine) -> str:
    if line.invoice_no is not None and str(line.invoice_no).strip():
        return normalize_dsi_invoice_no(line.invoice_no)
    mapped = line.mapped_canonical if isinstance(line.mapped_canonical, dict) else {}
    return normalize_dsi_invoice_no(mapped.get("invoice_no"))


def upsert_dsi_facts_for_staging_job(db: Session, job: ImportJob) -> tuple[int, int, int, list[str]]:
    """Apply sell-out / returns / inventory fact upserts for staging lines (import_mode apply)."""
    errors: list[str] = []
    sell_tbl = FactSalesSellout.__table__
    ret_tbl = FactReturns.__table__
    inv_tbl = FactInventoryDistributor.__table__
    lines = db.scalars(
        select(ImportDistributorSiStagingLine)
        .where(ImportDistributorSiStagingLine.import_job_id == job.id)
        .order_by(ImportDistributorSiStagingLine.source_row_number)
    ).all()
    applied_sell = 0
    applied_inv = 0
    applied_ret = 0
    for line in lines:
        parts: list[str] = []
        qs = line.quantity_sold
        qty_f = float(qs) if qs is not None else None
        inv_no = _invoice_no_for_staging_line(line)
        tx = line.transaction_date

        if (
            line.resolved_distributor_id
            and line.resolved_product_id
            and tx is not None
            and qty_f is not None
            and qty_f > 0
            and line.resolved_customer_id
        ):
            eff = line.computed_revenue_amount
            if eff is None and line.reported_revenue_amount is not None:
                eff = line.reported_revenue_amount
            if eff is None:
                eff = 0.0
            try:
                dist_id = int(line.resolved_distributor_id)
                cust_id = int(line.resolved_customer_id)
                prod_id = int(line.resolved_product_id)
                sk = dsi_sellout_source_key(
                    distributor_id=dist_id,
                    customer_id=cust_id,
                    product_id=prod_id,
                    transaction_date=tx,
                    invoice_no=inv_no,
                )
                stmt = (
                    pg_insert(sell_tbl)
                    .values(
                        source_key=sk,
                        staging_line_id=int(line.id),
                        product_id=prod_id,
                        customer_id=cust_id,
                        distributor_id=dist_id,
                        channel_id=None,
                        period_start=tx,
                        transaction_date=tx,
                        invoice_no=inv_no,
                        units=qty_f,
                        revenue=float(eff),
                        unit_sellout_price_ex_tax_amount=line.unit_sellout_price_ex_tax_amount,
                        reported_revenue_amount=line.reported_revenue_amount,
                        computed_revenue_amount=line.computed_revenue_amount,
                        currency_code=line.currency_code,
                        source_import_job_id=job.id,
                    )
                    .on_conflict_do_update(
                        constraint="uq_fact_sales_sellout_source_key",
                        set_={
                            "staging_line_id": text("EXCLUDED.staging_line_id"),
                            "units": text("EXCLUDED.units"),
                            "revenue": text("EXCLUDED.revenue"),
                            "unit_sellout_price_ex_tax_amount": text(
                                "EXCLUDED.unit_sellout_price_ex_tax_amount"
                            ),
                            "reported_revenue_amount": text("EXCLUDED.reported_revenue_amount"),
                            "computed_revenue_amount": text("EXCLUDED.computed_revenue_amount"),
                            "currency_code": text("EXCLUDED.currency_code"),
                            "source_import_job_id": text("EXCLUDED.source_import_job_id"),
                            "updated_at": text("now()"),
                        },
                    )
                    .returning(sell_tbl.c.id)
                )
                rid = db.execute(stmt).scalar_one()
                line.fact_sellout_row_id = int(rid) if rid is not None else None
                applied_sell += 1
                parts.append("sellout")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"sellout row {line.source_row_number}: {exc}")

        elif (
            line.resolved_distributor_id
            and line.resolved_product_id
            and tx is not None
            and qty_f is not None
            and qty_f < 0
            and line.resolved_customer_id
        ):
            unit_px = line.unit_sellout_price_ex_tax_amount
            if unit_px is None and line.reported_revenue_amount is not None and qty_f != 0:
                unit_px = abs(float(line.reported_revenue_amount) / qty_f)
            try:
                dist_id = int(line.resolved_distributor_id)
                cust_id = int(line.resolved_customer_id)
                prod_id = int(line.resolved_product_id)
                sk = dsi_return_source_key(
                    distributor_id=dist_id,
                    customer_id=cust_id,
                    product_id=prod_id,
                    transaction_date=tx,
                    invoice_no=inv_no,
                )
                ret_stmt = (
                    pg_insert(ret_tbl)
                    .values(
                        source_key=sk,
                        staging_line_id=int(line.id),
                        distributor_id=dist_id,
                        product_id=prod_id,
                        customer_id=cust_id,
                        transaction_date=tx,
                        invoice_no=inv_no,
                        return_quantity=abs(qty_f),
                        unit_price=unit_px,
                        import_job_id=job.id,
                    )
                    .on_conflict_do_update(
                        constraint="uq_fact_returns_source_key",
                        set_={
                            "return_quantity": text("EXCLUDED.return_quantity"),
                            "unit_price": text("EXCLUDED.unit_price"),
                            "updated_at": text("now()"),
                        },
                    )
                    .returning(ret_tbl.c.id)
                )
                db.execute(ret_stmt).scalar_one()
                applied_ret += 1
                parts.append("return")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"return row {line.source_row_number}: {exc}")

        if (
            line.resolved_distributor_id
            and line.resolved_product_id
            and line.snapshot_date is not None
            and line.stock_on_hand is not None
        ):
            try:
                dist_id = int(line.resolved_distributor_id)
                prod_id = int(line.resolved_product_id)
                snap = line.snapshot_date
                inv_sk = dsi_inventory_source_key(
                    distributor_id=dist_id,
                    product_id=prod_id,
                    as_of_date=snap,
                )
                inv_stmt = (
                    pg_insert(inv_tbl)
                    .values(
                        source_key=inv_sk,
                        product_id=prod_id,
                        distributor_id=dist_id,
                        as_of_date=snap,
                        on_hand_units=float(line.stock_on_hand),
                        source_import_job_id=job.id,
                    )
                    .on_conflict_do_update(
                        constraint="uq_fact_inventory_distributor_source_key",
                        set_={
                            "on_hand_units": text("EXCLUDED.on_hand_units"),
                            "source_import_job_id": text("EXCLUDED.source_import_job_id"),
                            "updated_at": text("now()"),
                        },
                    )
                    .returning(inv_tbl.c.id)
                )
                iid = db.execute(inv_stmt).scalar_one()
                line.fact_inventory_row_id = int(iid) if iid is not None else None
                applied_inv += 1
                parts.append("inventory")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"inventory row {line.source_row_number}: {exc}")

        if parts:
            line.apply_status = "+".join(parts)
        db.add(line)
    meta = dict(job.staged_metadata or {})
    meta["distributor_si"] = to_jsonable(
        {
            "applied": True,
            "applied_at": datetime.now(timezone.utc).isoformat(),
            "sellout_rows": applied_sell,
            "return_rows": applied_ret,
            "inventory_rows": applied_inv,
            "apply_errors": errors[:50],
        }
    )
    job.staged_metadata = to_jsonable(meta)
    db.add(job)
    return applied_sell, applied_inv, applied_ret, errors

