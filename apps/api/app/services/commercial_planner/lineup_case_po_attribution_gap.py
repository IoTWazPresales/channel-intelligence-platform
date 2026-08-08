"""BACKLOG-128 — case_po gap repair for attributed distributors.

When lineup lines have a distributor_id (D-038/D-040) but the case has no
``commercial_lineup_case_po`` link to any PO for that distributor, propose a
link from shipment evidence (PO-bearing ships overlapping the attributed
products). Missing case_po must never revoke attribution.

No fuzzy match. No auto-create dims. Uses ``link_case_to_existing_po``.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.commercial_lineup import CommercialLineupCasePo, CommercialLineupLine
from app.models.facts import FactInboundShipment
from app.models.purchase_order import PurchaseOrder
from app.services.commercial_planner.lineup_case_bulk_protection import CaseProtectedError
from app.services.commercial_planner.lineup_case_po_confirm import (
    CaseNotFoundError,
    CaseStatusNotConfirmableError,
    link_case_to_existing_po,
)
from app.services.steward_audit import record_steward_audit


async def preview_attributed_distributor_case_po_gaps(
    db: AsyncSession,
    *,
    case_ids: list[int] | None = None,
    distributor_ids: list[int] | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    """Read-only proposals: unique PO covering all attributed products for a gap."""
    q = select(CommercialLineupLine).where(
        CommercialLineupLine.distributor_id.isnot(None),
        CommercialLineupLine.product_id.isnot(None),
    )
    if case_ids:
        q = q.where(CommercialLineupLine.case_id.in_([int(x) for x in case_ids]))
    if distributor_ids:
        q = q.where(
            CommercialLineupLine.distributor_id.in_([int(x) for x in distributor_ids])
        )
    lines = list((await db.execute(q)).scalars().all())

    products_by_case_dist: dict[tuple[int, int], set[int]] = defaultdict(set)
    for ln in lines:
        products_by_case_dist[(int(ln.case_id), int(ln.distributor_id))].add(
            int(ln.product_id)
        )

    if not products_by_case_dist:
        return {"items": [], "gap_count": 0, "propose_count": 0, "dry_run": True}

    case_id_set = {cid for cid, _ in products_by_case_dist}
    linked_rows = (
        await db.execute(
            select(
                CommercialLineupCasePo.case_id,
                PurchaseOrder.distributor_id,
                PurchaseOrder.id,
            )
            .join(
                PurchaseOrder,
                PurchaseOrder.id == CommercialLineupCasePo.purchase_order_id,
            )
            .where(CommercialLineupCasePo.case_id.in_(list(case_id_set)))
        )
    ).all()
    linked_dists: dict[int, set[int]] = defaultdict(set)
    linked_pos: dict[int, set[int]] = defaultdict(set)
    for cid, dist_id, po_id in linked_rows:
        linked_pos[int(cid)].add(int(po_id))
        if dist_id is not None:
            linked_dists[int(cid)].add(int(dist_id))

    gaps = {
        key: prods
        for key, prods in products_by_case_dist.items()
        if key[1] not in linked_dists.get(key[0], set())
    }
    if not gaps:
        return {"items": [], "gap_count": 0, "propose_count": 0, "dry_run": True}

    all_products = {pid for prods in gaps.values() for pid in prods}
    all_dists = {d for _, d in gaps}
    ships = (
        await db.execute(
            select(
                FactInboundShipment.product_id,
                FactInboundShipment.resolved_distributor_id,
                FactInboundShipment.purchase_order_id,
            ).where(
                FactInboundShipment.product_id.in_(list(all_products)),
                FactInboundShipment.resolved_distributor_id.in_(list(all_dists)),
                FactInboundShipment.purchase_order_id.isnot(None),
            )
        )
    ).all()

    # (dist_id, po_id) -> products seen on PO-bearing ships
    po_products: dict[tuple[int, int], set[int]] = defaultdict(set)
    for pid, dist_id, po_id in ships:
        po_products[(int(dist_id), int(po_id))].add(int(pid))

    po_ids = {po_id for (_d, po_id) in po_products}
    po_meta: dict[int, PurchaseOrder] = {}
    if po_ids:
        for po in (
            await db.execute(select(PurchaseOrder).where(PurchaseOrder.id.in_(list(po_ids))))
        ).scalars().all():
            po_meta[int(po.id)] = po

    items: list[dict[str, Any]] = []
    for (case_id, dist_id), prods in sorted(gaps.items()):
        candidates: list[dict[str, Any]] = []
        for (d, po_id), ship_prods in po_products.items():
            if d != dist_id:
                continue
            if po_id in linked_pos.get(case_id, set()):
                continue
            overlap = sorted(prods & ship_prods)
            if not overlap:
                continue
            covers_all = prods <= ship_prods
            po = po_meta.get(po_id)
            candidates.append(
                {
                    "purchase_order_id": po_id,
                    "po_number_norm": po.po_number_norm if po else None,
                    "overlap_product_ids": overlap,
                    "overlap_count": len(overlap),
                    "covers_all_attributed_products": covers_all,
                }
            )
        candidates.sort(
            key=lambda c: (
                not c["covers_all_attributed_products"],
                -c["overlap_count"],
                c["purchase_order_id"],
            )
        )
        full_cover = [c for c in candidates if c["covers_all_attributed_products"]]
        action = "unproven"
        proposed_po: int | None = None
        if len(full_cover) == 1:
            action = "propose_link"
            proposed_po = int(full_cover[0]["purchase_order_id"])
        elif len(full_cover) > 1:
            action = "ambiguous_full_cover"
        elif len(candidates) == 1:
            action = "propose_partial"
            proposed_po = int(candidates[0]["purchase_order_id"])
        elif candidates:
            action = "ambiguous_partial"

        items.append(
            {
                "case_id": case_id,
                "distributor_id": dist_id,
                "attributed_product_ids": sorted(prods),
                "action": action,
                "proposed_purchase_order_id": proposed_po,
                "candidates": candidates[:20],
            }
        )
        if len(items) >= limit:
            break

    propose_count = sum(
        1 for it in items if it["action"] in {"propose_link", "propose_partial"}
    )
    return {
        "items": items,
        "gap_count": len(items),
        "propose_count": propose_count,
        "dry_run": True,
    }


async def apply_attributed_distributor_case_po_links(
    db: AsyncSession,
    user: dict | None,
    *,
    case_ids: list[int] | None = None,
    distributor_ids: list[int] | None = None,
    links: list[dict[str, int]] | None = None,
    allow_partial: bool = False,
    allow_protected: bool = True,
    commit: bool = True,
) -> dict[str, Any]:
    """Apply unique (or explicit) case↔PO links for attribution gaps.

    Default apply only ``propose_link`` (full product cover). Set
    ``allow_partial=True`` to also apply ``propose_partial``. Explicit ``links``
    (case_id + purchase_order_id) bypass uniqueness and still refuse missing POs.
    Never clears distributor attribution.
    """
    applied: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    if links:
        for item in links:
            case_id = int(item["case_id"])
            po_id = int(item["purchase_order_id"])
            try:
                result = await link_case_to_existing_po(
                    db,
                    case_id,
                    po_id,
                    notes="backlog_128_attribution_gap",
                    commit=False,
                    allow_protected=allow_protected,
                )
                applied.append(
                    {
                        "case_id": case_id,
                        "purchase_order_id": po_id,
                        "newly_linked": result["newly_linked"],
                        "via": "explicit",
                    }
                )
            except (
                CaseNotFoundError,
                CaseProtectedError,
                CaseStatusNotConfirmableError,
                ValueError,
            ) as exc:
                skipped.append(
                    {
                        "case_id": case_id,
                        "purchase_order_id": po_id,
                        "error": str(exc),
                    }
                )
    else:
        preview = await preview_attributed_distributor_case_po_gaps(
            db,
            case_ids=case_ids,
            distributor_ids=distributor_ids,
            limit=500,
        )
        allowed = {"propose_link"}
        if allow_partial:
            allowed.add("propose_partial")
        for it in preview["items"]:
            if it["action"] not in allowed or it["proposed_purchase_order_id"] is None:
                skipped.append(
                    {
                        "case_id": it["case_id"],
                        "distributor_id": it["distributor_id"],
                        "action": it["action"],
                        "reason": "not_unique_or_partial_disabled",
                    }
                )
                continue
            po_id = int(it["proposed_purchase_order_id"])
            try:
                result = await link_case_to_existing_po(
                    db,
                    int(it["case_id"]),
                    po_id,
                    notes="backlog_128_attribution_gap",
                    commit=False,
                    allow_protected=allow_protected,
                )
                applied.append(
                    {
                        "case_id": int(it["case_id"]),
                        "distributor_id": int(it["distributor_id"]),
                        "purchase_order_id": po_id,
                        "newly_linked": result["newly_linked"],
                        "via": it["action"],
                    }
                )
            except (
                CaseNotFoundError,
                CaseProtectedError,
                CaseStatusNotConfirmableError,
                ValueError,
            ) as exc:
                skipped.append(
                    {
                        "case_id": it["case_id"],
                        "purchase_order_id": po_id,
                        "error": str(exc),
                    }
                )

    await record_steward_audit(
        db,
        user,
        action="lineup_case_po_attribution_gap_apply",
        importer="commercial_planner",
        entity_type="case_po_link",
        entity_token=None,
        target_dim="commercial_lineup_case_po",
        target_id=None,
        payload={
            "applied_count": len(applied),
            "skipped_count": len(skipped),
            "applied": applied[:200],
            "skipped": skipped[:200],
        },
        commit=False,
    )
    if commit:
        await db.commit()
    else:
        await db.flush()
    return {
        "applied_count": len(applied),
        "skipped_count": len(skipped),
        "applied": applied,
        "skipped": skipped,
        "dry_run": False,
    }
