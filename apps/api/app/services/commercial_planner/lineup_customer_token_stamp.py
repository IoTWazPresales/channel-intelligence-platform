"""Steward customer-token stamp (Unit 6b/6c / BACKLOG-112).

Mechanism (C): mint/upsert GLOBAL ``CustomerSourceTokenAlias`` then stamp lineup
lines through ordinary ``resolve_lineup_customer_id_from_token``. Soft-revoke
flips status + unwinds from stamp audit prior_customer_ids. No dim auto-create.

Unit 6c: distributor-token dual write (OC customer + line.distributor_id),
candidate isolation, ship-only preselect guard, audit provenance, worklist preload.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.commercial_lineup import CommercialLineupCasePo, CommercialLineupLine
from app.models.dimensions import DimCustomer, DimDistributor
from app.models.facts import FactInboundShipment
from app.models.import_distributor_si import CustomerSourceTokenAlias
from app.models.purchase_order import PurchaseOrder
from app.services.commercial_planner.lineup_customer_alias_resolution import (
    resolve_lineup_customer_id_from_token,
)
from app.services.commercial_planner.lineup_distributor_token import match_distributor_token
from app.services.commercial_planner.open_channel_customer import get_open_channel_customer_id
from app.services.imports.distributor_sales_inventory import _norm_key
from app.services.imports.shipment_evidence_resolution_plan import (
    build_unique_approved_customer_alias_id_by_token,
)
from app.services.steward_audit import record_steward_audit

CONFLICT_DISPOSITIONS = ("scoped", "merge", "data_error")


class CustomerTokenConflictError(Exception):
    """Genuine multi-named-customer conflict — refuse write; route steward."""

    def __init__(self, norm_token: str, competing_customer_ids: list[int]):
        self.norm_token = norm_token
        self.competing_customer_ids = competing_customer_ids
        self.dispositions = list(CONFLICT_DISPOSITIONS)
        super().__init__(
            f"Genuine customer-token conflict for {norm_token!r}: "
            f"competing_customer_ids={competing_customer_ids}"
        )


class CustomerTokenStampError(Exception):
    """Validation / empty-token / missing target errors."""


def _clear_unknown_customer(diag: list | None) -> list | None:
    if not diag:
        return None
    cleaned = [d for d in diag if d != "unknown_customer"]
    return cleaned or None


async def _load_approved_alias_rows(
    db: AsyncSession, *, norm_token: str | None = None
) -> list[tuple[str, int, int | None]]:
    q = select(
        CustomerSourceTokenAlias.normalized_token,
        CustomerSourceTokenAlias.customer_id,
        CustomerSourceTokenAlias.source_definition_id,
    ).where(CustomerSourceTokenAlias.status == "approved")
    if norm_token is not None:
        q = q.where(CustomerSourceTokenAlias.normalized_token == norm_token)
    return list((await db.execute(q)).all())


async def _load_distributor_match_maps(
    db: AsyncSession,
) -> tuple[dict[str, int], dict[str, int]]:
    name_to_id: dict[str, int] = {}
    for d in (
        await db.execute(
            select(DimDistributor).where(
                DimDistributor.distributor_status == "active",
                DimDistributor.merged_into_distributor_id.is_(None),
            )
        )
    ).scalars().all():
        nk = _norm_key(d.name)
        if nk and nk not in name_to_id:
            name_to_id[nk] = int(d.id)
    alias_to_id: dict[str, int] = {}
    from app.models.import_distributor_si import DistributorSourceTokenAlias

    for a in (
        await db.execute(
            select(DistributorSourceTokenAlias).where(
                DistributorSourceTokenAlias.status == "approved"
            )
        )
    ).scalars().all():
        nk = _norm_key(a.normalized_token)
        if nk and nk not in alias_to_id:
            alias_to_id[nk] = int(a.distributor_id)
    return name_to_id, alias_to_id


def _isolated_product_ids(
    token_lines: list[CommercialLineupLine],
    *,
    case_lines_by_case: dict[int, list[CommercialLineupLine]],
) -> set[int]:
    """W6: drop products shared with another differently-resolved token on the same case."""
    my_token = _norm_key(token_lines[0].customer_token) if token_lines else ""
    my_prods = {int(ln.product_id) for ln in token_lines if ln.product_id is not None}
    if not my_prods:
        return set()
    excluded: set[int] = set()
    case_ids = {int(ln.case_id) for ln in token_lines}
    my_cids = {
        int(ln.customer_id) for ln in token_lines if ln.customer_id is not None
    }
    for cid in case_ids:
        for other in case_lines_by_case.get(cid, []):
            ont = _norm_key(other.customer_token)
            if not ont or ont == my_token:
                continue
            other_cid = int(other.customer_id) if other.customer_id is not None else None
            # resolution differs: other resolved to a customer we are not already on
            if other_cid is None:
                continue
            if my_cids and other_cid in my_cids:
                continue
            if other.product_id is not None and int(other.product_id) in my_prods:
                excluded.add(int(other.product_id))
    return my_prods - excluded


async def _ship_evidence_for_token_lines(
    db: AsyncSession,
    *,
    token_lines: list[CommercialLineupLine],
    case_lines_by_case: dict[int, list[CommercialLineupLine]] | None = None,
    po_ids_by_case: dict[int, list[int]] | None = None,
    ship_rows: list[Any] | None = None,
) -> tuple[set[int], list[dict[str, Any]]]:
    """Return (customer_ids, provenance rows) with W6 product isolation."""
    case_ids = {int(ln.case_id) for ln in token_lines}
    if not case_ids:
        return set(), []

    if case_lines_by_case is None:
        all_case_lines = list(
            (
                await db.execute(
                    select(CommercialLineupLine).where(
                        CommercialLineupLine.case_id.in_(list(case_ids)),
                        CommercialLineupLine.customer_token.isnot(None),
                    )
                )
            ).scalars().all()
        )
        case_lines_by_case = defaultdict(list)
        for ln in all_case_lines:
            case_lines_by_case[int(ln.case_id)].append(ln)

    product_ids = _isolated_product_ids(token_lines, case_lines_by_case=case_lines_by_case)
    if not product_ids:
        return set(), []

    if po_ids_by_case is None:
        po_rows = list(
            (
                await db.execute(
                    select(
                        CommercialLineupCasePo.case_id,
                        CommercialLineupCasePo.purchase_order_id,
                    ).where(CommercialLineupCasePo.case_id.in_(list(case_ids)))
                )
            ).all()
        )
        po_ids_by_case = defaultdict(list)
        for case_id, po_id in po_rows:
            po_ids_by_case[int(case_id)].append(int(po_id))

    po_ids = sorted({p for cid in case_ids for p in po_ids_by_case.get(cid, [])})
    if not po_ids:
        return set(), []

    if ship_rows is None:
        ship_rows = list(
            (
                await db.execute(
                    select(
                        FactInboundShipment.purchase_order_id,
                        FactInboundShipment.product_id,
                        FactInboundShipment.resolved_customer_id,
                        PurchaseOrder.distributor_id,
                    )
                    .join(
                        PurchaseOrder,
                        PurchaseOrder.id == FactInboundShipment.purchase_order_id,
                        isouter=True,
                    )
                    .where(
                        FactInboundShipment.purchase_order_id.in_(po_ids),
                        FactInboundShipment.product_id.in_(list(product_ids)),
                        FactInboundShipment.resolved_customer_id.isnot(None),
                    )
                )
            ).all()
        )

    cids: set[int] = set()
    provenance: list[dict[str, Any]] = []
    seen: set[tuple[int, int, int]] = set()
    for po_id, product_id, resolved_cid, po_dist in ship_rows:
        if product_id is None or int(product_id) not in product_ids:
            continue
        if int(po_id) not in set(po_ids):
            continue
        rc = int(resolved_cid)
        cids.add(rc)
        key = (rc, int(po_id), int(product_id))
        if key in seen:
            continue
        seen.add(key)
        provenance.append(
            {
                "source": "ship",
                "customer_id": rc,
                "purchase_order_id": int(po_id),
                "po_distributor_id": int(po_dist) if po_dist is not None else None,
                "product_id": int(product_id),
            }
        )
    return cids, provenance


async def _ship_customer_ids_for_token_lines(
    db: AsyncSession,
    *,
    token_lines: list[CommercialLineupLine],
) -> set[int]:
    cids, _ = await _ship_evidence_for_token_lines(db, token_lines=token_lines)
    return cids


async def _named_competitors(
    db: AsyncSession,
    *,
    norm_token: str,
    open_channel_id: int | None,
    token_lines: list[CommercialLineupLine] | None = None,
) -> list[int]:
    alias_rows = await _load_approved_alias_rows(db, norm_token=norm_token)
    ids: set[int] = {int(cid) for _, cid, _ in alias_rows}

    if token_lines is None:
        token_lines = await _lines_for_norm_token(db, norm_token)

    ids.update(await _ship_customer_ids_for_token_lines(db, token_lines=token_lines))

    if open_channel_id is not None:
        ids.discard(int(open_channel_id))
    return sorted(ids)


async def _lines_for_norm_token(db: AsyncSession, norm_token: str) -> list[CommercialLineupLine]:
    lines = list(
        (
            await db.execute(
                select(CommercialLineupLine).where(CommercialLineupLine.customer_token.isnot(None))
            )
        ).scalars().all()
    )
    return [ln for ln in lines if _norm_key(ln.customer_token) == norm_token]


async def _customer_label(db: AsyncSession, customer_id: int) -> str:
    row = await db.get(DimCustomer, customer_id)
    if row is None:
        return f"customer:{customer_id}"
    return f"{row.name or row.code or customer_id} (id {customer_id})"


async def _build_candidate_provenance(
    db: AsyncSession,
    *,
    norm_token: str,
    token_lines: list[CommercialLineupLine],
) -> tuple[set[int], list[dict[str, Any]], set[int], set[int]]:
    """Return (all_cands, provenance, alias_cids, ship_cids)."""
    alias_rows = await _load_approved_alias_rows(db, norm_token=norm_token)
    alias_cids = {int(cid) for _, cid, _ in alias_rows}
    provenance: list[dict[str, Any]] = [
        {"source": "alias", "customer_id": cid, "purchase_order_id": None, "po_distributor_id": None, "product_id": None}
        for cid in sorted(alias_cids)
    ]
    ship_cids, ship_prov = await _ship_evidence_for_token_lines(db, token_lines=token_lines)
    provenance.extend(ship_prov)
    return alias_cids | ship_cids, provenance, alias_cids, ship_cids


def _preferred_target(
    *,
    bucket: str,
    named_only: list[int],
    all_cands: set[int],
    alias_cids: set[int],
    ship_cids: set[int],
) -> int | None:
    """W5: never pre-select a candidate that is ship-only (no alias support)."""

    def _ok(cid: int) -> int | None:
        if cid in alias_cids:
            return cid
        # ship-only → require explicit steward choice
        if cid in ship_cids and cid not in alias_cids:
            return None
        return cid

    if bucket == "specificity" and named_only:
        return _ok(named_only[0])
    if bucket == "clean":
        if named_only:
            return _ok(named_only[0])
        if len(all_cands) == 1:
            return _ok(next(iter(all_cands)))
    return None


async def preview_customer_token_stamp(
    db: AsyncSession,
    *,
    norm_token: str,
    target_customer_id: int,
) -> dict[str, Any]:
    """Blast-radius preview — no writes. Includes candidate provenance (W5/W7)."""
    nt = _norm_key(norm_token)
    if not nt:
        raise CustomerTokenStampError("empty token — cannot stamp; see backlog tokenless path")
    target = await db.get(DimCustomer, int(target_customer_id))
    if target is None:
        raise CustomerTokenStampError(f"target customer {target_customer_id} does not exist")

    lines = await _lines_for_norm_token(db, nt)
    stampable = [
        ln
        for ln in lines
        if ln.customer_id is None or int(ln.customer_id) != int(target_customer_id)
    ]
    breakdown: dict[str, int] = defaultdict(int)
    for ln in lines:
        key = str(ln.customer_id) if ln.customer_id is not None else "null"
        breakdown[key] += 1

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

    all_cands, provenance, alias_cids, ship_cids = await _build_candidate_provenance(
        db, norm_token=nt, token_lines=lines
    )
    name_map, alias_map = await _load_distributor_match_maps(db)
    dist_match = match_distributor_token(nt, name_to_id=name_map, alias_to_id=alias_map)

    sample = [
        {
            "line_id": int(ln.id),
            "case_id": int(ln.case_id),
            "customer_token": ln.customer_token,
            "customer_id": int(ln.customer_id) if ln.customer_id is not None else None,
            "distributor_id": int(ln.distributor_id) if ln.distributor_id is not None else None,
        }
        for ln in stampable[:10]
    ]

    was_preselected = False
    # preferred computation for audit preview context
    oc_id = await get_open_channel_customer_id(db)
    named_only = sorted(c for c in all_cands if oc_id is None or c != int(oc_id))
    has_oc = oc_id is not None and int(oc_id) in all_cands
    if len(named_only) > 1:
        bucket = "genuine_conflict"
    elif len(named_only) == 1 and has_oc:
        bucket = "specificity"
    else:
        bucket = "clean"
    preferred = _preferred_target(
        bucket=bucket,
        named_only=named_only,
        all_cands=all_cands,
        alias_cids=alias_cids,
        ship_cids=ship_cids,
    )
    if preferred is not None and int(preferred) == int(target_customer_id):
        was_preselected = True

    return {
        "norm_token": nt,
        "target_customer_id": int(target_customer_id),
        "target_customer_label": await _customer_label(db, int(target_customer_id)),
        "line_count": len(stampable),
        "lines_matching_token": len(lines),
        "sample_lines": sample,
        "current_resolution_breakdown": dict(breakdown),
        "would_create_alias": existing is None,
        "existing_alias_id": int(existing.id) if existing is not None else None,
        "existing_alias_status": existing.status if existing is not None else None,
        "existing_alias_customer_id": int(existing.customer_id) if existing is not None else None,
        "candidates_presented": sorted(all_cands),
        "candidate_provenance": provenance,
        "candidate_source": {
            str(cid): ("alias" if cid in alias_cids else "ship")
            for cid in sorted(all_cands)
        },
        "was_preselected": was_preselected,
        "preferred_target_id": preferred,
        "distributor_token_match": (
            {
                "distributor_id": dist_match.distributor_id,
                "matched_via": dist_match.matched_via,
                "matched_key": dist_match.matched_key,
            }
            if dist_match
            else None
        ),
        "would_set_distributor_id": dist_match.distributor_id if dist_match else None,
    }


async def apply_customer_token_stamp(
    db: AsyncSession,
    user: dict | None,
    *,
    norm_token: str,
    target_customer_id: int,
    reason: str,
    commit: bool = True,
    allow_distributor_token: bool = True,
) -> dict[str, Any]:
    """One txn: refuse conflict → upsert global alias → stamp lines (+ optional dist) → audit."""
    nt = _norm_key(norm_token)
    if not nt:
        raise CustomerTokenStampError("empty token — cannot stamp; see backlog tokenless path")
    reason_s = (reason or "").strip()
    if not reason_s:
        raise CustomerTokenStampError("reason required")

    target = await db.get(DimCustomer, int(target_customer_id))
    if target is None:
        raise CustomerTokenStampError(f"target customer {target_customer_id} does not exist")

    oc_id = await get_open_channel_customer_id(db)
    lines = await _lines_for_norm_token(db, nt)

    name_map, alias_map_dist = await _load_distributor_match_maps(db)
    dist_match = (
        match_distributor_token(nt, name_to_id=name_map, alias_to_id=alias_map_dist)
        if allow_distributor_token
        else None
    )

    all_cands, provenance, alias_cids, ship_cids = await _build_candidate_provenance(
        db, norm_token=nt, token_lines=lines
    )
    named = sorted(c for c in all_cands if oc_id is None or c != int(oc_id))
    has_oc = oc_id is not None and int(oc_id) in all_cands
    if len(named) > 1:
        bucket = "genuine_conflict"
    elif len(named) == 1 and has_oc:
        bucket = "specificity"
    else:
        bucket = "clean"
    preferred = _preferred_target(
        bucket=bucket,
        named_only=named,
        all_cands=all_cands,
        alias_cids=alias_cids,
        ship_cids=ship_cids,
    )
    was_preselected = preferred is not None and int(preferred) == int(target_customer_id)

    # Distributor-token path: force Open Channel + write line.distributor_id (W1)
    line_distributor_id: int | None = None
    if dist_match is not None:
        if oc_id is None:
            raise CustomerTokenStampError("OPEN_CHANNEL customer missing — cannot apply distributor-token rule")
        if int(target_customer_id) != int(oc_id):
            raise CustomerTokenStampError(
                f"distributor-token stamp requires target OPEN_CHANNEL ({oc_id}), got {target_customer_id}"
            )
        line_distributor_id = int(dist_match.distributor_id)
        # Bypass multi-named conflict — the token names a distributor, not a retailer contest
    elif len(named) > 1:
        raise CustomerTokenConflictError(nt, named)

    # Upsert GLOBAL approved alias
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

    raw_sample = next(
        (ln.customer_token for ln in lines if ln.customer_token),
        nt,
    )
    if existing is None:
        alias = CustomerSourceTokenAlias(
            customer_id=int(target_customer_id),
            source_definition_id=None,
            distributor_id=None,
            raw_token=str(raw_sample)[:512],
            normalized_token=nt[:512],
            dealer_group_token=None,
            status="approved",
            notes=f"lineup_customer_token_stamp:{reason_s}"[:1024],
            created_from_import_job_id=None,
            import_entity_mapping_candidate_id=None,
        )
        db.add(alias)
        await db.flush()
    else:
        alias = existing
        if int(alias.customer_id) != int(target_customer_id):
            if oc_id is not None and int(alias.customer_id) == int(oc_id):
                alias.customer_id = int(target_customer_id)
            elif dist_match is not None and oc_id is not None and int(target_customer_id) == int(oc_id):
                # named→OC only when distributor-token rule explicitly rewrites (after revoke)
                alias.customer_id = int(target_customer_id)
            else:
                raise CustomerTokenConflictError(
                    nt, sorted({int(alias.customer_id), int(target_customer_id)})
                )
        await db.flush()

    alias_id = int(alias.id)

    all_rows = await _load_approved_alias_rows(db)
    alias_map = build_unique_approved_customer_alias_id_by_token(all_rows)
    alias_map[nt] = int(target_customer_id)

    cust_rows = list((await db.execute(select(DimCustomer))).scalars().all())
    customers_by_id = {int(c.id): c for c in cust_rows}
    customer_map: dict[str, DimCustomer] = {}
    for c in cust_rows:
        if c.name:
            customer_map[c.name.strip().lower()] = c
        if c.code:
            customer_map[c.code.strip().lower()] = c

    per_line: list[dict[str, Any]] = []
    line_ids: list[int] = []
    prior_customer_ids: dict[str, int | None] = {}
    prior_distributor_ids: dict[str, int | None] = {}

    for ln in lines:
        prior = int(ln.customer_id) if ln.customer_id is not None else None
        prior_dist = int(ln.distributor_id) if ln.distributor_id is not None else None
        resolved = resolve_lineup_customer_id_from_token(
            ln.customer_token,
            customer_map=customer_map,
            customer_alias_map=alias_map,
            customers_by_id=customers_by_id,
        )
        if resolved is None:
            continue
        changed = prior != int(resolved)
        dist_changed = False
        if line_distributor_id is not None:
            if prior_dist != line_distributor_id:
                ln.distributor_id = line_distributor_id
                dist_changed = True
            # D-040: token match writes FK as proposal (even if dist already set)
            if (ln.distributor_attribution_status or "") != "token_proposed":
                ln.distributor_attribution_status = "token_proposed"
                dist_changed = True
        if not changed and not dist_changed:
            continue
        if changed:
            ln.customer_id = int(resolved)
            ln.diagnostic_codes = _clear_unknown_customer(
                list(ln.diagnostic_codes) if ln.diagnostic_codes else None
            )
        per_line.append(
            {
                "line_id": int(ln.id),
                "prior_customer_id": prior,
                "prior_distributor_id": prior_dist,
                "distributor_id": int(ln.distributor_id) if ln.distributor_id is not None else None,
            }
        )
        line_ids.append(int(ln.id))
        prior_customer_ids[str(ln.id)] = prior
        prior_distributor_ids[str(ln.id)] = prior_dist

    cand_source = {
        str(cid): ("alias" if cid in alias_cids else "ship") for cid in sorted(all_cands)
    }

    await record_steward_audit(
        db,
        user,
        action="lineup_customer_token_stamp",
        importer="commercial_planner",
        entity_type="customer_token",
        entity_token=nt,
        target_dim="dim_customer",
        target_id=int(target_customer_id),
        payload={
            "norm_token": nt,
            "line_ids": line_ids,
            "reason": reason_s,
            "alias_id": alias_id,
            "prior_customer_ids": prior_customer_ids,
            "prior_distributor_ids": prior_distributor_ids,
            "target_customer_id": int(target_customer_id),
            "candidates_presented": sorted(all_cands),
            "candidate_source": cand_source,
            "was_preselected": was_preselected,
            "distributor_token_match": (
                {
                    "distributor_id": dist_match.distributor_id,
                    "matched_via": dist_match.matched_via,
                    "matched_key": dist_match.matched_key,
                }
                if dist_match
                else None
            ),
            "line_distributor_id": line_distributor_id,
            "candidate_provenance": provenance,
        },
        commit=False,
    )

    if commit:
        await db.commit()
    else:
        await db.flush()

    return {
        "alias_id": alias_id,
        "stamped_count": len(per_line),
        "per_line": per_line,
        "norm_token": nt,
        "target_customer_id": int(target_customer_id),
        "line_distributor_id": line_distributor_id,
        "was_preselected": was_preselected,
        "candidates_presented": sorted(all_cands),
    }


async def revoke_customer_token_alias(
    db: AsyncSession,
    user: dict | None,
    *,
    alias_id: int,
    reason: str,
    commit: bool = True,
) -> dict[str, Any]:
    """Soft-revoke alias (status flip) + unwind lines from stamp audit priors."""
    reason_s = (reason or "").strip()
    if not reason_s:
        raise CustomerTokenStampError("reason required")

    alias = await db.get(CustomerSourceTokenAlias, int(alias_id))
    if alias is None:
        raise CustomerTokenStampError(f"alias {alias_id} not found")
    if (alias.status or "").strip() != "approved":
        raise CustomerTokenStampError(f"alias {alias_id} is not approved (status={alias.status})")

    nt = alias.normalized_token
    target_cid = int(alias.customer_id)
    alias.status = "revoked"
    await db.flush()

    from app.models.steward_audit import StewardAuditEvent

    audits = list(
        (
            await db.execute(
                select(StewardAuditEvent)
                .where(
                    StewardAuditEvent.action == "lineup_customer_token_stamp",
                    StewardAuditEvent.entity_token == nt,
                )
                .order_by(StewardAuditEvent.id.desc())
                .limit(20)
            )
        ).scalars().all()
    )
    prior_map: dict[int, int | None] = {}
    prior_dist_map: dict[int, int | None] = {}
    for ev in audits:
        payload = ev.payload_json or {}
        if int(payload.get("alias_id") or 0) != int(alias_id):
            continue
        for lid_s, prior in (payload.get("prior_customer_ids") or {}).items():
            prior_map[int(lid_s)] = int(prior) if prior is not None else None
        for lid_s, prior in (payload.get("prior_distributor_ids") or {}).items():
            prior_dist_map[int(lid_s)] = int(prior) if prior is not None else None
        break

    unwound = 0
    if prior_map:
        lines = list(
            (
                await db.execute(
                    select(CommercialLineupLine).where(CommercialLineupLine.id.in_(list(prior_map.keys())))
                )
            ).scalars().all()
        )
        for ln in lines:
            if ln.customer_id is None or int(ln.customer_id) != target_cid:
                continue
            prior = prior_map.get(int(ln.id))
            ln.customer_id = prior
            if int(ln.id) in prior_dist_map:
                ln.distributor_id = prior_dist_map[int(ln.id)]
                ln.distributor_attribution_status = None
            if prior is None:
                diag = list(ln.diagnostic_codes or [])
                if "unknown_customer" not in diag:
                    diag.append("unknown_customer")
                ln.diagnostic_codes = diag
            unwound += 1

    await record_steward_audit(
        db,
        user,
        action="lineup_customer_token_alias_revoke",
        importer="commercial_planner",
        entity_type="customer_token",
        entity_token=nt,
        target_dim="dim_customer",
        target_id=target_cid,
        payload={
            "alias_id": int(alias_id),
            "reason": reason_s,
            "unwound_count": unwound,
            "norm_token": nt,
        },
        commit=False,
    )

    if commit:
        await db.commit()
    else:
        await db.flush()

    return {
        "revoked_alias_id": int(alias_id),
        "unwound_count": unwound,
        "norm_token": nt,
        "status": "revoked",
    }


async def list_customer_token_worklist(
    db: AsyncSession,
    *,
    limit: int = 200,
    exclude_prefix: str | None = "unit6b-",
) -> dict[str, Any]:
    """Group unresolved / contested lineup customer tokens for steward stamp.

    W10: SQL filter + preload — zero per-token queries in the loop.
    W9: exclude_prefix applied before grouping.
    """
    oc_id = await get_open_channel_customer_id(db)

    # SQL-filter unresolved lines (customer_id IS NULL)
    lines = list(
        (
            await db.execute(
                select(CommercialLineupLine).where(CommercialLineupLine.customer_id.is_(None))
            )
        ).scalars().all()
    )

    # Preload: all approved aliases
    all_alias_rows = await _load_approved_alias_rows(db)
    aliases_by_token: dict[str, set[int]] = defaultdict(set)
    for nt, cid, _src in all_alias_rows:
        aliases_by_token[_norm_key(nt)].add(int(cid))

    # Group by token (exclude_prefix BEFORE grouping)
    by_token: dict[str, list[CommercialLineupLine]] = defaultdict(list)
    empty_lines: list[CommercialLineupLine] = []
    excl = (exclude_prefix or "").strip().lower()
    for ln in lines:
        raw = (ln.customer_token or "").strip()
        if not raw:
            empty_lines.append(ln)
            continue
        nt = _norm_key(raw)
        if excl and nt.startswith(excl):
            continue
        by_token[nt].append(ln)

    case_ids = {int(ln.case_id) for tlines in by_token.values() for ln in tlines}

    # Preload case lines (for W6 isolation) — only cases we need
    case_lines_by_case: dict[int, list[CommercialLineupLine]] = defaultdict(list)
    if case_ids:
        for ln in (
            await db.execute(
                select(CommercialLineupLine).where(
                    CommercialLineupLine.case_id.in_(list(case_ids)),
                    CommercialLineupLine.customer_token.isnot(None),
                )
            )
        ).scalars().all():
            case_lines_by_case[int(ln.case_id)].append(ln)

    # Preload case→PO
    po_ids_by_case: dict[int, list[int]] = defaultdict(list)
    all_po_ids: set[int] = set()
    if case_ids:
        for case_id, po_id in (
            await db.execute(
                select(
                    CommercialLineupCasePo.case_id,
                    CommercialLineupCasePo.purchase_order_id,
                ).where(CommercialLineupCasePo.case_id.in_(list(case_ids)))
            )
        ).all():
            po_ids_by_case[int(case_id)].append(int(po_id))
            all_po_ids.add(int(po_id))

    # Preload ship rows for those POs (all products — filter in memory per token)
    ship_rows_all: list[Any] = []
    if all_po_ids:
        ship_rows_all = list(
            (
                await db.execute(
                    select(
                        FactInboundShipment.purchase_order_id,
                        FactInboundShipment.product_id,
                        FactInboundShipment.resolved_customer_id,
                        PurchaseOrder.distributor_id,
                    )
                    .join(
                        PurchaseOrder,
                        PurchaseOrder.id == FactInboundShipment.purchase_order_id,
                        isouter=True,
                    )
                    .where(
                        FactInboundShipment.purchase_order_id.in_(list(all_po_ids)),
                        FactInboundShipment.resolved_customer_id.isnot(None),
                    )
                )
            ).all()
        )

    name_map, alias_map_dist = await _load_distributor_match_maps(db)

    cust_ids_needed: set[int] = set()
    items: list[dict[str, Any]] = []

    for nt, token_lines in sorted(by_token.items(), key=lambda x: (-len(x[1]), x[0])):
        alias_cids = set(aliases_by_token.get(nt, set()))
        # Filter ship rows to this token's isolated products + POs
        product_ids = _isolated_product_ids(token_lines, case_lines_by_case=case_lines_by_case)
        t_cases = {int(ln.case_id) for ln in token_lines}
        t_pos = {p for cid in t_cases for p in po_ids_by_case.get(cid, [])}
        ship_cids: set[int] = set()
        ship_prov: list[dict[str, Any]] = []
        seen: set[tuple[int, int, int]] = set()
        for po_id, product_id, resolved_cid, po_dist in ship_rows_all:
            if int(po_id) not in t_pos:
                continue
            if product_id is None or int(product_id) not in product_ids:
                continue
            rc = int(resolved_cid)
            ship_cids.add(rc)
            key = (rc, int(po_id), int(product_id))
            if key in seen:
                continue
            seen.add(key)
            ship_prov.append(
                {
                    "source": "ship",
                    "customer_id": rc,
                    "purchase_order_id": int(po_id),
                    "po_distributor_id": int(po_dist) if po_dist is not None else None,
                    "product_id": int(product_id),
                }
            )

        all_cands = alias_cids | ship_cids
        named_only = sorted(c for c in all_cands if oc_id is None or c != int(oc_id))
        has_oc = oc_id is not None and int(oc_id) in all_cands

        dist_match = match_distributor_token(nt, name_to_id=name_map, alias_to_id=alias_map_dist)

        if dist_match is not None:
            bucket = "distributor_token"
        elif len(named_only) > 1:
            bucket = "genuine_conflict"
        elif len(named_only) == 1 and has_oc:
            bucket = "specificity"
        else:
            bucket = "clean"

        preferred = None
        if bucket == "distributor_token" and oc_id is not None:
            preferred = int(oc_id)
        elif bucket != "genuine_conflict":
            preferred = _preferred_target(
                bucket=bucket if bucket != "distributor_token" else "clean",
                named_only=named_only,
                all_cands=all_cands,
                alias_cids=alias_cids,
                ship_cids=ship_cids,
            )

        free_target_allowed = (
            bucket == "clean" and not all_cands
        ) or (
            bucket == "clean" and preferred is None and bool(all_cands)
        )

        stamp_enabled = False
        if bucket == "distributor_token":
            stamp_enabled = True
        elif bucket in {"clean", "specificity"} and preferred is not None:
            stamp_enabled = True
        elif free_target_allowed:
            stamp_enabled = False  # needs free pick first

        cand_ids = set(all_cands)
        if bucket == "distributor_token" and oc_id is not None:
            cand_ids.add(int(oc_id))
        cust_ids_needed.update(cand_ids)
        if preferred is not None:
            cust_ids_needed.add(preferred)
        if oc_id is not None:
            cust_ids_needed.add(int(oc_id))

        items.append(
            {
                "item_key": nt,
                "norm_token": nt,
                "sample_token": (token_lines[0].customer_token or nt),
                "line_count": len(token_lines),
                "bucket": bucket,
                "alias_candidate_ids": sorted(cand_ids),
                "preferred_target_id": preferred,
                "stamp_enabled": stamp_enabled,
                "free_target_allowed": free_target_allowed or bucket == "clean" and not all_cands,
                "conflict": bucket == "genuine_conflict",
                "competing_customer_ids": named_only if bucket == "genuine_conflict" else [],
                "dispositions": list(CONFLICT_DISPOSITIONS) if bucket == "genuine_conflict" else [],
                "distributor_token_match": (
                    {
                        "distributor_id": dist_match.distributor_id,
                        "matched_via": dist_match.matched_via,
                        "matched_key": dist_match.matched_key,
                    }
                    if dist_match
                    else None
                ),
                "would_set_attribution_status": "token_proposed" if dist_match else None,
                "ship_corroboration_offer": None,
                "candidate_provenance": (
                    [{"source": "alias", "customer_id": c} for c in sorted(alias_cids)] + ship_prov
                ),
            }
        )

    if empty_lines:
        items.append(
            {
                "item_key": "__empty_token__",
                "norm_token": "",
                "sample_token": "",
                "line_count": len(empty_lines),
                "bucket": "empty_token",
                "alias_candidate_ids": [],
                "preferred_target_id": None,
                "stamp_enabled": False,
                "free_target_allowed": False,
                "conflict": False,
                "competing_customer_ids": [],
                "dispositions": [],
                "distributor_token_match": None,
                "would_set_attribution_status": None,
                "ship_corroboration_offer": None,
                "candidate_provenance": [],
            }
        )

    # D-040: attach sole-exact ship corroboration offers for free-pick / clean tokens
    offer_tokens = [
        it["norm_token"]
        for it in items
        if it["bucket"] not in {"distributor_token", "empty_token", "genuine_conflict"}
        and it.get("free_target_allowed")
    ]
    if offer_tokens:
        from app.services.commercial_planner.lineup_distributor_attribution import (
            preview_distributor_confirmer,
        )

        offer_preview = await preview_distributor_confirmer(
            db, norm_tokens=offer_tokens, limit_tokens=len(offer_tokens)
        )
        offer_by_token = {
            it["norm_token"]: it.get("ship_corroboration_offer") for it in offer_preview["items"]
        }
        for it in items:
            if it["norm_token"] in offer_by_token:
                it["ship_corroboration_offer"] = offer_by_token[it["norm_token"]]

    labels: dict[int, str] = {}
    if cust_ids_needed:
        for c in (
            await db.execute(select(DimCustomer).where(DimCustomer.id.in_(list(cust_ids_needed))))
        ).scalars().all():
            labels[int(c.id)] = f"{c.name or c.code or c.id} (id {c.id})"

    for it in items:
        cands = []
        for cid in it["alias_candidate_ids"]:
            src = "alias"
            for p in it.get("candidate_provenance") or []:
                if int(p.get("customer_id") or 0) == cid:
                    src = p.get("source") or src
                    break
            cands.append(
                {
                    "targetKey": str(cid),
                    "label": labels.get(cid, f"customer:{cid}"),
                    "meta": {
                        "customer_id": cid,
                        "is_open_channel": oc_id is not None and cid == int(oc_id),
                        "preferred": it["preferred_target_id"] == cid,
                        "source": src,
                    },
                }
            )
        cands.sort(key=lambda x: (0 if x["meta"].get("preferred") else 1, x["label"]))
        it["alias_candidates"] = cands

    counts: dict[str, int] = defaultdict(int)
    for it in items:
        counts[it["bucket"]] += 1
        counts["all"] += 1

    return {
        "items": items[: max(1, min(int(limit), 500))],
        "total": len(items),
        "bucket_counts": dict(counts),
        "open_channel_customer_id": oc_id,
        "exclude_prefix": excl or None,
        "rows_scanned": len(lines),
        "data_unavailable": False,
    }


async def list_minted_global_aliases(db: AsyncSession, *, limit: int = 100) -> dict[str, Any]:
    rows = list(
        (
            await db.execute(
                select(CustomerSourceTokenAlias)
                .where(
                    CustomerSourceTokenAlias.source_definition_id.is_(None),
                    CustomerSourceTokenAlias.distributor_id.is_(None),
                    CustomerSourceTokenAlias.notes.ilike("lineup_customer_token_stamp:%"),
                )
                .order_by(CustomerSourceTokenAlias.id.desc())
                .limit(max(1, min(int(limit), 500)))
            )
        ).scalars().all()
    )
    out = []
    for a in rows:
        out.append(
            {
                "alias_id": int(a.id),
                "norm_token": a.normalized_token,
                "customer_id": int(a.customer_id),
                "status": a.status,
                "raw_token": a.raw_token,
            }
        )
    return {"aliases": out, "total": len(out)}
