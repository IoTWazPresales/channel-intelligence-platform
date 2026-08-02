"""Absorb duplicate Open Channel dim_customer rows onto canonical OPEN_CHANNEL.

The general customer merge engines refuse OPEN_CHANNEL as survivor (safety).
This steward-repair path is the only allowed absorb-into-OPEN_CHANNEL write:
losers must be the explicit duplicate ids Warren approved, survivor must be the
canonical ``code=OPEN_CHANNEL`` row.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.dimensions import DimCustomer
from app.services.commercial_planner.open_channel_customer import OPEN_CHANNEL_CUSTOMER_CODE
from app.services.customer_full_repoint import (
    CustomerFullRepointAbortError,
    count_customer_fk_refs,
    repoint_customer_footprint_full,
)


class OpenChannelAbsorbError(ValueError):
    pass


def resolve_open_channel_id(db: Session) -> int:
    row = db.scalar(select(DimCustomer).where(DimCustomer.code == OPEN_CHANNEL_CUSTOMER_CODE))
    if row is None:
        raise OpenChannelAbsorbError("Canonical OPEN_CHANNEL customer missing")
    return int(row.id)


def preview_absorb_into_open_channel(
    db: Session,
    *,
    loser_ids: list[int],
    audit_note: str,
    expected_survivor_id: int | None = None,
) -> dict[str, Any]:
    note = (audit_note or "").strip()
    if not note:
        raise OpenChannelAbsorbError("audit_note is required")
    losers = sorted({int(x) for x in loser_ids})
    if not losers:
        raise OpenChannelAbsorbError("loser_ids required")

    survivor_id = resolve_open_channel_id(db)
    if expected_survivor_id is not None and int(expected_survivor_id) != survivor_id:
        raise OpenChannelAbsorbError(
            f"expected_survivor_id={expected_survivor_id} but OPEN_CHANNEL id={survivor_id}"
        )
    if survivor_id in losers:
        raise OpenChannelAbsorbError("OPEN_CHANNEL cannot be listed as a loser")

    survivor = db.get(DimCustomer, survivor_id)
    assert survivor is not None

    loser_plans: list[dict[str, Any]] = []
    already_redirected: list[int] = []
    for lid in losers:
        row = db.get(DimCustomer, lid)
        if row is None:
            raise OpenChannelAbsorbError(f"loser {lid} not found")
        if row.merged_into_customer_id is not None:
            if int(row.merged_into_customer_id) == survivor_id:
                already_redirected.append(lid)
                continue
            raise OpenChannelAbsorbError(
                f"loser {lid} already merged into {row.merged_into_customer_id} (not OPEN_CHANNEL)"
            )
        if (row.code or "").strip().upper() == OPEN_CHANNEL_CUSTOMER_CODE:
            raise OpenChannelAbsorbError(f"loser {lid} also has code OPEN_CHANNEL — halt")
        refs = count_customer_fk_refs(db, lid)
        loser_plans.append(
            {
                "customer_id": lid,
                "customer_code": row.code,
                "customer_name": row.name,
                "customer_status": row.customer_status,
                "fk_breakdown": [{"label": k, "count": v} for k, v in sorted(refs.items()) if v],
                "action": "repoint_and_soft_redirect_to_OPEN_CHANNEL",
            }
        )

    return {
        "dry_run": True,
        "merge_kind": "open_channel_absorb",
        "survivor_id": survivor_id,
        "survivor_code": OPEN_CHANNEL_CUSTOMER_CODE,
        "loser_ids": losers,
        "pending_loser_ids": [int(p["customer_id"]) for p in loser_plans],
        "already_redirected_ids": already_redirected,
        "loser_plans": loser_plans,
        "audit_note": note,
    }


def confirm_absorb_into_open_channel(
    db: Session,
    *,
    loser_ids: list[int],
    audit_note: str,
    performed_by: str | None = None,
    expected_survivor_id: int | None = None,
) -> dict[str, Any]:
    preview = preview_absorb_into_open_channel(
        db,
        loser_ids=loser_ids,
        audit_note=audit_note,
        expected_survivor_id=expected_survivor_id,
    )
    kid = int(preview["survivor_id"])
    survivor = db.get(DimCustomer, kid)
    if survivor is None or survivor.code != OPEN_CHANNEL_CUSTOMER_CODE:
        raise OpenChannelAbsorbError("OPEN_CHANNEL survivor missing at apply time")

    stamp = datetime.now(timezone.utc).isoformat()
    actor = (performed_by or "steward").strip() or "steward"
    merge_line = (
        f"[open-channel absorb {stamp}] survivor={kid}; losers={preview['loser_ids']}; "
        f"by={actor}; note={audit_note.strip()[:400]}"
    )
    prior = (survivor.notes_summary or "").strip()
    survivor.notes_summary = f"{prior}\n{merge_line}".strip()[:512]
    db.add(survivor)

    repoint_stats: list[dict[str, Any]] = []
    soft_redirected: list[int] = list(preview.get("already_redirected_ids") or [])
    try:
        for plan in preview["loser_plans"]:
            lid = int(plan["customer_id"])
            expected = {str(x["label"]): int(x["count"]) for x in plan.get("fk_breakdown") or []}
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
        raise OpenChannelAbsorbError(str(exc)) from exc

    if preview["loser_plans"]:
        db.commit()
    return {
        "dry_run": False,
        "merge_kind": "open_channel_absorb",
        "survivor_id": kid,
        "loser_ids": list(preview["loser_ids"]),
        "pending_loser_ids": list(preview.get("pending_loser_ids") or []),
        "already_redirected_ids": list(preview.get("already_redirected_ids") or []),
        "repoint_stats": repoint_stats,
        "soft_redirected_customer_ids": soft_redirected,
        "audit_note": audit_note.strip(),
    }
