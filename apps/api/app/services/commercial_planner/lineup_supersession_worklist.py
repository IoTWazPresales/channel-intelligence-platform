"""Read-only steward worklist for active lineup supersession collisions."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.commercial_lineup import CommercialLineupCase, CommercialLineupLine
from app.models.dimensions import DimCustomer
from app.services.commercial_planner.lineup_period_canonical import (
    display_period_label_from_period_start,
    is_active_lineup_case,
    quarter_key_from_period_start,
    supersession_group_key_from_period_start,
)
from app.services.imports.distributor_sales_inventory import _norm_key


async def preview_active_supersession_collisions_async(db: AsyncSession) -> list[dict[str, Any]]:
    cases = list((await db.execute(select(CommercialLineupCase))).scalars().all())
    lines = list((await db.execute(select(CommercialLineupLine))).scalars().all())
    return _build_collision_worklist(cases, lines)


def preview_active_supersession_collisions_sync(db: Session) -> list[dict[str, Any]]:
    cases = list(db.scalars(select(CommercialLineupCase)).all())
    lines = list(db.scalars(select(CommercialLineupLine)).all())
    return _build_collision_worklist(cases, lines)


def _build_collision_worklist(
    cases: list[CommercialLineupCase],
    lines: list[CommercialLineupLine],
) -> list[dict[str, Any]]:
    active_by_id = {int(c.id): c for c in cases if is_active_lineup_case(c)}
    cust_by_case: dict[int, set[int]] = defaultdict(set)
    for ln in lines:
        if ln.customer_id is None:
            continue
        cid = int(ln.case_id)
        if cid in active_by_id:
            cust_by_case[cid].add(int(ln.customer_id))

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen_case_per_group: dict[str, set[int]] = defaultdict(set)

    for case_id, case in active_by_id.items():
        if case.inferred_period_start is None:
            continue
        bu = (case.business_unit or case.product_line or "unknown").strip().upper()
        for customer_id in cust_by_case.get(case_id, set()):
            gkey = supersession_group_key_from_period_start(
                case.inferred_period_start,
                customer_id=customer_id,
                customer_token=None,
                business_unit=bu,
                normalize_customer_token=_norm_key,
            )
            if case_id in seen_case_per_group[gkey]:
                continue
            seen_case_per_group[gkey].add(case_id)
            groups[gkey].append(
                {
                    "case_id": case_id,
                    "period_start": case.inferred_period_start.isoformat(),
                    "quarter_key": quarter_key_from_period_start(case.inferred_period_start),
                    "display_period_label": display_period_label_from_period_start(case.inferred_period_start),
                    "period_label": case.period_label,
                    "customer_id": customer_id,
                    "business_unit": bu,
                    "file_name": case.file_name,
                    "commercial_status": case.commercial_status,
                }
            )

    out: list[dict[str, Any]] = []
    for gkey, members in groups.items():
        if len(members) < 2:
            continue
        ordered = sorted(members, key=lambda m: (m["case_id"], m["file_name"] or ""))
        out.append(
            {
                "supersession_group_key": gkey,
                "member_count": len(ordered),
                "members": ordered,
            }
        )
    out.sort(key=lambda g: (-int(g["member_count"]), g["supersession_group_key"]))
    return out


async def enrich_collision_worklist_customer_names(
    db: AsyncSession, worklist: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    cust_ids = sorted(
        {
            int(m["customer_id"])
            for g in worklist
            for m in g.get("members", [])
            if m.get("customer_id") is not None
        }
    )
    names: dict[int, str] = {}
    if cust_ids:
        for cid, code, name in (
            await db.execute(
                select(DimCustomer.id, DimCustomer.code, DimCustomer.name).where(
                    DimCustomer.id.in_(cust_ids)
                )
            )
        ).all():
            names[int(cid)] = f"{code} — {name}"
    enriched: list[dict[str, Any]] = []
    for g in worklist:
        members = []
        for m in g.get("members", []):
            mc = dict(m)
            cid = mc.get("customer_id")
            if cid is not None:
                mc["customer_label"] = names.get(int(cid))
            members.append(mc)
        enriched.append({**g, "members": members})
    return enriched
