"""DSI product resolution: shipment-evidence tie-break (componentized, removable).

Uses resolved ``shipment_evidence_line`` rows (same month + distributor + token) to pick a single
``dim_product.id`` when Product Master tier resolution is ambiguous. Does not modify shipment import.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy.orm import Session


@dataclass(frozen=True)
class CandidateShipmentEvidence:
    """Parsed from ``ImportEntityMappingCandidate.context`` (set during DSI validate aggregation)."""

    dominant_evidence_month: str | None
    dominant_unresolved_distributor_id: int | None
    stored_distinct_product_ids: tuple[int, ...]


def parse_candidate_shipment_evidence(ctx: dict[str, Any] | None) -> CandidateShipmentEvidence:
    if not ctx:
        return CandidateShipmentEvidence(None, None, ())
    dom = ctx.get("dominant_unresolved_distributor_id")
    try:
        dist_id = int(dom) if dom is not None else None
    except (TypeError, ValueError):
        dist_id = None
    month = ctx.get("dominant_evidence_month")
    em = str(month).strip()[:7] if isinstance(month, str) and month.strip() else None
    raw_ids = ctx.get("shipment_distinct_product_ids")
    ids: list[int] = []
    if isinstance(raw_ids, list):
        for x in raw_ids:
            try:
                v = int(x)
            except (TypeError, ValueError):
                continue
            if v > 0:
                ids.append(v)
    return CandidateShipmentEvidence(em, dist_id, tuple(sorted(set(ids))))


def evidence_date_from_month(evidence_month: str | None) -> date | None:
    if not evidence_month or len(evidence_month) < 7:
        return None
    try:
        y = int(evidence_month[:4])
        m = int(evidence_month[5:7])
        return date(y, m, 1)
    except (TypeError, ValueError):
        return None


def intersect_eligible_with_shipment_ids(
    eligible_product_ids: list[int],
    shipment_product_ids: tuple[int, ...] | list[int],
) -> int | None:
    """Return sole product id when intersection is exactly one, else None."""
    if not eligible_product_ids or not shipment_product_ids:
        return None
    elig = {int(x) for x in eligible_product_ids if int(x) > 0}
    ship = {int(x) for x in shipment_product_ids if int(x) > 0}
    inter = elig & ship
    if len(inter) == 1:
        return int(next(iter(inter)))
    return None


def try_shipment_tiebreak_product_id(
    session: Session | None,
    *,
    eligible_product_ids: list[int],
    raw_token: str | None,
    distributor_id: int | None,
    evidence_date: date | None,
    stored_distinct_product_ids: tuple[int, ...] = (),
    corr_cache: Any = None,
) -> tuple[int | None, str | None]:
    """Pick one PM id via stored validate-time ids first, then live shipment corroboration lookup.

    Returns ``(product_id, tiebreak_source)`` where source is ``stored_context``,
    ``shipment_disambiguate``, or None.
    """
    pick = intersect_eligible_with_shipment_ids(eligible_product_ids, stored_distinct_product_ids)
    if pick is not None:
        return pick, "stored_context"

    if session is None and corr_cache is None:
        return None, None
    if distributor_id is None or evidence_date is None or not eligible_product_ids:
        return None, None

    from app.services.imports.distributor_sales_inventory import _shipment_disambiguate_product_id

    live_pick, scope = _shipment_disambiguate_product_id(
        session,
        distributor_id,
        evidence_date,
        raw_token,
        eligible_product_ids,
        corr_cache=corr_cache,
    )
    if live_pick is not None:
        src = "shipment_disambiguate"
        if scope == "cross_distributor":
            src = f"{src}_cross_distributor"
        return int(live_pick), src
    return None, None


def corroboration_chip_label_from_context(ctx: dict[str, Any] | None) -> str | None:
    """Human-facing label: distinguish tie-break ready vs signal-only hits."""
    if not ctx:
        return None
    tie = ctx.get("shipment_product_tiebreak")
    if isinstance(tie, dict) and tie.get("resolved_product_id"):
        return "Shipment tie-break (1 product)"
    markers = ctx.get("corroboration_markers")
    if isinstance(markers, list) and "shipment_evidence_product" in markers:
        sec = ctx.get("shipment_evidence_corroboration")
        if isinstance(sec, dict) and sec.get("signal_only"):
            n = sec.get("best_match_count")
            if isinstance(n, int) and n > 0:
                return f"Shipment lines found ({n})"
            return "Shipment lines found"
    return None
