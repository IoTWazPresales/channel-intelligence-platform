"""BACKLOG-124 — tokenless lineup customer stamp (no alias, no invented token).

Empty ``customer_token`` lines cannot use Mechanism C (global alias). Steward stamps
``customer_id`` directly on selected ``line_ids`` with explicit confirm. Ship/PO
customers are hints only — never preselected auto-apply; never auto-create dims.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.commercial_lineup import CommercialLineupLine
from app.models.dimensions import DimCustomer
from app.services.commercial_planner.lineup_customer_token_stamp import (
    CustomerTokenStampError,
    _clear_unknown_customer,
)
from app.services.steward_audit import record_steward_audit


def _is_blank_token(ln: CommercialLineupLine) -> bool:
    return not (ln.customer_token or "").strip()


async def preview_tokenless_customer_stamp(
    db: AsyncSession,
    *,
    line_ids: list[int],
    target_customer_id: int,
) -> dict[str, Any]:
    ids = [int(x) for x in line_ids]
    if not ids:
        raise CustomerTokenStampError("line_ids required")
    target = await db.get(DimCustomer, int(target_customer_id))
    if target is None:
        raise CustomerTokenStampError(f"target customer {target_customer_id} does not exist")

    lines = list(
        (
            await db.execute(
                select(CommercialLineupLine).where(CommercialLineupLine.id.in_(ids))
            )
        ).scalars().all()
    )
    found = {int(ln.id) for ln in lines}
    missing = [i for i in ids if i not in found]
    if missing:
        raise CustomerTokenStampError(f"unknown line_ids: {missing[:20]}")

    eligible: list[CommercialLineupLine] = []
    rejected: list[dict[str, Any]] = []
    for ln in lines:
        if ln.customer_id is not None:
            rejected.append({"line_id": int(ln.id), "reason": "customer_id_already_set"})
            continue
        if not _is_blank_token(ln):
            rejected.append({"line_id": int(ln.id), "reason": "customer_token_not_blank"})
            continue
        eligible.append(ln)

    eligible_ids = [int(ln.id) for ln in eligible]
    return {
        "line_count": len(eligible),
        "eligible_line_ids": eligible_ids,
        "rejected_count": len(rejected),
        "rejected": rejected[:50],
        "target_customer_id": int(target_customer_id),
        "target_customer_label": f"{target.name or target.code or target.id} (id {target.id})",
        "sample_line_ids": eligible_ids[:20],
        "case_ids": sorted({int(ln.case_id) for ln in eligible}),
        "mints_alias": False,
        "writes_customer_token": False,
    }


async def apply_tokenless_customer_stamp(
    db: AsyncSession,
    user: dict | None,
    *,
    line_ids: list[int],
    target_customer_id: int,
    reason: str,
    commit: bool = True,
) -> dict[str, Any]:
    reason_s = (reason or "").strip()
    if not reason_s:
        raise CustomerTokenStampError("reason required")

    preview = await preview_tokenless_customer_stamp(
        db, line_ids=line_ids, target_customer_id=target_customer_id
    )
    if preview["line_count"] < 1:
        raise CustomerTokenStampError(
            "no eligible empty-token lines to stamp "
            f"(rejected={preview['rejected_count']})"
        )

    eligible_ids = [int(x) for x in preview.get("eligible_line_ids") or []]
    if not eligible_ids:
        raise CustomerTokenStampError("no eligible empty-token lines to stamp")
    # Re-load eligible only
    lines = list(
        (
            await db.execute(
                select(CommercialLineupLine).where(CommercialLineupLine.id.in_(eligible_ids))
            )
        ).scalars().all()
    )
    per_line: list[dict[str, Any]] = []
    prior_customer_ids: dict[str, int | None] = {}
    for ln in lines:
        if ln.customer_id is not None or not _is_blank_token(ln):
            continue
        prior = int(ln.customer_id) if ln.customer_id is not None else None
        ln.customer_id = int(target_customer_id)
        ln.diagnostic_codes = _clear_unknown_customer(
            list(ln.diagnostic_codes) if ln.diagnostic_codes else None
        )
        # Explicit: do not invent customer_token; do not mint alias
        per_line.append(
            {
                "line_id": int(ln.id),
                "case_id": int(ln.case_id),
                "prior_customer_id": prior,
                "customer_id": int(target_customer_id),
            }
        )
        prior_customer_ids[str(ln.id)] = prior

    await record_steward_audit(
        db,
        user,
        action="lineup_tokenless_customer_stamp",
        importer="commercial_planner",
        entity_type="lineup_line",
        entity_token=None,
        target_dim="dim_customer",
        target_id=int(target_customer_id),
        payload={
            "reason": reason_s,
            "line_ids": [p["line_id"] for p in per_line],
            "prior_customer_ids": prior_customer_ids,
            "target_customer_id": int(target_customer_id),
            "mints_alias": False,
            "writes_customer_token": False,
            "rejected": preview["rejected"],
        },
        commit=False,
    )
    if commit:
        await db.commit()
    else:
        await db.flush()
    return {
        "stamped_count": len(per_line),
        "per_line": per_line,
        "target_customer_id": int(target_customer_id),
        "rejected_count": preview["rejected_count"],
        "mints_alias": False,
    }
