"""Lineup distributor attribution — propose / confirm / conflict (Unit 6f / D-040).

Token (D-038) writes distributor_id as a working FK with status token_proposed.
Shipment confirmer upgrades to shipment_confirmed, leaves proposed when multi/no
ships, or sets conflict when ships exist and the proposed dist is absent.
Never auto-clears distributor_id. No DAP. No fuzzy match. No auto-create dims.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.commercial_lineup import (
    CommercialLineupCase,
    CommercialLineupLine,
    DISTRIBUTOR_ATTRIBUTION_STATUSES,
)
from app.models.dimensions import DimCustomer, DimDistributor
from app.models.facts import FactInboundShipment
from app.models.import_distributor_si import CustomerSourceTokenAlias
from app.services.commercial_planner.lineup_customer_alias_resolution import (
    resolve_lineup_customer_id_from_token,
)
from app.services.commercial_planner.lineup_customer_token_stamp import (
    _isolated_product_ids,
    _load_distributor_match_maps,
)
from app.services.commercial_planner.lineup_distributor_token import match_distributor_token
from app.services.commercial_planner.lineup_period_canonical import (
    quarter_bounds_from_period_start,
)
from app.services.commercial_planner.lineup_po_auto_link import (
    evidence_date_for_period_match,
)
from app.services.commercial_planner.open_channel_customer import get_open_channel_customer_id
from app.services.imports.distributor_sales_inventory import _norm_key
from app.services.imports.shipment_evidence_resolution_plan import (
    build_unique_approved_customer_alias_id_by_token,
)
from app.services.steward_audit import record_steward_audit

STATUS_TOKEN_PROPOSED = "token_proposed"
STATUS_STEWARD_SET = "steward_set"
STATUS_SHIPMENT_CONFIRMED = "shipment_confirmed"
STATUS_CONFLICT = "conflict"


class DistributorAttributionError(Exception):
    """Validation / missing target errors for attribution steward actions."""


@dataclass(frozen=True)
class _ShipHit:
    product_id: int
    distributor_id: int
    quantity: float | None
    shipment_id: int


def _qty_key(q: float | Decimal | None) -> float | None:
    if q is None:
        return None
    return float(q)


async def _cases_by_id(db: AsyncSession, case_ids: set[int]) -> dict[int, CommercialLineupCase]:
    if not case_ids:
        return {}
    rows = (
        await db.execute(
            select(CommercialLineupCase).where(CommercialLineupCase.id.in_(list(case_ids)))
        )
    ).scalars().all()
    return {int(c.id): c for c in rows}


def _period_start_for_line(
    ln: CommercialLineupLine, cases: dict[int, CommercialLineupCase]
) -> date | None:
    case = cases.get(int(ln.case_id))
    if case is None:
        return None
    return case.inferred_period_start


async def _eligible_ships_for_products(
    db: AsyncSession,
    *,
    product_ids: set[int],
    period_starts: set[date],
) -> list[_ShipHit]:
    if not product_ids or not period_starts:
        return []
    rows = (
        await db.execute(
            select(
                FactInboundShipment.id,
                FactInboundShipment.product_id,
                FactInboundShipment.resolved_distributor_id,
                FactInboundShipment.quantity,
                FactInboundShipment.crad_date,
                FactInboundShipment.schedule_ship_date,
                FactInboundShipment.ship_confirm_date,
            ).where(
                FactInboundShipment.product_id.in_(list(product_ids)),
                FactInboundShipment.resolved_distributor_id.isnot(None),
            )
        )
    ).all()
    windows = [quarter_bounds_from_period_start(ps) for ps in period_starts]
    hits: list[_ShipHit] = []
    for sid, pid, dist_id, qty, crad, sched, ship_c in rows:
        ev, _src = evidence_date_for_period_match(
            crad_date=crad, schedule_ship_date=sched, ship_confirm_date=ship_c
        )
        if ev is None:
            continue
        if not any(start <= ev < end for start, end in windows):
            continue
        hits.append(
            _ShipHit(
                product_id=int(pid),
                distributor_id=int(dist_id),
                quantity=_qty_key(qty),
                shipment_id=int(sid),
            )
        )
    return hits


def _evaluate_token_group(
    *,
    token_lines: list[CommercialLineupLine],
    ships: list[_ShipHit],
    isolated_products: set[int],
) -> dict[str, Any]:
    line_qty_by_product: dict[int, set[float]] = defaultdict(set)
    for ln in token_lines:
        if ln.product_id is None:
            continue
        pid = int(ln.product_id)
        if pid not in isolated_products:
            continue
        q = _qty_key(ln.quantity_units)
        if q is not None and q != 0:
            line_qty_by_product[pid].add(q)

    eligible = [s for s in ships if s.product_id in isolated_products]
    dists = {s.distributor_id for s in eligible}
    exact_qty_ships = [
        s
        for s in eligible
        if s.quantity is not None and s.quantity in line_qty_by_product.get(s.product_id, set())
    ]
    exact_dists = {s.distributor_id for s in exact_qty_ships}
    sole_exact: int | None = next(iter(exact_dists)) if len(exact_dists) == 1 else None

    per_line: list[dict[str, Any]] = []
    for ln in token_lines:
        proposed = int(ln.distributor_id) if ln.distributor_id is not None else None
        current = (ln.distributor_attribution_status or "").strip() or None
        action = "noop"
        new_status = current

        if not eligible:
            action = "no_ships"
        elif sole_exact is not None:
            if proposed is None:
                action = "offer_accept"
            elif proposed == sole_exact:
                if current != STATUS_SHIPMENT_CONFIRMED:
                    action = "confirm"
                    new_status = STATUS_SHIPMENT_CONFIRMED
                else:
                    action = "already_confirmed"
            else:
                action = "conflict"
                new_status = STATUS_CONFLICT
        elif proposed is not None and proposed not in dists:
            action = "conflict"
            new_status = STATUS_CONFLICT
        elif proposed is not None and proposed in dists:
            if current == STATUS_CONFLICT:
                action = "leave_conflict"
            elif current is None:
                new_status = STATUS_TOKEN_PROPOSED
                action = "backfill_proposed"
            else:
                action = "leave_proposed"
        else:
            action = "unproven_multi"

        per_line.append(
            {
                "line_id": int(ln.id),
                "case_id": int(ln.case_id),
                "product_id": int(ln.product_id) if ln.product_id is not None else None,
                "quantity_units": _qty_key(ln.quantity_units),
                "distributor_id": proposed,
                "current_status": current,
                "action": action,
                "new_status": new_status,
            }
        )

    offer = None
    if sole_exact is not None:
        offer = {
            "distributor_id": sole_exact,
            "reason": "sole_resolved_distributor_exact_qty",
            "exact_qty_ship_count": len(exact_qty_ships),
            "eligible_dist_count": len(dists),
        }

    return {
        "eligible_distributor_ids": sorted(dists),
        "exact_qty_distributor_ids": sorted(exact_dists),
        "sole_exact_distributor_id": sole_exact,
        "ship_corroboration_offer": offer,
        "per_line": per_line,
        "eligible_ship_count": len(eligible),
    }


async def preview_distributor_confirmer(
    db: AsyncSession,
    *,
    norm_tokens: list[str] | None = None,
    case_ids: list[int] | None = None,
    limit_tokens: int = 200,
) -> dict[str, Any]:
    q = select(CommercialLineupLine).where(
        CommercialLineupLine.customer_token.isnot(None),
        CommercialLineupLine.customer_token != "",
    )
    if case_ids:
        q = q.where(CommercialLineupLine.case_id.in_([int(x) for x in case_ids]))
    lines = list((await db.execute(q)).scalars().all())

    by_token: dict[str, list[CommercialLineupLine]] = defaultdict(list)
    token_filter = {_norm_key(t) for t in norm_tokens} if norm_tokens is not None else None
    for ln in lines:
        nt = _norm_key(ln.customer_token or "")
        if not nt:
            continue
        if token_filter is not None and nt not in token_filter:
            continue
        by_token[nt].append(ln)

    tokens_sorted = sorted(by_token.keys())[: max(1, min(int(limit_tokens), 500))]
    case_ids_all = {int(ln.case_id) for t in tokens_sorted for ln in by_token[t]}
    cases = await _cases_by_id(db, case_ids_all)

    case_lines_by_case: dict[int, list[CommercialLineupLine]] = defaultdict(list)
    if case_ids_all:
        for ln in (
            await db.execute(
                select(CommercialLineupLine).where(
                    CommercialLineupLine.case_id.in_(list(case_ids_all)),
                    CommercialLineupLine.customer_token.isnot(None),
                )
            )
        ).scalars().all():
            case_lines_by_case[int(ln.case_id)].append(ln)

    items: list[dict[str, Any]] = []
    summary: dict[str, int] = defaultdict(int)
    for t in tokens_sorted:
        tlines = by_token[t]
        iso = _isolated_product_ids(tlines, case_lines_by_case=case_lines_by_case)
        t_periods = {
            ps
            for ln in tlines
            if (ps := _period_start_for_line(ln, cases)) is not None
        }
        t_ships = await _eligible_ships_for_products(
            db, product_ids=iso, period_starts=t_periods
        )
        ev = _evaluate_token_group(
            token_lines=tlines, ships=t_ships, isolated_products=iso
        )
        for pl in ev["per_line"]:
            summary[pl["action"]] += 1
        items.append({"norm_token": t, "line_count": len(tlines), **ev})

    return {
        "items": items,
        "token_count": len(items),
        "action_counts": dict(summary),
        "dry_run": True,
        "data_unavailable": False,
    }


async def apply_distributor_confirmer(
    db: AsyncSession,
    user: dict | None,
    *,
    norm_tokens: list[str] | None = None,
    case_ids: list[int] | None = None,
    commit: bool = True,
) -> dict[str, Any]:
    preview = await preview_distributor_confirmer(
        db, norm_tokens=norm_tokens, case_ids=case_ids, limit_tokens=500
    )
    line_ids = [
        int(pl["line_id"])
        for it in preview["items"]
        for pl in it["per_line"]
        if pl["action"] in {"confirm", "conflict", "backfill_proposed"}
    ]
    if not line_ids:
        return {
            "updated_count": 0,
            "per_line": [],
            "action_counts": preview["action_counts"],
            "dry_run": False,
        }

    lines = {
        int(ln.id): ln
        for ln in (
            await db.execute(
                select(CommercialLineupLine).where(CommercialLineupLine.id.in_(line_ids))
            )
        ).scalars().all()
    }
    updates: list[dict[str, Any]] = []
    for it in preview["items"]:
        for pl in it["per_line"]:
            if pl["action"] not in {"confirm", "conflict", "backfill_proposed"}:
                continue
            ln = lines.get(int(pl["line_id"]))
            if ln is None:
                continue
            prior = ln.distributor_attribution_status
            new_s = pl["new_status"]
            if new_s not in DISTRIBUTOR_ATTRIBUTION_STATUSES:
                continue
            ln.distributor_attribution_status = new_s
            updates.append(
                {
                    "line_id": int(ln.id),
                    "norm_token": it["norm_token"],
                    "action": pl["action"],
                    "prior_status": prior,
                    "new_status": new_s,
                    "distributor_id": int(ln.distributor_id) if ln.distributor_id else None,
                }
            )

    await record_steward_audit(
        db,
        user,
        action="lineup_distributor_attribution_confirm",
        importer="commercial_planner",
        entity_type="distributor_attribution",
        entity_token=None,
        target_dim="commercial_lineup_line",
        target_id=None,
        payload={
            "updated_count": len(updates),
            "per_line": updates[:500],
            "norm_tokens": norm_tokens,
            "case_ids": case_ids,
        },
        commit=False,
    )
    if commit:
        await db.commit()
    else:
        await db.flush()
    return {
        "updated_count": len(updates),
        "per_line": updates,
        "action_counts": preview["action_counts"],
        "dry_run": False,
    }


async def ship_corroboration_offer_for_token(
    db: AsyncSession, *, norm_token: str
) -> dict[str, Any] | None:
    nt = _norm_key(norm_token)
    if not nt:
        return None
    preview = await preview_distributor_confirmer(db, norm_tokens=[nt], limit_tokens=1)
    if not preview["items"]:
        return None
    return preview["items"][0].get("ship_corroboration_offer")


async def accept_ship_corroborated_distributor(
    db: AsyncSession,
    user: dict | None,
    *,
    norm_token: str,
    distributor_id: int,
    reason: str,
    commit: bool = True,
) -> dict[str, Any]:
    nt = _norm_key(norm_token)
    reason_s = (reason or "").strip()
    if not nt or not reason_s:
        raise DistributorAttributionError("norm_token and reason required")

    dist = await db.get(DimDistributor, int(distributor_id))
    if dist is None:
        raise DistributorAttributionError(f"distributor {distributor_id} does not exist")

    offer = await ship_corroboration_offer_for_token(db, norm_token=nt)
    if offer is None or int(offer["distributor_id"]) != int(distributor_id):
        raise DistributorAttributionError(
            "distributor_id does not match current sole-exact ship corroboration offer"
        )

    oc_id = await get_open_channel_customer_id(db)
    if oc_id is None:
        raise DistributorAttributionError("OPEN_CHANNEL customer missing")

    lines = list(
        (
            await db.execute(
                select(CommercialLineupLine).where(CommercialLineupLine.customer_token.isnot(None))
            )
        ).scalars().all()
    )
    token_lines = [ln for ln in lines if _norm_key(ln.customer_token or "") == nt]
    if not token_lines:
        raise DistributorAttributionError(f"no lineup lines for token {nt!r}")

    existing = (
        await db.execute(
            select(CustomerSourceTokenAlias).where(
                CustomerSourceTokenAlias.normalized_token == nt,
                CustomerSourceTokenAlias.status == "approved",
                CustomerSourceTokenAlias.source_definition_id.is_(None),
                CustomerSourceTokenAlias.distributor_id.is_(None),
            )
        )
    ).scalars().first()
    raw_sample = next((ln.customer_token for ln in token_lines if ln.customer_token), nt)
    if existing is None:
        alias = CustomerSourceTokenAlias(
            customer_id=int(oc_id),
            source_definition_id=None,
            distributor_id=None,
            raw_token=str(raw_sample)[:512],
            normalized_token=nt[:512],
            dealer_group_token=None,
            status="approved",
            notes=f"ship_corroborated_accept:{reason_s}"[:1024],
            created_from_import_job_id=None,
            import_entity_mapping_candidate_id=None,
        )
        db.add(alias)
        await db.flush()
    else:
        alias = existing
        if int(alias.customer_id) != int(oc_id):
            alias.customer_id = int(oc_id)
        await db.flush()

    all_rows = list(
        (
            await db.execute(
                select(
                    CustomerSourceTokenAlias.normalized_token,
                    CustomerSourceTokenAlias.customer_id,
                    CustomerSourceTokenAlias.source_definition_id,
                ).where(CustomerSourceTokenAlias.status == "approved")
            )
        ).all()
    )
    alias_map = build_unique_approved_customer_alias_id_by_token(all_rows)
    alias_map[nt] = int(oc_id)
    cust_rows = list((await db.execute(select(DimCustomer))).scalars().all())
    customers_by_id = {int(c.id): c for c in cust_rows}
    customer_map: dict[str, DimCustomer] = {}
    for c in cust_rows:
        if c.name:
            customer_map[c.name.strip().lower()] = c
        if c.code:
            customer_map[c.code.strip().lower()] = c

    per_line: list[dict[str, Any]] = []
    prior_customer_ids: dict[str, int | None] = {}
    prior_distributor_ids: dict[str, int | None] = {}
    for ln in token_lines:
        prior_c = int(ln.customer_id) if ln.customer_id is not None else None
        prior_d = int(ln.distributor_id) if ln.distributor_id is not None else None
        resolved = resolve_lineup_customer_id_from_token(
            ln.customer_token,
            customer_map=customer_map,
            customer_alias_map=alias_map,
            customers_by_id=customers_by_id,
        )
        if resolved is None:
            continue
        ln.customer_id = int(resolved)
        ln.distributor_id = int(distributor_id)
        ln.distributor_attribution_status = STATUS_STEWARD_SET
        diag = list(ln.diagnostic_codes or [])
        ln.diagnostic_codes = [d for d in diag if d != "unknown_customer"] or None
        per_line.append(
            {
                "line_id": int(ln.id),
                "prior_customer_id": prior_c,
                "prior_distributor_id": prior_d,
                "distributor_id": int(distributor_id),
            }
        )
        prior_customer_ids[str(ln.id)] = prior_c
        prior_distributor_ids[str(ln.id)] = prior_d

    await record_steward_audit(
        db,
        user,
        action="lineup_ship_corroborated_distributor_accept",
        importer="commercial_planner",
        entity_type="customer_token",
        entity_token=nt,
        target_dim="dim_distributor",
        target_id=int(distributor_id),
        payload={
            "norm_token": nt,
            "reason": reason_s,
            "alias_id": int(alias.id),
            "open_channel_customer_id": int(oc_id),
            "distributor_id": int(distributor_id),
            "offer": offer,
            "prior_customer_ids": prior_customer_ids,
            "prior_distributor_ids": prior_distributor_ids,
            "line_ids": [p["line_id"] for p in per_line],
            "status": STATUS_STEWARD_SET,
        },
        commit=False,
    )
    if commit:
        await db.commit()
    else:
        await db.flush()
    return {
        "norm_token": nt,
        "alias_id": int(alias.id),
        "distributor_id": int(distributor_id),
        "stamped_count": len(per_line),
        "status": STATUS_STEWARD_SET,
        "per_line": per_line,
    }


async def soft_clear_line_distributor(
    db: AsyncSession,
    user: dict | None,
    *,
    line_ids: list[int],
    reason: str,
    commit: bool = True,
) -> dict[str, Any]:
    reason_s = (reason or "").strip()
    if not reason_s:
        raise DistributorAttributionError("reason required")
    ids = [int(x) for x in line_ids]
    if not ids:
        raise DistributorAttributionError("line_ids required")

    lines = list(
        (
            await db.execute(
                select(CommercialLineupLine).where(CommercialLineupLine.id.in_(ids))
            )
        ).scalars().all()
    )
    cleared: list[dict[str, Any]] = []
    for ln in lines:
        prior = int(ln.distributor_id) if ln.distributor_id is not None else None
        prior_status = ln.distributor_attribution_status
        if prior is None and not prior_status:
            continue
        ln.distributor_id = None
        ln.distributor_attribution_status = None
        cleared.append(
            {
                "line_id": int(ln.id),
                "prior_distributor_id": prior,
                "prior_status": prior_status,
            }
        )

    await record_steward_audit(
        db,
        user,
        action="lineup_distributor_soft_clear",
        importer="commercial_planner",
        entity_type="distributor_attribution",
        entity_token=None,
        target_dim="commercial_lineup_line",
        target_id=None,
        payload={"reason": reason_s, "cleared": cleared},
        commit=False,
    )
    if commit:
        await db.commit()
    else:
        await db.flush()
    return {"cleared_count": len(cleared), "cleared": cleared}


async def override_distributor_attribution(
    db: AsyncSession,
    user: dict | None,
    *,
    line_ids: list[int],
    distributor_id: int,
    reason: str,
    commit: bool = True,
) -> dict[str, Any]:
    reason_s = (reason or "").strip()
    if not reason_s:
        raise DistributorAttributionError("reason required")
    dist = await db.get(DimDistributor, int(distributor_id))
    if dist is None:
        raise DistributorAttributionError(f"distributor {distributor_id} does not exist")

    ids = [int(x) for x in line_ids]
    lines = list(
        (
            await db.execute(
                select(CommercialLineupLine).where(CommercialLineupLine.id.in_(ids))
            )
        ).scalars().all()
    )
    updated: list[dict[str, Any]] = []
    for ln in lines:
        prior = int(ln.distributor_id) if ln.distributor_id is not None else None
        prior_status = ln.distributor_attribution_status
        ln.distributor_id = int(distributor_id)
        ln.distributor_attribution_status = STATUS_STEWARD_SET
        updated.append(
            {
                "line_id": int(ln.id),
                "prior_distributor_id": prior,
                "prior_status": prior_status,
                "distributor_id": int(distributor_id),
            }
        )

    await record_steward_audit(
        db,
        user,
        action="lineup_distributor_attribution_override",
        importer="commercial_planner",
        entity_type="distributor_attribution",
        entity_token=None,
        target_dim="dim_distributor",
        target_id=int(distributor_id),
        payload={"reason": reason_s, "updated": updated},
        commit=False,
    )
    if commit:
        await db.commit()
    else:
        await db.flush()
    return {
        "updated_count": len(updated),
        "distributor_id": int(distributor_id),
        "status": STATUS_STEWARD_SET,
        "updated": updated,
    }


async def list_distributor_attribution_review(
    db: AsyncSession,
    *,
    limit: int = 200,
    statuses: list[str] | None = None,
) -> dict[str, Any]:
    want = statuses or [STATUS_TOKEN_PROPOSED, STATUS_CONFLICT]
    want = [s for s in want if s in DISTRIBUTOR_ATTRIBUTION_STATUSES]
    # Status counts across all matching rows (not just the limited page)
    count_rows = (
        await db.execute(
            select(
                CommercialLineupLine.distributor_attribution_status,
                func.count(),
            )
            .where(CommercialLineupLine.distributor_attribution_status.in_(want))
            .group_by(CommercialLineupLine.distributor_attribution_status)
        )
    ).all()
    counts: dict[str, int] = defaultdict(int)
    for st, n in count_rows:
        counts[str(st)] = int(n)
        counts["all"] += int(n)

    q = (
        select(CommercialLineupLine, CommercialLineupCase)
        .join(CommercialLineupCase, CommercialLineupCase.id == CommercialLineupLine.case_id)
        .where(CommercialLineupLine.distributor_attribution_status.in_(want))
        .order_by(CommercialLineupLine.id.desc())
        .limit(max(1, min(int(limit), 500)))
    )
    rows = (await db.execute(q)).all()
    dist_ids = {int(ln.distributor_id) for ln, _c in rows if ln.distributor_id is not None}
    labels: dict[int, str] = {}
    if dist_ids:
        for d in (
            await db.execute(select(DimDistributor).where(DimDistributor.id.in_(list(dist_ids))))
        ).scalars().all():
            labels[int(d.id)] = f"{d.name or d.code or d.id} (id {d.id})"

    items = []
    for ln, case in rows:
        st = ln.distributor_attribution_status or ""
        items.append(
            {
                "line_id": int(ln.id),
                "case_id": int(ln.case_id),
                "period_label": case.period_label,
                "customer_token": ln.customer_token,
                "norm_token": _norm_key(ln.customer_token or ""),
                "customer_id": int(ln.customer_id) if ln.customer_id else None,
                "distributor_id": int(ln.distributor_id) if ln.distributor_id else None,
                "distributor_label": labels.get(int(ln.distributor_id)) if ln.distributor_id else None,
                "distributor_attribution_status": st,
                "product_id": int(ln.product_id) if ln.product_id else None,
                "quantity_units": _qty_key(ln.quantity_units),
            }
        )
    return {
        "items": items,
        "total": int(counts.get("all", 0)),
        "status_counts": dict(counts),
        "data_unavailable": False,
    }


async def backfill_token_proposed_status(
    db: AsyncSession,
    user: dict | None,
    *,
    commit: bool = True,
) -> dict[str, Any]:
    lines = list(
        (
            await db.execute(
                select(CommercialLineupLine).where(
                    CommercialLineupLine.distributor_id.isnot(None),
                    CommercialLineupLine.distributor_attribution_status.is_(None),
                )
            )
        ).scalars().all()
    )
    updated = 0
    for ln in lines:
        ln.distributor_attribution_status = STATUS_TOKEN_PROPOSED
        updated += 1

    await record_steward_audit(
        db,
        user,
        action="lineup_distributor_attribution_backfill",
        importer="commercial_planner",
        entity_type="distributor_attribution",
        entity_token=None,
        target_dim="commercial_lineup_line",
        target_id=None,
        payload={"updated_count": updated},
        commit=False,
    )
    if commit:
        await db.commit()
    else:
        await db.flush()
    return {"updated_count": updated}
