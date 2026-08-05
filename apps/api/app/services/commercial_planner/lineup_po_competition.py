"""PO auto-link competition classifier (BACKLOG-119 / D-033).

Multiple BUs may legitimately share one PO. Contested means shipment evidence does
**not** explain the multiple claims. Annotation only — FLAG ≠ BLOCK (never gates apply).

BU grain is ``dim_product.product_line`` (NB/NR/NV/…) — never ``business_unit`` (CONSUMER).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from app.services.commercial_planner.lineup_period_canonical import (
    parse_period_filter_to_year_quarter,
    quarter_key_from_period_start,
)

# --- reason vocabulary (snake_case, po_* prefix — same family as ops residual tags) ---
# Before (ops residual only): po_competes_cases:<ids>, customer_unresolved, involves_survivor
# Match reasons (unchanged): customer_product_crad_in_period, …
REASON_MULTI_BU_SHARED = "po_multi_bu_shared"
REASON_COMPETES_SAME_BU_SAME_PERIOD = "po_competes_same_bu_same_period"
REASON_COMPETES_CROSS_PERIOD = "po_competes_cross_period"
REASON_INDETERMINATE_NO_SHIPMENT = "po_compete_indeterminate_no_shipment"

CompetitionStatus = Literal["not_contested", "contested", "indeterminate"]


@dataclass(frozen=True)
class CompetitionClassification:
    """Result for one po_number_norm claimed by ≥2 cases."""

    po_number_norm: str
    status: CompetitionStatus
    reason: str
    competing_case_ids: tuple[int, ...]
    case_bus: tuple[str, ...]
    ship_bus: tuple[str, ...]
    period_keys: tuple[str, ...]


def case_period_key(
    *,
    inferred_period_start: date | None,
    period_label: str | None,
) -> str | None:
    """Canonical quarter key for competition (``26Q1``). Prefer inferred_period_start."""
    if inferred_period_start is not None:
        return quarter_key_from_period_start(inferred_period_start)
    year, quarter = parse_period_filter_to_year_quarter(period_label)
    if year is not None and quarter is not None:
        return f"{str(year)[-2:]}Q{quarter}"
    return None


def normalize_bu(raw: str | None) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip().upper()
    return s or None


def classify_po_competition(
    *,
    po_number_norm: str,
    claiming_cases: list[dict[str, Any]],
    ship_product_bu: dict[int, str],
    case_product_ids: dict[int, set[int]],
) -> CompetitionClassification:
    """Classify multi-case claims on one PO norm.

    ``claiming_cases`` entries: ``case_id``, ``bu`` (case business_unit / product_line),
    ``period_key`` (from ``case_period_key``).

    ``ship_product_bu``: product_id → BU from ``dim_product.product_line`` for facts on this PO.
    ``case_product_ids``: case_id → lineup product_ids on that case.

    Classes (Warren):
      (a) shipment multi-BU + each case BU matches a shipped BU via product overlap → not_contested
      (b) same BU, same period → contested
      (c) different periods → contested
      (d) no shipment evidence → indeterminate
    """
    case_ids = tuple(sorted({int(c["case_id"]) for c in claiming_cases}))
    bus = tuple(
        sorted(
            {
                b
                for c in claiming_cases
                if (b := normalize_bu(c.get("bu"))) is not None
            }
        )
    )
    period_keys = tuple(
        sorted({pk for c in claiming_cases if (pk := c.get("period_key")) is not None})
    )
    ship_bus = tuple(sorted({normalize_bu(b) for b in ship_product_bu.values() if normalize_bu(b)}))

    if not ship_product_bu:
        return CompetitionClassification(
            po_number_norm=po_number_norm,
            status="indeterminate",
            reason=REASON_INDETERMINATE_NO_SHIPMENT,
            competing_case_ids=case_ids,
            case_bus=bus,
            ship_bus=ship_bus,
            period_keys=period_keys,
        )

    if len(period_keys) > 1:
        return CompetitionClassification(
            po_number_norm=po_number_norm,
            status="contested",
            reason=REASON_COMPETES_CROSS_PERIOD,
            competing_case_ids=case_ids,
            case_bus=bus,
            ship_bus=ship_bus,
            period_keys=period_keys,
        )

    if len(bus) <= 1:
        return CompetitionClassification(
            po_number_norm=po_number_norm,
            status="contested",
            reason=REASON_COMPETES_SAME_BU_SAME_PERIOD,
            competing_case_ids=case_ids,
            case_bus=bus,
            ship_bus=ship_bus,
            period_keys=period_keys,
        )

    # Multi-BU claims: (a) only when shipment shows multiple BUs and each case
    # overlaps shipped products in its own BU.
    if len(ship_bus) >= 2 and _all_cases_match_shipped_bu(
        claiming_cases=claiming_cases,
        ship_product_bu=ship_product_bu,
        case_product_ids=case_product_ids,
    ):
        return CompetitionClassification(
            po_number_norm=po_number_norm,
            status="not_contested",
            reason=REASON_MULTI_BU_SHARED,
            competing_case_ids=case_ids,
            case_bus=bus,
            ship_bus=ship_bus,
            period_keys=period_keys,
        )

    # Same period, multi-BU claims, but shipment does not explain → contested
    return CompetitionClassification(
        po_number_norm=po_number_norm,
        status="contested",
        reason=REASON_COMPETES_SAME_BU_SAME_PERIOD,
        competing_case_ids=case_ids,
        case_bus=bus,
        ship_bus=ship_bus,
        period_keys=period_keys,
    )


def _all_cases_match_shipped_bu(
    *,
    claiming_cases: list[dict[str, Any]],
    ship_product_bu: dict[int, str],
    case_product_ids: dict[int, set[int]],
) -> bool:
    by_case: dict[int, str | None] = {}
    for c in claiming_cases:
        cid = int(c["case_id"])
        by_case[cid] = normalize_bu(c.get("bu"))
    for cid, bu in by_case.items():
        if not bu:
            return False
        products = case_product_ids.get(cid) or set()
        overlap = False
        for pid in products:
            ship_bu = normalize_bu(ship_product_bu.get(pid))
            if ship_bu == bu:
                overlap = True
                break
        if not overlap:
            return False
    return True


def classify_proposals_competition(
    proposals: list[dict[str, Any]],
    *,
    case_meta: dict[int, dict[str, Any]],
    case_product_ids: dict[int, set[int]],
    ship_products_by_po_norm: dict[str, dict[int, str]],
) -> dict[str, CompetitionClassification]:
    """Classify every po_norm claimed by ≥2 proposals. Pure — no DB I/O.

    ``case_meta[case_id]``: ``bu``, ``inferred_period_start``, ``period_label``.
    ``ship_products_by_po_norm[norm]``: product_id → product_line BU.
    """
    by_po: dict[str, list[dict[str, Any]]] = {}
    for p in proposals:
        norm = (p.get("po_number_norm") or "").strip()
        if not norm:
            continue
        by_po.setdefault(norm, []).append(p)

    out: dict[str, CompetitionClassification] = {}
    for norm, props in by_po.items():
        case_ids = {int(p["case_id"]) for p in props}
        if len(case_ids) < 2:
            continue
        claiming: list[dict[str, Any]] = []
        for cid in sorted(case_ids):
            meta = case_meta.get(cid) or {}
            claiming.append(
                {
                    "case_id": cid,
                    "bu": meta.get("bu"),
                    "period_key": case_period_key(
                        inferred_period_start=meta.get("inferred_period_start"),
                        period_label=meta.get("period_label"),
                    ),
                }
            )
        out[norm] = classify_po_competition(
            po_number_norm=norm,
            claiming_cases=claiming,
            ship_product_bu=ship_products_by_po_norm.get(norm) or {},
            case_product_ids=case_product_ids,
        )
    return out


def annotate_proposals_with_competition(
    proposals: list[dict[str, Any]],
    classifications: dict[str, CompetitionClassification],
) -> None:
    """Mutate proposals in place with competition annotation. FLAG ≠ BLOCK."""
    for p in proposals:
        norm = (p.get("po_number_norm") or "").strip()
        cls = classifications.get(norm)
        if cls is None:
            p["competition"] = None
            continue
        p["competition"] = {
            "status": cls.status,
            "reason": cls.reason,
            "competing_case_ids": list(cls.competing_case_ids),
            "case_bus": list(cls.case_bus),
            "ship_bus": list(cls.ship_bus),
            "period_keys": list(cls.period_keys),
            # Contested is annotation only — never a link/apply gate.
            "blocks_apply": False,
        }


def is_contested(competition: dict[str, Any] | None) -> bool:
    return bool(competition and competition.get("status") == "contested")
