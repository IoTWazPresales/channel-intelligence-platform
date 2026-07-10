"""Derive business_unit for a commercial lineup case / sheet slice (Spec C §3.5).

Pure resolver tiers (never block — unresolved / low confidence surfaces flags only):

1. product-derived — SKU tokens via shared ``resolve_product_id_single_match`` → dim_product.business_unit
2. shipment-derived — catalogue-miss tokens corroborated from shipment_evidence_line → product BU
3. sheet code — NB / NR / NX / NV
4. folder path — archive segment (e.g. ``NB\\2025\\Q1``)
5. manual — steward override

Reuses ``ProductResolutionIndex`` / ``product_resolution_standard`` — no parallel product resolver.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dimensions import DimProduct
from app.services.imports.shipment_evidence_read import (
    apply_active_evidence_filter,
    shipment_evidence_read_model,
)

EV = shipment_evidence_read_model()
from app.services.imports.distributor_sales_inventory import ProductResolutionIndex, _product_token_key
from app.services.imports.product_resolution_standard import resolve_product_id_single_match

# Default sheet/folder BU codes when no tenant config is supplied (unit tests / legacy).
CANONICAL_SHEET_BU_CODES: frozenset[str] = frozenset({"NB", "NR", "NX", "NV"})


def _bu_codes(tenant_bu_codes: frozenset[str] | None) -> frozenset[str]:
    return tenant_bu_codes if tenant_bu_codes is not None else CANONICAL_SHEET_BU_CODES


def _norm_sheet_bu(
    value: str | None,
    *,
    tenant_bu_codes: frozenset[str] | None = None,
) -> str | None:
    if not value:
        return None
    codes = _bu_codes(tenant_bu_codes)
    text = str(value).strip().upper()
    if not text or text in ("SHEET1", "SHEET2", "DATA"):
        return None
    # Exact sheet tab codes.
    if text in codes:
        return text
    # Leading token before space/punctuation, e.g. "NB Consumer" -> NB.
    head = re.split(r"[\s_\-]+", text, maxsplit=1)[0]
    return head if head in codes else None


def infer_business_unit_from_sheet_code(
    sheet_name: str | None,
    *,
    tenant_bu_codes: frozenset[str] | None = None,
) -> str | None:
    return _norm_sheet_bu(sheet_name, tenant_bu_codes=tenant_bu_codes)


def infer_business_unit_from_folder_path(
    folder_path: str | None,
    *,
    tenant_bu_codes: frozenset[str] | None = None,
) -> str | None:
    """Return the first path segment that matches a tenant BU code."""
    if not folder_path:
        return None
    for segment in re.split(r"[\\/]+", str(folder_path).strip()):
        bu = _norm_sheet_bu(segment, tenant_bu_codes=tenant_bu_codes)
        if bu:
            return bu
    return None


# Below this resolved-row fraction the sheet is likely a spec-dump / non-lineup shape (job #217).
LIKELY_NOT_LINEUP_RESOLUTION_RATE: float = 0.05

# Minimum resolved fraction before product-derived BU is chosen as the winning tier.
PRODUCT_DERIVED_MIN_RESOLVED_FRACTION: float = 0.25


@dataclass(frozen=True, slots=True)
class LineupBuResolutionReport:
    """Structured BU derivation outcome — advisory flags, never raises."""

    business_unit: str | None
    source_tier: str | None  # product | shipment | sheet | folder | manual
    flags: list[str] = field(default_factory=list)
    product_resolution_rate: float | None = None
    product_derived_bu: str | None = None
    label_bu: str | None = None
    bu_vote_counts: dict[str, int] = field(default_factory=dict)
    per_tier: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "business_unit": self.business_unit,
            "source_tier": self.source_tier,
            "flags": list(self.flags),
            "product_resolution_rate": self.product_resolution_rate,
            "product_derived_bu": self.product_derived_bu,
            "label_bu": self.label_bu,
            "bu_vote_counts": dict(self.bu_vote_counts),
            "per_tier": dict(self.per_tier),
        }


@dataclass(frozen=True, slots=True)
class LineupRowProductTokens:
    """One lineup row's product identity candidates (parser-aligned field order)."""

    sku_raw: str | None = None
    part_number_raw: str | None = None
    model_raw: str | None = None


def _majority_vote(counts: dict[str, int]) -> tuple[str | None, dict[str, int]]:
    if not counts:
        return None, {}
    winner = max(counts.items(), key=lambda kv: (kv[1], kv[0]))[0]
    return winner, counts


def resolve_row_product_id(
    index: ProductResolutionIndex,
    row: LineupRowProductTokens,
) -> int | None:
    """Resolve one lineup row to dim_product.id using the shared single-match tiers."""
    for raw in (row.sku_raw, row.part_number_raw, row.model_raw):
        if not raw:
            continue
        pid = resolve_product_id_single_match(index, raw)
        if pid is not None:
            return int(pid)
    return None


def _derive_product_tier(
    rows: list[LineupRowProductTokens],
    index: ProductResolutionIndex,
    business_unit_by_product_id: dict[int, str],
) -> tuple[str | None, float, dict[str, int], list[str]]:
    """Product-derived BU + resolution rate + per-BU vote counts + tier-local flags."""
    flags: list[str] = []
    total = len(rows)
    if total == 0:
        return None, 0.0, {}, flags

    resolved_bus: list[str] = []
    resolved_count = 0
    for row in rows:
        pid = resolve_row_product_id(index, row)
        if pid is None:
            continue
        resolved_count += 1
        bu = business_unit_by_product_id.get(pid)
        if bu and str(bu).strip():
            resolved_bus.append(str(bu).strip()[:64])

    rate = resolved_count / total
    if rate < LIKELY_NOT_LINEUP_RESOLUTION_RATE:
        flags.append("bu_likely_not_lineup")

    bu_counts: dict[str, int] = {}
    for bu in resolved_bus:
        bu_counts[bu] = bu_counts.get(bu, 0) + 1

    if len(bu_counts) >= 2:
        flags.append("bu_multi_bu_in_sheet")

    majority, _ = _majority_vote(bu_counts)
    if rate >= PRODUCT_DERIVED_MIN_RESOLVED_FRACTION and majority:
        return majority, rate, bu_counts, flags

    # Under-resolved — product tier does not win, but expose majority if any for mismatch checks.
    return majority if majority else None, rate, bu_counts, flags


def _derive_shipment_tier(shipment_business_units: list[str]) -> str | None:
    counts: dict[str, int] = {}
    for bu in shipment_business_units:
        text = str(bu).strip()
        if text:
            key = text[:64]
            counts[key] = counts.get(key, 0) + 1
    winner, _ = _majority_vote(counts)
    return winner


def _label_bu(
    sheet_name: str | None,
    folder_path: str | None,
    *,
    tenant_bu_codes: frozenset[str] | None = None,
) -> str | None:
    return infer_business_unit_from_sheet_code(sheet_name, tenant_bu_codes=tenant_bu_codes) or infer_business_unit_from_folder_path(
        folder_path, tenant_bu_codes=tenant_bu_codes
    )


def resolve_lineup_business_unit(
    *,
    rows: list[LineupRowProductTokens],
    product_index: ProductResolutionIndex,
    business_unit_by_product_id: dict[int, str],
    shipment_business_units: list[str] | None = None,
    sheet_name: str | None = None,
    folder_path: str | None = None,
    manual_business_unit: str | None = None,
    tenant_bu_codes: frozenset[str] | None = None,
) -> LineupBuResolutionReport:
    """Ordered fallback BU resolver. Never raises; low confidence → flags only."""
    flags: list[str] = []
    per_tier: dict[str, Any] = {}

    label = _label_bu(sheet_name, folder_path, tenant_bu_codes=tenant_bu_codes)

    if manual_business_unit and str(manual_business_unit).strip():
        bu = str(manual_business_unit).strip()[:64]
        return LineupBuResolutionReport(
            business_unit=bu,
            source_tier="manual",
            flags=flags,
            label_bu=label,
            per_tier={"manual": bu},
        )

    product_bu, rate, bu_counts, product_flags = _derive_product_tier(
        rows, product_index, business_unit_by_product_id
    )
    flags.extend(product_flags)
    per_tier["product"] = {
        "candidate_bu": product_bu,
        "resolution_rate": rate,
        "bu_vote_counts": bu_counts,
        "resolved_rows": sum(bu_counts.values()),
        "total_rows": len(rows),
    }

    if product_bu and rate >= PRODUCT_DERIVED_MIN_RESOLVED_FRACTION:
        if label and label != product_bu:
            flags.append("bu_label_product_mismatch")
        return LineupBuResolutionReport(
            business_unit=product_bu,
            source_tier="product",
            flags=_dedupe_flags(flags),
            product_resolution_rate=rate,
            product_derived_bu=product_bu,
            label_bu=label,
            bu_vote_counts=bu_counts,
            per_tier=per_tier,
        )

    shipment_bus = list(shipment_business_units or [])
    shipment_bu = _derive_shipment_tier(shipment_bus)
    per_tier["shipment"] = {"candidate_bu": shipment_bu, "hint_count": len(shipment_bus)}
    if shipment_bu:
        if label and label != shipment_bu:
            flags.append("bu_label_product_mismatch")
        return LineupBuResolutionReport(
            business_unit=shipment_bu,
            source_tier="shipment",
            flags=_dedupe_flags(flags),
            product_resolution_rate=rate,
            product_derived_bu=product_bu,
            label_bu=label,
            bu_vote_counts=bu_counts,
            per_tier=per_tier,
        )

    sheet_bu = infer_business_unit_from_sheet_code(sheet_name, tenant_bu_codes=tenant_bu_codes)
    per_tier["sheet"] = {"candidate_bu": sheet_bu, "sheet_name": sheet_name}
    if sheet_bu:
        if product_bu and product_bu != sheet_bu:
            flags.append("bu_label_product_mismatch")
        return LineupBuResolutionReport(
            business_unit=sheet_bu,
            source_tier="sheet",
            flags=_dedupe_flags(flags),
            product_resolution_rate=rate,
            product_derived_bu=product_bu,
            label_bu=label,
            bu_vote_counts=bu_counts,
            per_tier=per_tier,
        )

    folder_bu = infer_business_unit_from_folder_path(folder_path, tenant_bu_codes=tenant_bu_codes)
    per_tier["folder"] = {"candidate_bu": folder_bu, "folder_path": folder_path}
    if folder_bu:
        if product_bu and product_bu != folder_bu:
            flags.append("bu_label_product_mismatch")
        return LineupBuResolutionReport(
            business_unit=folder_bu,
            source_tier="folder",
            flags=_dedupe_flags(flags),
            product_resolution_rate=rate,
            product_derived_bu=product_bu,
            label_bu=label,
            bu_vote_counts=bu_counts,
            per_tier=per_tier,
        )

    # No tier produced a BU — still return diagnostic report (non-blocking).
    return LineupBuResolutionReport(
        business_unit=None,
        source_tier=None,
        flags=_dedupe_flags(flags),
        product_resolution_rate=rate,
        product_derived_bu=product_bu,
        label_bu=label,
        bu_vote_counts=bu_counts,
        per_tier=per_tier,
    )


def _dedupe_flags(flags: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for f in flags:
        if f not in seen:
            seen.add(f)
            out.append(f)
    return out


async def load_business_unit_by_product_id(db: AsyncSession) -> dict[int, str]:
    """Folder-grain BU (NB/NR/NV/PF/XB) from ``dim_product.product_line`` for resolver product tier.

    ``dim_product.business_unit`` is division-level (CONSUMER/COMMERCIAL) — not used here.
    """
    rows = (await db.execute(select(DimProduct.id, DimProduct.product_line))).all()
    out: dict[int, str] = {}
    for pid, product_line in rows:
        if product_line and str(product_line).strip():
            out[int(pid)] = str(product_line).strip()
    return out


async def load_shipment_business_unit_hints(
    db: AsyncSession,
    tokens: list[str],
    *,
    customer_id: int | None = None,
    distributor_id: int | None = None,
) -> list[str]:
    """Shipment-derived BU hints for catalogue-miss tokens (resolved product on evidence lines)."""
    keys = sorted({_product_token_key(t) for t in tokens if _product_token_key(t)})
    if not keys:
        return []

    token_match = or_(
        func.lower(func.trim(EV.item_code)).in_(keys),
        func.lower(func.trim(EV.sales_model_name)).in_(keys),
        func.lower(func.trim(EV.ean_code)).in_(keys),
        func.lower(func.trim(EV.upc_code)).in_(keys),
    )
    stmt = apply_active_evidence_filter(
        select(DimProduct.business_unit, DimProduct.product_line)
        .join(EV, EV.product_id == DimProduct.id)
        .where(EV.product_id.isnot(None), token_match),
        model=EV,
    )
    if customer_id is not None:
        stmt = stmt.where(
            or_(
                EV.resolved_customer_id == customer_id,
                EV.customer_id == customer_id,
            )
        )
    if distributor_id is not None:
        stmt = stmt.where(
            or_(
                EV.resolved_distributor_id == distributor_id,
                EV.distributor_id == distributor_id,
            )
        )

    hints: list[str] = []
    for division_bu, product_line in (await db.execute(stmt)).all():
        if product_line and str(product_line).strip():
            hints.append(str(product_line).strip())
        elif division_bu and str(division_bu).strip():
            hints.append(str(division_bu).strip())
    return hints
