"""Distributor sales & inventory import: staging, resolution, aggregated mapping candidates, fact apply."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import pandas as pd
from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.dimensions import DimCustomer, DimDistributor, DimProduct
from app.models.facts import FactInventoryDistributor, FactSalesSellout
from app.models.import_distributor_si import (
    CustomerSourceTokenAlias,
    DistributorSourceTokenAlias,
    ImportDistributorSiStagingLine,
    ImportEntityMappingCandidate,
)
from app.models.ingestion import ImportJob, ImportRowResult
from app.models.mapping import ProductAlias
from app.services.commercial_planner.open_channel_customer import OPEN_CHANNEL_CUSTOMER_CODE
from app.utils.json_safe import to_jsonable, verify_json_serializable

CANONICAL = (
    "distributor_token",
    "product_identifier",
    "transaction_date",
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


def _product_eligible_for_dsi_auto(p: DimProduct, evidence_date: date | None) -> bool:
    """Whether a Product Master row may receive **automatic** DSI resolution (never silent pick).

    Inactive / clearly retired-lifecycle strings / outside launch–retire window for the evidence date
    are ineligible. Empty ``lifecycle_status`` does not alone disqualify if ``is_active`` is true.
    """
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
    """Load Product Master identity fields + ProductAlias for DSI resolution (single pass per import job)."""
    products = list(db.scalars(select(DimProduct)).all())
    products_by_id: dict[int, DimProduct] = {int(p.id): p for p in products}
    sku_to_id: dict[str, int] = {}
    part_pairs: list[tuple[str, int]] = []
    sm_pairs: list[tuple[str, int]] = []
    model_pairs: list[tuple[str, int]] = []
    mkt_pairs: list[tuple[str, int]] = []
    ean_pairs: list[tuple[str, int]] = []
    upc_pairs: list[tuple[str, int]] = []
    for p in products:
        sk = _product_token_key(p.sku)
        if sk:
            sku_to_id[sk] = int(p.id)
        pk = _product_token_key(p.part_number)
        if pk:
            part_pairs.append((pk, int(p.id)))
        sm = _product_token_key(p.sales_model_name)
        if sm:
            sm_pairs.append((sm, int(p.id)))
        mn = _product_token_key(p.model_name)
        if mn:
            model_pairs.append((mn, int(p.id)))
        mk = _product_token_key(p.marketing_name)
        if mk:
            mkt_pairs.append((mk, int(p.id)))
        ean = _product_token_key(p.ean)
        if ean:
            ean_pairs.append((ean, int(p.id)))
        upc = _product_token_key(p.upc)
        if upc:
            upc_pairs.append((upc, int(p.id)))
    alias_pairs: list[tuple[str, int]] = []
    steward_alias_by_key: dict[str, int] = {}
    for a in db.scalars(select(ProductAlias)).all():
        av = _product_token_key(a.alias_value)
        if av:
            alias_pairs.append((av, int(a.product_id)))
            if (getattr(a, "confidence", None) or "") == "steward_approved":
                pid_a = int(a.product_id)
                if pid_a in products_by_id:
                    steward_alias_by_key[av] = pid_a
    return ProductResolutionIndex(
        sku_to_id=sku_to_id,
        part_number_to_ids=_multimap_from_pairs(part_pairs),
        sales_model_name_to_ids=_multimap_from_pairs(sm_pairs),
        model_name_to_ids=_multimap_from_pairs(model_pairs),
        marketing_name_to_ids=_multimap_from_pairs(mkt_pairs),
        ean_to_ids=_multimap_from_pairs(ean_pairs),
        upc_to_ids=_multimap_from_pairs(upc_pairs),
        alias_value_to_ids=_multimap_from_pairs(alias_pairs),
        products_by_id=products_by_id,
        steward_alias_by_key=steward_alias_by_key,
    )


def _resolve_product(
    raw: str | None, idx: ProductResolutionIndex, evidence_date: date | None = None
) -> tuple[int | None, str | None, str | None, ProductResolutionEvidence | None]:
    """Resolve RAW product_identifier to dim_product.id with lifecycle-aware eligibility.

    **Steward-approved aliases** (``ProductAlias.confidence == "steward_approved"``), keyed like other
    lookups via ``_product_token_key``, are evaluated **first**. They bind distributor-reported tokens to
    Product Master rows chosen by a human and must survive revalidation even when an inactive SKU or
    ambiguous identity tier would otherwise block automatic resolution (including inactive targets for
    historical DSI evidence).

    Automatic tier order: SKU → part_number → sales_model_name → model_name → marketing_name → ean → upc
    → non-steward ProductAlias. Within a tier: **only eligible** rows may auto-resolve; multiple eligible
    hits defer ambiguity until lower tiers (e.g. a clarifying alias) are tried. Ineligible-only hits at a
    tier are recorded and the walk **continues**.

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
            if p is not None and _product_eligible_for_dsi_auto(p, evidence_date):
                out.append(int(i))
        return out

    def _inactive_snapshots(tier: str, ids: tuple[int, ...]) -> list[dict[str, Any]]:
        snaps: list[dict[str, Any]] = []
        for i in ids:
            p = idx.products_by_id.get(int(i))
            if p is None:
                continue
            if _product_eligible_for_dsi_auto(p, evidence_date):
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
        if p0 is not None and _product_eligible_for_dsi_auto(p0, evidence_date):
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
            if p is not None and _product_eligible_for_dsi_auto(p, evidence_date):
                elig_a.append(int(aid))
        if len(elig_a) == 1:
            return int(elig_a[0]), None, "product_resolved_alias", None
        if len(elig_a) > 1:
            snaps = [_product_snapshot_for_dsi_context(idx.products_by_id[i]) for i in sorted(set(elig_a))]
            amb = {
                "tier": "product_alias",
                "product_ids": sorted(set(elig_a)),
                "eligible_products": snaps[:12],
            }
            return None, "ambiguous_product_alias", None, ProductResolutionEvidence(ambiguous_eligible=amb)
        in_sn = _inactive_snapshots("product_alias", a_ids)
        accumulated.inactive_hits.extend(in_sn)

    if pending_ambiguous is not None:
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


def process_distributor_sales_inventory(db: Session, job: ImportJob, df: pd.DataFrame, mapping: dict[str, str]) -> int:
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

    db.execute(delete(ImportDistributorSiStagingLine).where(ImportDistributorSiStagingLine.import_job_id == job.id))
    db.execute(delete(ImportEntityMappingCandidate).where(ImportEntityMappingCandidate.import_job_id == job.id))
    db.flush()

    ignored_src_cols = [k for k, v in mapping.items() if v == "ignored_shipping_evidence"]

    prod_idx = _load_product_resolution_index(db)
    source = job.source
    source_def_id = source.id if source else None

    agg: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {
            "row_count": 0,
            "total_units": Decimal(0),
            "total_value": Decimal(0),
            "samples": [],
            "strategic_channel_hint": False,
            "customer_evidence_norms": [],
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

    for idx, row in df.iterrows():
        rn = int(idx) + 1
        raw_payload = {str(k): to_jsonable(row[k]) for k in row.index}
        mapped = _build_mapped_canonical(row, mapping, ignored_src_cols)
        verify_json_serializable("raw_row_payload", raw_payload)
        verify_json_serializable("mapped_canonical", mapped)

        dist_raw = _clean_str(row.get(_col(mapping, "distributor_token"))) if _col(mapping, "distributor_token") else None
        prod_raw = _clean_str(row.get(_col(mapping, "product_identifier"))) if _col(mapping, "product_identifier") else None
        cust_raw = _clean_str(row.get(_col(mapping, "customer_dealer_token"))) if _col(mapping, "customer_dealer_token") else None
        dg_raw = _clean_str(row.get(_col(mapping, "dealer_group_token"))) if _col(mapping, "dealer_group_token") else None
        ch_raw = _channel_raw_for_dsi(row, mapping)
        reg_raw = _region_raw_for_dsi(row, mapping)
        open_raw = row.get(_col(mapping, "open_channel_evidence")) if _col(mapping, "open_channel_evidence") else None

        tx_date = _parse_date(row.get(_col(mapping, "transaction_date"))) if _col(mapping, "transaction_date") else None
        snap_date = _parse_date(row.get(_col(mapping, "snapshot_date"))) if _col(mapping, "snapshot_date") else None
        if tx_date is None and snap_date is not None:
            tx_date = snap_date
        if snap_date is None and tx_date is not None:
            snap_date = tx_date

        qty_sold = _parse_decimal(row.get(_col(mapping, "quantity_sold"))) if _col(mapping, "quantity_sold") else None
        soh = _parse_decimal(row.get(_col(mapping, "stock_on_hand"))) if _col(mapping, "stock_on_hand") else None
        unit_price = (
            _parse_decimal(row.get(_col(mapping, "unit_sellout_price_ex_tax_amount")))
            if _col(mapping, "unit_sellout_price_ex_tax_amount")
            else None
        )
        reported_rev = (
            _parse_decimal(row.get(_col(mapping, "reported_revenue_amount")))
            if _col(mapping, "reported_revenue_amount")
            else None
        )
        cur = _clean_str(row.get(_col(mapping, "currency_code"))) if _col(mapping, "currency_code") else None

        computed_rev: Decimal | None = None
        if qty_sold is not None and unit_price is not None:
            computed_rev = qty_sold * unit_price

        diag: list[str] = []

        rdid, derr = _resolve_distributor(db, dist_raw, source_def_id)
        if derr:
            diag.append(derr)

        evidence_date = tx_date or snap_date
        rpid, perr, presolve_tag, pev = _resolve_product(prod_raw, prod_idx, evidence_date)
        if perr:
            diag.append(perr)
        elif presolve_tag:
            diag.append(presolve_tag)

        rdistributor_id = rdid
        rcustomer_id: int | None = None

        sellout_attempt = (
            qty_sold is not None and tx_date is not None and qty_sold != 0
        )
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
        sellout_blocked_no_tx = bool(
            qty_sold is not None and qty_sold != 0 and tx_date is None
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

        line = ImportDistributorSiStagingLine(
            import_job_id=job.id,
            source_row_number=rn,
            raw_row_payload=raw_payload,
            mapped_canonical=mapped,
            raw_distributor_token=dist_raw,
            raw_customer_dealer_token=cust_raw,
            raw_dealer_group_token=dg_raw,
            raw_product_token=prod_raw,
            resolved_distributor_id=rdistributor_id,
            resolved_customer_id=rcustomer_id,
            resolved_product_id=rpid,
            transaction_date=tx_date,
            snapshot_date=snap_date,
            quantity_sold=float(qty_sold) if qty_sold is not None else None,
            stock_on_hand=float(soh) if soh is not None else None,
            unit_sellout_price_ex_tax_amount=float(unit_price) if unit_price is not None else None,
            reported_revenue_amount=float(reported_rev) if reported_rev is not None else None,
            computed_revenue_amount=float(computed_rev) if computed_rev is not None else None,
            currency_code=(cur[:8] if cur else None),
            resolution_status=res_status,
            diagnostic_codes=diag,
            severity=sev,
            apply_status="pending",
        )
        db.add(line)

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
            a["row_count"] += 1
            if qty_sold is not None:
                a["total_units"] += abs(qty_sold)
            if reported_rev is not None:
                a["total_value"] += abs(reported_rev)
            if len(a["samples"]) < 5:
                a["samples"].append(prod_raw)
        if sellout_attempt and rcustomer_id is None:
            ckey = _customer_candidate_identity_norm(cust_raw, dg_raw)
            k = ("customer_dealer_token", ckey)
            a = agg[k]
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
            cu_ev = (
                _norm_key(cust_raw)
                if cust_raw and not _customer_token_is_placeholder(_norm_key(cust_raw), cust_raw)
                else None
            )
            if cu_ev:
                lst = a["customer_evidence_norms"]
                if cu_ev not in lst and len(lst) < 8:
                    lst.append(cu_ev)
            if dg_raw and not _dealer_group_is_placeholder(dg_raw):
                if a.get("dealer_group_raw") is None:
                    a["dealer_group_raw"] = dg_raw.strip()[:512]
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
            if ps == "dealer_name_group":
                if isinstance(dgr_store, str) and dgr_store.strip():
                    dealer_token_col = dgr_store.strip()[:512]
                elif nkey_clean and nkey_clean != "__blank__":
                    dealer_token_col = nkey_clean[:512]
        if etype == "product_identifier":
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
            status="needs_review",
            context=to_jsonable(ctx),
        )
        db.add(cand)

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
        sell_tbl = FactSalesSellout.__table__
        inv_tbl = FactInventoryDistributor.__table__
        lines = db.scalars(
            select(ImportDistributorSiStagingLine)
            .where(ImportDistributorSiStagingLine.import_job_id == job.id)
            .order_by(ImportDistributorSiStagingLine.source_row_number)
        ).all()
        applied_sell = 0
        applied_inv = 0
        for line in lines:
            parts = []
            qs = line.quantity_sold
            sellout_units_ok = (
                qs is not None
                and float(qs) != 0.0
            )
            if (
                line.resolved_distributor_id
                and line.resolved_product_id
                and line.transaction_date is not None
                and qs is not None
                and sellout_units_ok
                and line.resolved_customer_id
            ):
                eff = line.computed_revenue_amount
                if eff is None and line.reported_revenue_amount is not None:
                    eff = line.reported_revenue_amount
                if eff is None:
                    eff = 0.0
                stmt = (
                    pg_insert(sell_tbl)
                    .values(
                        product_id=line.resolved_product_id,
                        customer_id=line.resolved_customer_id,
                        distributor_id=line.resolved_distributor_id,
                        channel_id=None,
                        period_start=line.transaction_date,
                        units=line.quantity_sold,
                        revenue=float(eff),
                        unit_sellout_price_ex_tax_amount=line.unit_sellout_price_ex_tax_amount,
                        reported_revenue_amount=line.reported_revenue_amount,
                        computed_revenue_amount=line.computed_revenue_amount,
                        currency_code=line.currency_code,
                        source_import_job_id=job.id,
                    )
                    .on_conflict_do_update(
                        constraint="uq_fact_sales_sellout_dsi_v1",
                        set_={
                            "units": text("EXCLUDED.units"),
                            "revenue": text("EXCLUDED.revenue"),
                            "unit_sellout_price_ex_tax_amount": text("EXCLUDED.unit_sellout_price_ex_tax_amount"),
                            "reported_revenue_amount": text("EXCLUDED.reported_revenue_amount"),
                            "computed_revenue_amount": text("EXCLUDED.computed_revenue_amount"),
                            "currency_code": text("EXCLUDED.currency_code"),
                            "source_import_job_id": text("EXCLUDED.source_import_job_id"),
                        },
                    )
                    .returning(sell_tbl.c.id)
                )
                rid = db.execute(stmt).scalar_one()
                line.fact_sellout_row_id = int(rid) if rid is not None else None
                applied_sell += 1
                parts.append("sellout")
            if (
                line.resolved_distributor_id
                and line.resolved_product_id
                and line.snapshot_date is not None
                and line.stock_on_hand is not None
            ):
                inv_stmt = (
                    pg_insert(inv_tbl)
                    .values(
                        product_id=line.resolved_product_id,
                        distributor_id=line.resolved_distributor_id,
                        as_of_date=line.snapshot_date,
                        on_hand_units=float(line.stock_on_hand),
                        source_import_job_id=job.id,
                    )
                    .on_conflict_do_update(
                        constraint="uq_fact_inventory_distributor_dsi_v1",
                        set_={
                            "on_hand_units": text("EXCLUDED.on_hand_units"),
                            "source_import_job_id": text("EXCLUDED.source_import_job_id"),
                        },
                    )
                    .returning(inv_tbl.c.id)
                )
                iid = db.execute(inv_stmt).scalar_one()
                line.fact_inventory_row_id = int(iid) if iid is not None else None
                applied_inv += 1
                parts.append("inventory")
            if parts:
                line.apply_status = "+".join(parts)
        meta = dict(job.staged_metadata or {})
        meta["distributor_si"] = to_jsonable(
            {
                "applied": True,
                "applied_at": datetime.now(timezone.utc).isoformat(),
                "sellout_rows": applied_sell,
                "inventory_rows": applied_inv,
            }
        )
        job.staged_metadata = to_jsonable(meta)
        eff_rev_note = f" Applied sell-out facts={applied_sell}, inventory facts={applied_inv} (upsert by natural key)."

    summary = {
        "staging_rows": int(len(df)),
        "blocking_rows": blocking,
        "warning_rows": warnings,
        "aggregated_candidates": len(agg),
        "import_mode": job.import_mode,
        "sellout_issue_rows": dsi_sellout_issue_rows,
        "rows_inventory_ready_with_sellout_warnings": dsi_inv_ready_with_sellout_issue_rows,
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
    return 1 if blocking else 0

