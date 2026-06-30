"""Full distributor merge (name-similarity groups) — preview + confirm."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.dimensions import DimDistributor
from app.services.commercial_planner.unassigned_distributor import UNASSIGNED_DISTRIBUTOR_CODE
from app.services.distributor_duplicate_groups import (
    _DistributorRow,
    build_duplicate_groups,
    survivor_hint_sort_key,
)
from app.services.distributor_fk_discovery import discover_distributor_fk_columns, extra_distributor_ref_specs
from app.services.distributor_full_repoint import (
    DistributorFullRepointAbortError,
    count_distributor_fk_refs,
    repoint_distributor_footprint_full,
)
from app.services.distributor_merge_po_consolidation import plan_distributor_owned_po_actions

_LEGAL_FORM_PATTERN = re.compile(
    r"\b(?:pty|ltd|cc|inc|llc|corp|corporation|limited|proprietary)\b",
    re.IGNORECASE,
)


class DistributorFullMergeError(ValueError):
    pass


def _load_all_distributor_rows(db: Session) -> list[_DistributorRow]:
    rows = db.execute(
        select(
            DimDistributor.id,
            DimDistributor.code,
            DimDistributor.name,
            DimDistributor.distributor_status,
            DimDistributor.created_at,
        )
        .where(DimDistributor.merged_into_distributor_id.is_(None))
        .order_by(DimDistributor.id.asc())
    ).all()
    return [
        _DistributorRow(
            id=int(r.id),
            code=str(r.code),
            name=str(r.name),
            distributor_status=str(getattr(r, "distributor_status", None) or "active"),
            created_at=r.created_at,
        )
        for r in rows
    ]


def _members_for_similarity_key(db: Session, similarity_key: str) -> list[_DistributorRow]:
    key = (similarity_key or "").strip()
    if not key:
        raise DistributorFullMergeError("similarity_key is required")
    for group in build_duplicate_groups(_load_all_distributor_rows(db)):
        if group["similarity_key"] == key:
            return list(group["members"])
    raise DistributorFullMergeError(f"No duplicate group found for similarity_key={key!r}")


def _default_survivor_id(members: list[_DistributorRow]) -> int:
    if len(members) < 2:
        raise DistributorFullMergeError("Group must have at least 2 members")
    return sorted(members, key=survivor_hint_sort_key)[0].id


def _assert_survivor_valid(db: Session, *, survivor_id: int, member_ids: list[int]) -> DimDistributor:
    if int(survivor_id) not in member_ids:
        raise DistributorFullMergeError(f"survivor_id {survivor_id} is not a member of this group")
    survivor = db.get(DimDistributor, int(survivor_id))
    if survivor is None:
        raise DistributorFullMergeError(f"survivor_id {survivor_id} not found")
    if survivor.code == UNASSIGNED_DISTRIBUTOR_CODE:
        raise DistributorFullMergeError("UNASSIGNED distributor cannot be a merge survivor")
    return survivor


def _legal_form_ambiguity_flags(members: list[_DistributorRow]) -> list[str]:
    forms: set[str] = set()
    for m in members:
        hits = {x.lower() for x in _LEGAL_FORM_PATTERN.findall(m.name or "")}
        if hits:
            forms |= hits
    if len(forms) > 1:
        return [f"multiple_legal_forms:{','.join(sorted(forms))}"]
    raw_names = {(m.name or "").strip().lower() for m in members}
    if len(raw_names) > 1 and len(forms) >= 1:
        return ["name_variants_with_legal_form"]
    return []


def _fk_enumeration_report(db: Session) -> dict[str, Any]:
    cols = discover_distributor_fk_columns(db)
    extras = extra_distributor_ref_specs()
    return {
        "pg_constraint_fk_columns": [f"{t}.{c}" for t, c in cols],
        "extra_ref_specs": [f"{t}.{c} ({w})" for t, c, w in extras],
        "note": (
            "purchase_order.distributor_id handled by PO consolidation sub-engine "
            "(UNIQUE po_number_norm + distributor_id)"
        ),
    }


def preview_distributor_full_merge(
    db: Session,
    *,
    similarity_key: str,
    survivor_id: int | None,
    audit_note: str,
    distributor_ids: list[int] | None = None,
) -> dict[str, Any]:
    note = (audit_note or "").strip()
    if not note:
        raise DistributorFullMergeError("audit_note is required")

    members = _members_for_similarity_key(db, similarity_key)
    member_ids = [m.id for m in members]
    if distributor_ids is not None:
        provided = sorted({int(x) for x in distributor_ids})
        if provided != sorted(member_ids):
            raise DistributorFullMergeError("distributor_ids must match the duplicate group members")

    kid = int(survivor_id) if survivor_id is not None else _default_survivor_id(members)
    _assert_survivor_valid(db, survivor_id=kid, member_ids=member_ids)
    losers = [int(x) for x in member_ids if int(x) != kid]

    loser_plans: list[dict[str, Any]] = []
    for lid in losers:
        fk_breakdown = [
            {"label": k, "count": v} for k, v in sorted(count_distributor_fk_refs(db, lid).items())
        ]
        po_plans = plan_distributor_owned_po_actions(db, keeper_distributor_id=kid, loser_distributor_id=lid)
        loser_plans.append(
            {
                "distributor_id": lid,
                "distributor_code": next((m.code for m in members if m.id == lid), None),
                "distributor_name": next((m.name for m in members if m.id == lid), None),
                "fk_breakdown": fk_breakdown,
                "po_plans": po_plans,
                "action": "repoint_and_soft_redirect",
            }
        )

    return {
        "dry_run": True,
        "merge_kind": "distributor_full",
        "similarity_key": similarity_key,
        "survivor_id": kid,
        "loser_ids": losers,
        "member_ids": member_ids,
        "loser_plans": loser_plans,
        "ambiguity_flags": _legal_form_ambiguity_flags(members),
        "fk_enumeration": _fk_enumeration_report(db),
        "audit_note": note,
    }


def preview_distributor_full_merge_bulk(
    db: Session,
    *,
    groups: list[dict[str, Any]],
    audit_note: str,
) -> dict[str, Any]:
    note = (audit_note or "").strip()
    if not note:
        raise DistributorFullMergeError("audit_note is required")
    if not groups:
        raise DistributorFullMergeError("At least one group is required")

    previews: list[dict[str, Any]] = []
    total_losers = 0
    total_fk_rows = 0
    total_po_consolidations = 0
    for g in groups:
        sk = str(g.get("similarity_key") or "").strip()
        sid = g.get("survivor_id")
        p = preview_distributor_full_merge(
            db,
            similarity_key=sk,
            survivor_id=int(sid) if sid is not None else None,
            audit_note=note,
            distributor_ids=g.get("distributor_ids"),
        )
        previews.append(p)
        total_losers += len(p.get("loser_ids") or [])
        for lp in p.get("loser_plans") or []:
            total_fk_rows += sum(int(x.get("count") or 0) for x in lp.get("fk_breakdown") or [])
            total_po_consolidations += sum(
                1 for pp in lp.get("po_plans") or [] if pp.get("action") == "consolidate_into_po"
            )

    return {
        "dry_run": True,
        "merge_kind": "distributor_full_bulk",
        "group_count": len(previews),
        "total_loser_distributors": total_losers,
        "total_fk_rows_to_repoint": total_fk_rows,
        "total_po_consolidations": total_po_consolidations,
        "group_previews": previews,
        "fk_enumeration": _fk_enumeration_report(db),
        "audit_note": note,
    }


def confirm_distributor_full_merge_sync(
    db: Session,
    *,
    similarity_key: str,
    survivor_id: int,
    audit_note: str,
    performed_by: str | None = None,
    distributor_ids: list[int] | None = None,
) -> dict[str, Any]:
    preview = preview_distributor_full_merge(
        db,
        similarity_key=similarity_key,
        survivor_id=survivor_id,
        audit_note=audit_note,
        distributor_ids=distributor_ids,
    )
    kid = int(preview["survivor_id"])
    losers = [int(x) for x in preview["loser_ids"]]
    survivor = db.get(DimDistributor, kid)
    if survivor is None:
        raise DistributorFullMergeError("Survivor missing at apply time")

    stamp = datetime.now(timezone.utc).isoformat()
    actor = (performed_by or "steward").strip() or "steward"
    merge_line = (
        f"[distributor-full merge {stamp}] key={similarity_key}; survivor={kid}; losers={losers}; "
        f"by={actor}; note={audit_note.strip()[:400]}"
    )
    prior = (survivor.merge_note or "").strip()
    survivor.merge_note = f"{prior}\n{merge_line}".strip() if prior else merge_line.strip()
    db.add(survivor)

    repoint_stats: list[dict[str, Any]] = []
    soft_redirected: list[int] = []

    try:
        for lid in losers:
            lp = next((x for x in preview["loser_plans"] if int(x["distributor_id"]) == lid), None)
            expected = {
                str(x["label"]): int(x["count"]) for x in (lp.get("fk_breakdown") if lp else [])
            }
            po_plans = lp.get("po_plans") if lp else None
            stats = repoint_distributor_footprint_full(
                db,
                loser_id=lid,
                keeper_id=kid,
                expected_counts=expected,
                po_plans=po_plans,
            )
            repoint_stats.append({"distributor_id": lid, **stats})

            loser_row = db.get(DimDistributor, lid)
            if loser_row is not None:
                loser_row.merged_into_distributor_id = kid
                status = getattr(loser_row, "distributor_status", None)
                if status not in ("merged", "inactive"):
                    loser_row.distributor_status = "merged"
                db.add(loser_row)
                soft_redirected.append(lid)
            db.flush()
    except DistributorFullRepointAbortError as exc:
        db.rollback()
        raise DistributorFullMergeError(str(exc)) from exc

    db.commit()
    return {
        "dry_run": False,
        "merge_kind": "distributor_full",
        "similarity_key": similarity_key,
        "survivor_id": kid,
        "loser_ids": losers,
        "repoint_stats": repoint_stats,
        "soft_redirected_distributor_ids": soft_redirected,
        "audit_note": audit_note.strip(),
    }
