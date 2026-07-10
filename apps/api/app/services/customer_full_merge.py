"""Full customer merge (name-similarity groups) — preview + confirm, modelled on alias-scope merge."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.dimensions import DimCustomer
from app.services.commercial_planner.open_channel_customer import OPEN_CHANNEL_CUSTOMER_CODE
from app.services.customer_duplicate_groups import (
    _CustomerRow,
    build_duplicate_groups,
    survivor_hint_sort_key,
)
from app.services.customer_fk_discovery import discover_customer_fk_columns, extra_customer_ref_specs
from app.services.customer_full_repoint import (
    CustomerFullRepointAbortError,
    count_customer_fk_refs,
    repoint_customer_footprint_full,
)

_LEGAL_FORM_PATTERN = re.compile(
    r"\b(?:pty|ltd|cc|inc|llc|corp|corporation|limited|proprietary)\b",
    re.IGNORECASE,
)


class CustomerFullMergeError(ValueError):
    pass


def _load_all_customer_rows(db: Session) -> list[_CustomerRow]:
    rows = db.execute(
        select(
            DimCustomer.id,
            DimCustomer.code,
            DimCustomer.name,
            DimCustomer.customer_status,
            DimCustomer.created_at,
        )
        .where(DimCustomer.merged_into_customer_id.is_(None))
        .order_by(DimCustomer.id.asc())
    ).all()
    return [
        _CustomerRow(
            id=int(r.id),
            code=str(r.code),
            name=str(r.name),
            customer_status=str(r.customer_status or ""),
            created_at=r.created_at,
        )
        for r in rows
    ]


def _members_for_similarity_key(db: Session, similarity_key: str) -> list[_CustomerRow]:
    key = (similarity_key or "").strip()
    if not key:
        raise CustomerFullMergeError("similarity_key is required")
    for group in build_duplicate_groups(_load_all_customer_rows(db)):
        if group["similarity_key"] == key:
            return list(group["members"])
    raise CustomerFullMergeError(f"No duplicate group found for similarity_key={key!r}")


def _default_survivor_id(members: list[_CustomerRow]) -> int:
    if len(members) < 2:
        raise CustomerFullMergeError("Group must have at least 2 members")
    return sorted(members, key=survivor_hint_sort_key)[0].id


def _assert_survivor_valid(db: Session, *, survivor_id: int, member_ids: list[int]) -> DimCustomer:
    if int(survivor_id) not in member_ids:
        raise CustomerFullMergeError(f"survivor_id {survivor_id} is not a member of this group")
    survivor = db.get(DimCustomer, int(survivor_id))
    if survivor is None:
        raise CustomerFullMergeError(f"survivor_id {survivor_id} not found")
    if survivor.code == OPEN_CHANNEL_CUSTOMER_CODE:
        raise CustomerFullMergeError("OPEN_CHANNEL cannot be a merge survivor")
    return survivor


def _reject_non_customer_entities(member_ids: list[int]) -> None:
    """Products and distributors are out of scope — only dim_customer ids allowed."""
    # Callers pass dim_customer ids from duplicate groups; explicit guard for API misuse.
    if not member_ids or any(int(x) <= 0 for x in member_ids):
        raise CustomerFullMergeError("customer_ids must be positive dim_customer ids")


def _legal_form_ambiguity_flags(members: list[_CustomerRow]) -> list[str]:
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
    cols = discover_customer_fk_columns(db)
    extras = extra_customer_ref_specs()
    return {
        "pg_constraint_fk_columns": [f"{t}.{c}" for t, c in cols],
        "extra_ref_specs": [f"{t}.{c} ({w})" for t, c, w in extras],
        "note": "commercial_lineup_case_po has no customer_id FK — PO links repoint via purchase_order only",
    }


def preview_customer_full_merge(
    db: Session,
    *,
    similarity_key: str,
    survivor_id: int | None,
    audit_note: str,
    customer_ids: list[int] | None = None,
) -> dict[str, Any]:
    note = (audit_note or "").strip()
    if not note:
        raise CustomerFullMergeError("audit_note is required")

    members = _members_for_similarity_key(db, similarity_key)
    member_ids = [m.id for m in members]
    if customer_ids is not None:
        provided = sorted({int(x) for x in customer_ids})
        if provided != sorted(member_ids):
            raise CustomerFullMergeError("customer_ids must match the duplicate group members")
    _reject_non_customer_entities(member_ids)

    kid = int(survivor_id) if survivor_id is not None else _default_survivor_id(members)
    _assert_survivor_valid(db, survivor_id=kid, member_ids=member_ids)
    losers = [int(x) for x in member_ids if int(x) != kid]

    loser_plans: list[dict[str, Any]] = []
    for lid in losers:
        fk_breakdown = [
            {"label": k, "count": v} for k, v in sorted(count_customer_fk_refs(db, lid).items())
        ]
        loser_plans.append(
            {
                "customer_id": lid,
                "customer_code": next((m.code for m in members if m.id == lid), None),
                "customer_name": next((m.name for m in members if m.id == lid), None),
                "fk_breakdown": fk_breakdown,
                "action": "repoint_and_soft_redirect",
            }
        )

    return {
        "dry_run": True,
        "merge_kind": "customer_full",
        "similarity_key": similarity_key,
        "survivor_id": kid,
        "loser_ids": losers,
        "member_ids": member_ids,
        "loser_plans": loser_plans,
        "ambiguity_flags": _legal_form_ambiguity_flags(members),
        "fk_enumeration": _fk_enumeration_report(db),
        "audit_note": note,
    }


def preview_customer_full_merge_bulk(
    db: Session,
    *,
    groups: list[dict[str, Any]],
    audit_note: str,
) -> dict[str, Any]:
    note = (audit_note or "").strip()
    if not note:
        raise CustomerFullMergeError("audit_note is required")
    if not groups:
        raise CustomerFullMergeError("At least one group is required")

    previews: list[dict[str, Any]] = []
    total_losers = 0
    total_fk_rows = 0
    for g in groups:
        sk = str(g.get("similarity_key") or "").strip()
        sid = g.get("survivor_id")
        p = preview_customer_full_merge(
            db,
            similarity_key=sk,
            survivor_id=int(sid) if sid is not None else None,
            audit_note=note,
            customer_ids=g.get("customer_ids"),
        )
        previews.append(p)
        total_losers += len(p.get("loser_ids") or [])
        for lp in p.get("loser_plans") or []:
            total_fk_rows += sum(int(x.get("count") or 0) for x in lp.get("fk_breakdown") or [])

    return {
        "dry_run": True,
        "merge_kind": "customer_full_bulk",
        "group_count": len(previews),
        "total_loser_customers": total_losers,
        "total_fk_rows_to_repoint": total_fk_rows,
        "group_previews": previews,
        "fk_enumeration": _fk_enumeration_report(db),
        "audit_note": note,
    }


def confirm_customer_full_merge_sync(
    db: Session,
    *,
    similarity_key: str,
    survivor_id: int,
    audit_note: str,
    performed_by: str | None = None,
    customer_ids: list[int] | None = None,
) -> dict[str, Any]:
    preview = preview_customer_full_merge(
        db,
        similarity_key=similarity_key,
        survivor_id=survivor_id,
        audit_note=audit_note,
        customer_ids=customer_ids,
    )
    kid = int(preview["survivor_id"])
    losers = [int(x) for x in preview["loser_ids"]]
    survivor = db.get(DimCustomer, kid)
    if survivor is None:
        raise CustomerFullMergeError("Survivor missing at apply time")

    stamp = datetime.now(timezone.utc).isoformat()
    actor = (performed_by or "steward").strip() or "steward"
    merge_line = (
        f"[customer-full merge {stamp}] key={similarity_key}; survivor={kid}; losers={losers}; "
        f"by={actor}; note={audit_note.strip()[:400]}"
    )
    prior = (survivor.notes_summary or "").strip()
    survivor.notes_summary = f"{prior}\n{merge_line}".strip()[:512]
    db.add(survivor)

    repoint_stats: list[dict[str, Any]] = []
    soft_redirected: list[int] = []

    try:
        for lid in losers:
            lp = next((x for x in preview["loser_plans"] if int(x["customer_id"]) == lid), None)
            expected = {
                str(x["label"]): int(x["count"]) for x in (lp.get("fk_breakdown") if lp else [])
            }
            stats = repoint_customer_footprint_full(
                db,
                loser_id=lid,
                keeper_id=kid,
                expected_counts=expected,
            )
            repoint_stats.append({"customer_id": lid, **stats})

            loser_row = db.get(DimCustomer, lid)
            if loser_row is not None:
                loser_row.merged_into_customer_id = kid
                if loser_row.customer_status not in ("merged", "inactive"):
                    loser_row.customer_status = "merged"
                db.add(loser_row)
                soft_redirected.append(lid)
            db.flush()
    except CustomerFullRepointAbortError as exc:
        db.rollback()
        raise CustomerFullMergeError(str(exc)) from exc

    db.commit()
    return {
        "dry_run": False,
        "merge_kind": "customer_full",
        "similarity_key": similarity_key,
        "survivor_id": kid,
        "loser_ids": losers,
        "repoint_stats": repoint_stats,
        "soft_redirected_customer_ids": soft_redirected,
        "audit_note": audit_note.strip(),
    }
