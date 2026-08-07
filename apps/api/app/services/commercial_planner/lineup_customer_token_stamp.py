"""Steward customer-token stamp via global approved alias (Unit 6b / BACKLOG-112).

Mechanism (C): mint/upsert GLOBAL ``CustomerSourceTokenAlias`` then stamp lineup
lines through ordinary ``resolve_lineup_customer_id_from_token``. Soft-revoke
flips status + unwinds from stamp audit prior_customer_ids. No dim auto-create.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.commercial_lineup import CommercialLineupLine
from app.models.dimensions import DimCustomer
from app.models.facts import FactInboundShipment
from app.models.import_distributor_si import CustomerSourceTokenAlias
from app.services.commercial_planner.lineup_customer_alias_resolution import (
    resolve_lineup_customer_id_from_token,
)
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


async def _ship_customer_ids_for_token_lines(
    db: AsyncSession,
    *,
    token_lines: list[CommercialLineupLine],
) -> set[int]:
    """Ship-resolved customers scoped to POs linked to the same cases as these lines.

    Broad product-only fan-out pulls unrelated customers who bought the same SKU
    and falsely marks specificity tokens as genuine_conflict.
    """
    case_ids = {int(ln.case_id) for ln in token_lines}
    product_ids = {int(ln.product_id) for ln in token_lines if ln.product_id is not None}
    if not case_ids or not product_ids:
        return set()
    from app.models.commercial_lineup import CommercialLineupCasePo

    po_ids = list(
        (
            await db.execute(
                select(CommercialLineupCasePo.purchase_order_id).where(
                    CommercialLineupCasePo.case_id.in_(list(case_ids))
                )
            )
        ).scalars().all()
    )
    if not po_ids:
        return set()
    ship_cids = list(
        (
            await db.execute(
                select(FactInboundShipment.resolved_customer_id)
                .where(
                    FactInboundShipment.purchase_order_id.in_([int(p) for p in po_ids]),
                    FactInboundShipment.product_id.in_(list(product_ids)),
                    FactInboundShipment.resolved_customer_id.isnot(None),
                )
                .distinct()
            )
        ).scalars().all()
    )
    return {int(c) for c in ship_cids if c is not None}


async def _named_competitors(
    db: AsyncSession,
    *,
    norm_token: str,
    open_channel_id: int | None,
    token_lines: list[CommercialLineupLine] | None = None,
) -> list[int]:
    """Distinct non–OPEN_CHANNEL customers from approved aliases + case-PO-scoped ship evidence."""
    alias_rows = await _load_approved_alias_rows(db, norm_token=norm_token)
    ids: set[int] = {int(cid) for _, cid, _ in alias_rows}

    if token_lines is None:
        all_lines = list(
            (
                await db.execute(
                    select(CommercialLineupLine).where(CommercialLineupLine.customer_token.isnot(None))
                )
            ).scalars().all()
        )
        token_lines = [ln for ln in all_lines if _norm_key(ln.customer_token) == norm_token]

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


async def preview_customer_token_stamp(
    db: AsyncSession,
    *,
    norm_token: str,
    target_customer_id: int,
) -> dict[str, Any]:
    """Blast-radius preview — no writes."""
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

    sample = [
        {
            "line_id": int(ln.id),
            "case_id": int(ln.case_id),
            "customer_token": ln.customer_token,
            "customer_id": int(ln.customer_id) if ln.customer_id is not None else None,
        }
        for ln in stampable[:10]
    ]

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
    }


async def apply_customer_token_stamp(
    db: AsyncSession,
    user: dict | None,
    *,
    norm_token: str,
    target_customer_id: int,
    reason: str,
    commit: bool = True,
) -> dict[str, Any]:
    """One txn: refuse conflict → upsert global alias → stamp lines → audit."""
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
    named = await _named_competitors(
        db, norm_token=nt, open_channel_id=oc_id, token_lines=lines
    )
    if len(named) > 1:
        raise CustomerTokenConflictError(nt, named)

    # Upsert GLOBAL approved alias (C7)
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
            # Specificity correction: only allow OC → named (or same family)
            if oc_id is not None and int(alias.customer_id) == int(oc_id):
                alias.customer_id = int(target_customer_id)
            else:
                raise CustomerTokenConflictError(
                    nt, sorted({int(alias.customer_id), int(target_customer_id)})
                )
        await db.flush()

    alias_id = int(alias.id)

    # Refresh alias map and stamp via ordinary resolution (C6)
    all_rows = await _load_approved_alias_rows(db)
    alias_map = build_unique_approved_customer_alias_id_by_token(all_rows)
    # Ensure our global target is visible even if scoped duplicates exist
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

    for ln in lines:
        prior = int(ln.customer_id) if ln.customer_id is not None else None
        resolved = resolve_lineup_customer_id_from_token(
            ln.customer_token,
            customer_map=customer_map,
            customer_alias_map=alias_map,
            customers_by_id=customers_by_id,
        )
        if resolved is None:
            continue
        if prior == int(resolved):
            continue
        ln.customer_id = int(resolved)
        ln.diagnostic_codes = _clear_unknown_customer(
            list(ln.diagnostic_codes) if ln.diagnostic_codes else None
        )
        per_line.append({"line_id": int(ln.id), "prior_customer_id": prior})
        line_ids.append(int(ln.id))
        prior_customer_ids[str(ln.id)] = prior

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
            "target_customer_id": int(target_customer_id),
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

    # Find latest stamp audit for this alias
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
    for ev in audits:
        payload = ev.payload_json or {}
        if int(payload.get("alias_id") or 0) != int(alias_id):
            continue
        for lid_s, prior in (payload.get("prior_customer_ids") or {}).items():
            prior_map[int(lid_s)] = int(prior) if prior is not None else None
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
) -> dict[str, Any]:
    """Group unresolved / contested lineup customer tokens for steward stamp."""
    oc_id = await get_open_channel_customer_id(db)
    lines = list(
        (
            await db.execute(
                select(CommercialLineupLine).where(
                    or_(
                        CommercialLineupLine.customer_id.is_(None),
                        CommercialLineupLine.customer_token.isnot(None),
                    )
                )
            )
        ).scalars().all()
    )

    # Group null-customer lines by norm token (include empty)
    by_token: dict[str, list[CommercialLineupLine]] = defaultdict(list)
    empty_lines: list[CommercialLineupLine] = []
    for ln in lines:
        if ln.customer_id is not None:
            continue
        raw = (ln.customer_token or "").strip()
        if not raw:
            empty_lines.append(ln)
            continue
        by_token[_norm_key(raw)].append(ln)

    # Dim labels cache
    cust_ids_needed: set[int] = set()
    items: list[dict[str, Any]] = []

    for nt, token_lines in sorted(by_token.items(), key=lambda x: (-len(x[1]), x[0])):
        alias_rows = await _load_approved_alias_rows(db, norm_token=nt)
        all_cands = {int(cid) for _, cid, _ in alias_rows}
        all_cands.update(await _ship_customer_ids_for_token_lines(db, token_lines=token_lines))

        named_only = sorted(c for c in all_cands if oc_id is None or c != int(oc_id))
        has_oc = oc_id is not None and int(oc_id) in all_cands

        if len(named_only) > 1:
            bucket = "genuine_conflict"
        elif len(named_only) == 1 and has_oc:
            bucket = "specificity"
        elif len(named_only) == 1 or (len(all_cands) == 1):
            bucket = "clean"
        elif not all_cands:
            bucket = "clean"
        else:
            bucket = "clean"

        # Pre-select: specificity → named; clean → sole candidate
        preferred: int | None = None
        if bucket == "specificity" and named_only:
            preferred = named_only[0]
        elif bucket == "clean":
            if named_only:
                preferred = named_only[0]
            elif len(all_cands) == 1:
                preferred = next(iter(all_cands))

        cust_ids_needed.update(all_cands)
        if preferred is not None:
            cust_ids_needed.add(preferred)

        items.append(
            {
                "item_key": nt,
                "norm_token": nt,
                "sample_token": (token_lines[0].customer_token or nt),
                "line_count": len(token_lines),
                "bucket": bucket,
                "alias_candidate_ids": sorted(all_cands),
                "preferred_target_id": preferred,
                "stamp_enabled": bucket in {"clean", "specificity"} and bool(all_cands),
                "conflict": bucket == "genuine_conflict",
                "competing_customer_ids": named_only if bucket == "genuine_conflict" else [],
                "dispositions": list(CONFLICT_DISPOSITIONS) if bucket == "genuine_conflict" else [],
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
                "conflict": False,
                "competing_customer_ids": [],
                "dispositions": [],
            }
        )

    # Attach labels
    labels: dict[int, str] = {}
    if cust_ids_needed:
        for c in (
            await db.execute(select(DimCustomer).where(DimCustomer.id.in_(list(cust_ids_needed))))
        ).scalars().all():
            labels[int(c.id)] = f"{c.name or c.code or c.id} (id {c.id})"

    for it in items:
        cands = []
        for cid in it["alias_candidate_ids"]:
            cands.append(
                {
                    "targetKey": str(cid),
                    "label": labels.get(cid, f"customer:{cid}"),
                    "meta": {
                        "customer_id": cid,
                        "is_open_channel": oc_id is not None and cid == int(oc_id),
                        "preferred": it["preferred_target_id"] == cid,
                    },
                }
            )
        # Prefer named first in list for specificity
        cands.sort(key=lambda x: (0 if x["meta"].get("preferred") else 1, x["label"]))
        it["alias_candidates"] = cands

    # Bucket counts
    counts = defaultdict(int)
    for it in items:
        counts[it["bucket"]] += 1
        counts["all"] += 1

    return {
        "items": items[: max(1, min(int(limit), 500))],
        "total": len(items),
        "bucket_counts": dict(counts),
        "open_channel_customer_id": oc_id,
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
