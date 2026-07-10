"""BACKLOG-061 B3 — distributor promote-in-place (same id, code reassignment).

Mutates an existing TMP-DIST row only. Never auto-creates dim_distributor.
Never touches merged_into_distributor_id, FKs, or aliases.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dimensions import DimDistributor

PROMOTE_TARGET_STATUS = "active"
PROMOTE_ALLOW_TMP_ACTIVE_WITH_CONFIRM = True
PROMOTE_AUDIT_MODE = "api_response_only"

TMP_DISTRIBUTOR_CODE_PREFIX = "TMP-DIST"

BULK_UPSERT_TMP_DUPLICATE_WARNING = (
    "Future bulk upserts that still send the old TMP code will create a NEW distributor row; "
    "prefer a source-token alias or update source files."
)


class DistributorPromoteError(Exception):
    def __init__(self, message: str, *, status_code: int = 400, code: str = "promote_rejected"):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


def _norm_code(raw: str | None) -> str:
    return (raw or "").strip()


def _is_tmp_distributor_code(code: str) -> bool:
    return code.startswith(f"{TMP_DISTRIBUTOR_CODE_PREFIX}-")


async def _find_code_owner(
    db: AsyncSession,
    *,
    new_code: str,
    exclude_distributor_id: int,
) -> DimDistributor | None:
    key = new_code.strip().lower()
    if not key:
        return None
    return (
        await db.execute(
            select(DimDistributor).where(
                DimDistributor.id != int(exclude_distributor_id),
                func.lower(DimDistributor.code) == key,
            )
        )
    ).scalars().first()


def _eligibility(row: DimDistributor) -> dict[str, Any]:
    code = _norm_code(row.code)
    status = (row.distributor_status or "").strip().lower()
    merged = row.merged_into_distributor_id is not None
    reasons: list[str] = []
    if merged:
        reasons.append("row_is_merged_loser")
    if not _is_tmp_distributor_code(code):
        reasons.append("code_not_tmp_dist")
    if status == "merged":
        reasons.append("status_merged")

    admin_mint_edge = False
    # All TMP-DIST on cip are active today — treat active TMP as the normal path.
    if _is_tmp_distributor_code(code) and not merged and status == "active":
        admin_mint_edge = True
        if not PROMOTE_ALLOW_TMP_ACTIVE_WITH_CONFIRM:
            reasons.append("tmp_active_not_allowed")

    if _is_tmp_distributor_code(code) and not merged and status not in ("unverified", "active"):
        reasons.append(f"status_not_eligible:{status or 'blank'}")

    disp = (getattr(row, "no_code_disposition", None) or "").strip().lower()
    if disp:
        reasons.append(f"disposition_{disp}")

    eligible = (
        not reasons
        and _is_tmp_distributor_code(code)
        and not merged
        and status in ("unverified", "active")
    )
    return {
        "eligible": eligible,
        "reasons": reasons,
        "admin_mint_edge": admin_mint_edge,
        "old_code": code,
        "old_status": row.distributor_status,
    }


async def preview_distributor_promote(
    db: AsyncSession,
    *,
    distributor_id: int,
    new_code: str,
) -> dict[str, Any]:
    row = await db.get(DimDistributor, distributor_id)
    if row is None:
        raise DistributorPromoteError("Distributor not found", status_code=404, code="not_found")

    target = _norm_code(new_code)
    if not target:
        raise DistributorPromoteError("new_code is required", status_code=400, code="blank_code")
    if _is_tmp_distributor_code(target):
        raise DistributorPromoteError(
            "new_code must be a real business code, not TMP-DIST-*",
            status_code=400,
            code="new_code_is_tmp",
        )
    if len(target) > 64:
        raise DistributorPromoteError("new_code exceeds 64 characters", status_code=400, code="code_too_long")

    elig = _eligibility(row)
    owner = await _find_code_owner(db, new_code=target, exclude_distributor_id=int(row.id))
    collision: dict[str, Any] | None = None
    if owner is not None:
        collision = {
            "distributor_id": int(owner.id),
            "code": owner.code,
            "distributor_status": owner.distributor_status,
            "merged_into_distributor_id": owner.merged_into_distributor_id,
            "note": (
                "dim_distributor.code is UNIQUE; merged losers retain codes, so this code cannot be "
                "reassigned until the other row's code is changed."
            ),
        }

    warnings: list[str] = []
    if elig["eligible"] or elig.get("admin_mint_edge"):
        warnings.append(BULK_UPSERT_TMP_DUPLICATE_WARNING)
        if elig.get("admin_mint_edge"):
            warnings.append(
                "TMP-DIST rows are typically status=active (mint default). Promote requires confirm=true."
            )

    can_confirm = bool(elig["eligible"]) and collision is None
    return {
        "dry_run": True,
        "distributor_id": int(row.id),
        "new_code": target,
        "promote_target_status": PROMOTE_TARGET_STATUS,
        "audit_mode": PROMOTE_AUDIT_MODE,
        "eligibility": elig,
        "collision": collision,
        "warnings": warnings,
        "can_confirm": can_confirm,
        "applied": False,
    }


async def confirm_distributor_promote(
    db: AsyncSession,
    *,
    distributor_id: int,
    new_code: str,
    note: str | None = None,
) -> dict[str, Any]:
    preview = await preview_distributor_promote(db, distributor_id=distributor_id, new_code=new_code)
    if not preview["can_confirm"]:
        if preview.get("collision"):
            raise DistributorPromoteError(
                f"new_code already owned by distributor_id={preview['collision']['distributor_id']}",
                status_code=409,
                code="code_collision",
            )
        reasons = preview["eligibility"].get("reasons") or ["not_eligible"]
        raise DistributorPromoteError(
            f"Distributor not eligible for promote: {', '.join(reasons)}",
            status_code=422,
            code="not_eligible",
        )

    row = await db.get(DimDistributor, distributor_id)
    assert row is not None
    old_code = row.code
    old_status = row.distributor_status
    target = preview["new_code"]

    if _norm_code(old_code).lower() == target.lower() and (old_status or "").lower() == PROMOTE_TARGET_STATUS:
        raise DistributorPromoteError(
            "Distributor already promoted to this code",
            status_code=409,
            code="already_promoted",
        )
    if not _is_tmp_distributor_code(_norm_code(old_code)):
        raise DistributorPromoteError(
            "Distributor already has a non-TMP code",
            status_code=409,
            code="already_promoted",
        )

    row.code = target
    row.distributor_status = PROMOTE_TARGET_STATUS
    if note and note.strip():
        prior = (row.merge_note or "").strip()
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        line = f"[{stamp} promote] {note.strip()}"
        row.merge_note = f"{prior}\n{line}".strip()
    db.add(row)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise DistributorPromoteError(
            "new_code conflict (unique constraint)",
            status_code=409,
            code="code_collision",
        ) from exc
    await db.refresh(row)

    return {
        "dry_run": False,
        "applied": True,
        "distributor_id": int(row.id),
        "old_code": old_code,
        "new_code": row.code,
        "old_status": old_status,
        "new_status": row.distributor_status,
        "merged_into_distributor_id": row.merged_into_distributor_id,
        "promoted_at": datetime.now(timezone.utc).isoformat(),
        "audit_mode": PROMOTE_AUDIT_MODE,
        "warnings": preview.get("warnings") or [],
        "note": (note or "").strip() or None,
    }
