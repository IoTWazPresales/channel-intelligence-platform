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


def _parse_int_list(ctx: dict[str, Any], key: str, *, limit: int = 8) -> list[int]:
    raw = ctx.get(key)
    out: list[int] = []
    if not isinstance(raw, list):
        return out
    for x in raw:
        try:
            v = int(x)
        except (TypeError, ValueError):
            continue
        if v > 0 and v not in out:
            out.append(v)
        if len(out) >= limit:
            break
    return out


def _parse_month_list(ctx: dict[str, Any], *, limit: int = 6) -> list[str]:
    months: list[str] = []
    for key in ("dominant_evidence_month",):
        m = ctx.get(key)
        if isinstance(m, str) and m.strip():
            em = m.strip()[:7]
            if em not in months:
                months.append(em)
    for counts_key in ("shipment_evidence_month_counts", "dsi_evidence_month_counts"):
        mc = ctx.get(counts_key)
        if isinstance(mc, dict):
            for k in sorted(mc.keys(), key=lambda x: int(mc.get(x) or 0), reverse=True):
                if isinstance(k, str) and k.strip():
                    em = k.strip()[:7]
                    if em not in months:
                        months.append(em)
                if len(months) >= limit:
                    break
        if len(months) >= limit:
            break
    return months[:limit]


def build_tiebreak_scope_attempts(
    ctx: dict[str, Any] | None,
    *,
    normalized_key: str | None = None,
    staging_scopes: dict[str, list[tuple[int, str]]] | None = None,
    fallback_distributor_id: int | None = None,
    fallback_evidence_date: date | None = None,
    max_attempts: int = 24,
) -> list[tuple[int, date]]:
    """Distinct (distributor_id, evidence_date) pairs to try for live shipment corroboration."""
    if not ctx and fallback_distributor_id is None and not staging_scopes:
        if fallback_distributor_id is not None and fallback_evidence_date is not None:
            return [(int(fallback_distributor_id), fallback_evidence_date)]
        return []

    c = ctx or {}
    dist_ids = _parse_int_list(c, "unresolved_distributor_ids")
    dom = c.get("dominant_unresolved_distributor_id")
    if dom is not None:
        try:
            dv = int(dom)
            if dv > 0 and dv not in dist_ids:
                dist_ids.insert(0, dv)
        except (TypeError, ValueError):
            pass
    if fallback_distributor_id is not None:
        fd = int(fallback_distributor_id)
        if fd > 0 and fd not in dist_ids:
            dist_ids.insert(0, fd)

    nk = (normalized_key or c.get("normalized_key") or "").strip().lower()
    if staging_scopes and nk:
        for dist_id, em in staging_scopes.get(nk, []):
            if dist_id > 0 and dist_id not in dist_ids:
                dist_ids.append(dist_id)

    months = _parse_month_list(c)
    if fallback_evidence_date is not None:
        em = fallback_evidence_date.strftime("%Y-%m")
        if em not in months:
            months.insert(0, em)

    if staging_scopes and nk:
        for dist_id, em in staging_scopes.get(nk, []):
            if em not in months:
                months.append(em)

    if not dist_ids or not months:
        if fallback_distributor_id is not None and fallback_evidence_date is not None:
            return [(int(fallback_distributor_id), fallback_evidence_date)]
        return []

    attempts: list[tuple[int, date]] = []
    seen: set[tuple[int, str]] = set()
    for dist_id in dist_ids:
        for em in months:
            ev = evidence_date_from_month(em)
            if ev is None:
                continue
            key = (dist_id, em)
            if key in seen:
                continue
            seen.add(key)
            attempts.append((dist_id, ev))
            if len(attempts) >= max_attempts:
                return attempts
    return attempts


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
    candidate_context: dict[str, Any] | None = None,
    normalized_key: str | None = None,
    staging_scopes: dict[str, list[tuple[int, str]]] | None = None,
    global_product_identity: Any = None,
) -> tuple[int | None, str | None]:
    """Pick one PM id via stored validate-time ids first, then scoped corroboration, then global identity.

    Returns ``(product_id, tiebreak_source)`` where source is ``stored_context``,
    ``shipment_disambiguate`` (variants), ``shipment_global_identity``, or None.
    """
    pick = intersect_eligible_with_shipment_ids(eligible_product_ids, stored_distinct_product_ids)
    if pick is not None:
        return pick, "stored_context"

    if not eligible_product_ids:
        return None, None

    if session is not None or corr_cache is not None:
        from app.services.imports.distributor_sales_inventory import _shipment_disambiguate_product_id

        scope_attempts = build_tiebreak_scope_attempts(
            candidate_context,
            normalized_key=normalized_key,
            staging_scopes=staging_scopes,
            fallback_distributor_id=distributor_id,
            fallback_evidence_date=evidence_date,
        )
        if not scope_attempts and distributor_id is not None and evidence_date is not None:
            scope_attempts = [(int(distributor_id), evidence_date)]

        unanimous: set[int] = set()
        last_scope: str | None = None
        for dist_id, ev_date in scope_attempts:
            live_pick, ship_scope = _shipment_disambiguate_product_id(
                session,
                dist_id,
                ev_date,
                raw_token,
                eligible_product_ids,
                corr_cache=corr_cache,
            )
            if live_pick is None:
                continue
            unanimous.add(int(live_pick))
            last_scope = ship_scope
            if len(unanimous) > 1:
                return None, None

        if len(unanimous) == 1:
            src = "shipment_disambiguate"
            if last_scope == "cross_distributor":
                src = f"{src}_cross_distributor"
            if len(scope_attempts) > 1:
                src = f"{src}_multi_scope"
            return int(next(iter(unanimous))), src

    if global_product_identity is not None:
        global_ids = global_product_identity.distinct_product_ids_for_token(raw_token)
        global_pick = intersect_eligible_with_shipment_ids(eligible_product_ids, global_ids)
        if global_pick is not None:
            return global_pick, "shipment_global_identity"

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
