"""BACKLOG-061 B1 — customer promote-in-place (same id, code reassignment).

Mutates an existing TMP-CUST row only. Never auto-creates dim_customer.
Never touches merged_into_customer_id, FKs, or aliases.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dimensions import DimCustomer

# Warren design §6 — flip these if decisions change (one-line).
PROMOTE_TARGET_STATUS = "active"
PROMOTE_ALLOW_TMP_ACTIVE_WITH_CONFIRM = True
PROMOTE_AUDIT_MODE = "api_response_only"  # no new columns

TMP_CUSTOMER_CODE_PREFIX = "TMP-CUST"

PROVISIONAL_REUSE_STOP_WARNING = (
    "Leaving unverified stops provisional reuse for this row; future imports may mint a duplicate."
)
BULK_UPSERT_TMP_DUPLICATE_WARNING = (
    "Future bulk upserts that still send the old TMP code will create a NEW customer row; "
    "prefer a source-token alias or update source files."
)


class CustomerPromoteError(Exception):
    def __init__(self, message: str, *, status_code: int = 400, code: str = "promote_rejected"):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


def _norm_code(raw: str | None) -> str:
    return (raw or "").strip()


def _is_tmp_customer_code(code: str) -> bool:
    return code.startswith(f"{TMP_CUSTOMER_CODE_PREFIX}-")


async def _find_code_owner(
    db: AsyncSession,
    *,
    new_code: str,
    exclude_customer_id: int,
) -> DimCustomer | None:
    """Any other row holding this code (case-insensitive). Unique constraint is exact;

    merge losers keep their codes, so a merged row still blocks reuse — design §3.2.4
    'merged collision allowed' is NOT implementable without renaming losers (schema/ops).
    """
    key = new_code.strip().lower()
    if not key:
        return None
    return (
        await db.execute(
            select(DimCustomer).where(
                DimCustomer.id != int(exclude_customer_id),
                func.lower(DimCustomer.code) == key,
            )
        )
    ).scalars().first()


def _eligibility(row: DimCustomer) -> dict[str, Any]:
    code = _norm_code(row.code)
    status = (row.customer_status or "").strip().lower()
    merged = row.merged_into_customer_id is not None

    reasons: list[str] = []
    if merged:
        reasons.append("row_is_merged_loser")
    if not _is_tmp_customer_code(code):
        reasons.append("code_not_tmp_cust")
    if status == "merged":
        reasons.append("status_merged")

    admin_mint_edge = False
    if _is_tmp_customer_code(code) and not merged and status == "active":
        admin_mint_edge = True
        if not PROMOTE_ALLOW_TMP_ACTIVE_WITH_CONFIRM:
            reasons.append("tmp_active_not_allowed")

    if _is_tmp_customer_code(code) and not merged and status not in ("unverified", "active"):
        reasons.append(f"status_not_eligible:{status or 'blank'}")

    disp = (getattr(row, "no_code_disposition", None) or "").strip().lower()
    if disp:
        reasons.append(f"disposition_{disp}")

    eligible = not reasons and _is_tmp_customer_code(code) and not merged and status in (
        "unverified",
        "active",
    )
    return {
        "eligible": eligible,
        "reasons": reasons,
        "admin_mint_edge": admin_mint_edge,
        "old_code": code,
        "old_status": row.customer_status,
    }


async def preview_customer_promote(
    db: AsyncSession,
    *,
    customer_id: int,
    new_code: str,
) -> dict[str, Any]:
    row = await db.get(DimCustomer, customer_id)
    if row is None:
        raise CustomerPromoteError("Customer not found", status_code=404, code="not_found")

    target = _norm_code(new_code)
    if not target:
        raise CustomerPromoteError("new_code is required", status_code=400, code="blank_code")
    if _is_tmp_customer_code(target):
        raise CustomerPromoteError(
            "new_code must be a real business code, not TMP-CUST-*",
            status_code=400,
            code="new_code_is_tmp",
        )
    if len(target) > 64:
        raise CustomerPromoteError("new_code exceeds 64 characters", status_code=400, code="code_too_long")

    elig = _eligibility(row)
    owner = await _find_code_owner(db, new_code=target, exclude_customer_id=int(row.id))
    collision: dict[str, Any] | None = None
    if owner is not None:
        collision = {
            "customer_id": int(owner.id),
            "code": owner.code,
            "customer_status": owner.customer_status,
            "merged_into_customer_id": owner.merged_into_customer_id,
            "note": (
                "dim_customer.code is UNIQUE; merged losers retain codes, so this code cannot be "
                "reassigned until the other row's code is changed (design §3.2.4 amendment)."
            ),
        }

    warnings: list[str] = []
    if elig["eligible"] or elig.get("admin_mint_edge"):
        if (row.customer_status or "").strip().lower() == "unverified":
            warnings.append(PROVISIONAL_REUSE_STOP_WARNING)
        warnings.append(BULK_UPSERT_TMP_DUPLICATE_WARNING)
        if elig.get("admin_mint_edge"):
            warnings.append(
                "Admin-mint edge: TMP-CUST with status=active — promote requires confirm=true "
                f"(PROMOTE_ALLOW_TMP_ACTIVE_WITH_CONFIRM={PROMOTE_ALLOW_TMP_ACTIVE_WITH_CONFIRM})."
            )

    can_confirm = bool(elig["eligible"]) and collision is None
    return {
        "dry_run": True,
        "customer_id": int(row.id),
        "new_code": target,
        "promote_target_status": PROMOTE_TARGET_STATUS,
        "audit_mode": PROMOTE_AUDIT_MODE,
        "eligibility": elig,
        "collision": collision,
        "warnings": warnings,
        "can_confirm": can_confirm,
        "applied": False,
    }


async def confirm_customer_promote(
    db: AsyncSession,
    *,
    customer_id: int,
    new_code: str,
    note: str | None = None,
) -> dict[str, Any]:
    preview = await preview_customer_promote(db, customer_id=customer_id, new_code=new_code)
    if not preview["can_confirm"]:
        if preview.get("collision"):
            raise CustomerPromoteError(
                f"new_code already owned by customer_id={preview['collision']['customer_id']}",
                status_code=409,
                code="code_collision",
            )
        reasons = preview["eligibility"].get("reasons") or ["not_eligible"]
        raise CustomerPromoteError(
            f"Customer not eligible for promote: {', '.join(reasons)}",
            status_code=422,
            code="not_eligible",
        )

    row = await db.get(DimCustomer, customer_id)
    assert row is not None
    old_code = row.code
    old_status = row.customer_status
    target = preview["new_code"]

    # Idempotency: already promoted to this code
    if _norm_code(old_code).lower() == target.lower() and (old_status or "").lower() == PROMOTE_TARGET_STATUS:
        raise CustomerPromoteError(
            "Customer already promoted to this code",
            status_code=409,
            code="already_promoted",
        )
    if not _is_tmp_customer_code(_norm_code(old_code)):
        raise CustomerPromoteError(
            "Customer already has a non-TMP code (already promoted or never provisional)",
            status_code=409,
            code="already_promoted",
        )

    row.code = target
    row.customer_status = PROMOTE_TARGET_STATUS
    # Never touch merged_into_customer_id
    if note and note.strip():
        prior = (row.notes_summary or "").strip()
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        line = f"[{stamp} promote] {note.strip()}"
        row.notes_summary = f"{prior}\n{line}".strip()[:512]
    db.add(row)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise CustomerPromoteError(
            "new_code conflict (unique constraint)",
            status_code=409,
            code="code_collision",
        ) from exc
    await db.refresh(row)

    return {
        "dry_run": False,
        "applied": True,
        "customer_id": int(row.id),
        "old_code": old_code,
        "new_code": row.code,
        "old_status": old_status,
        "new_status": row.customer_status,
        "merged_into_customer_id": row.merged_into_customer_id,
        "promoted_at": datetime.now(timezone.utc).isoformat(),
        "audit_mode": PROMOTE_AUDIT_MODE,
        "warnings": preview.get("warnings") or [],
        "note": (note or "").strip() or None,
    }
