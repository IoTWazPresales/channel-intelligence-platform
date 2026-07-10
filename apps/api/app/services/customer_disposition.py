"""BACKLOG-061-U3 — no-code disposition batch (park / exclude / clear).

Mutates no_code_disposition only. Never changes customer_status, code, or FKs.
Never auto-creates dim_customer.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dimensions import DimCustomer
from app.services.customer_promote import CustomerPromoteError, TMP_CUSTOMER_CODE_PREFIX, _norm_code

DISPOSITION_BATCH_MAX = 500
DispositionAction = Literal["parked", "excluded", "clear"]
ALLOWED_DISPOSITIONS = frozenset({"parked", "excluded", "clear"})


def _is_tmp_customer_code(code: str) -> bool:
    return code.startswith(f"{TMP_CUSTOMER_CODE_PREFIX}-")


async def run_customer_disposition_batch(
    db: AsyncSession,
    *,
    customer_ids: list[int],
    disposition: str,
    note: str | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    action = (disposition or "").strip().lower()
    if action not in ALLOWED_DISPOSITIONS:
        raise CustomerPromoteError(
            f"Invalid disposition {disposition!r}; expected parked|excluded|clear",
            status_code=422,
            code="invalid_disposition",
        )
    if len(customer_ids) > DISPOSITION_BATCH_MAX:
        raise CustomerPromoteError(
            f"Too many ids (max {DISPOSITION_BATCH_MAX})",
            status_code=422,
            code="batch_too_large",
        )

    target_value: str | None = None if action == "clear" else action
    note_clean = (note or "").strip() or None
    results: list[dict[str, Any]] = []

    for raw_id in customer_ids:
        try:
            cid = int(raw_id)
        except (TypeError, ValueError):
            results.append(
                {
                    "customer_id": raw_id,
                    "tmp_code": None,
                    "status": "blocked",
                    "outcome": "blocked",
                    "reasons": ["not_found"],
                    "no_code_disposition": None,
                }
            )
            continue

        row = await db.get(DimCustomer, cid)
        if row is None:
            results.append(
                {
                    "customer_id": cid,
                    "tmp_code": None,
                    "status": "blocked",
                    "outcome": "blocked",
                    "reasons": ["not_found"],
                    "no_code_disposition": None,
                }
            )
            continue

        code = _norm_code(row.code)
        current = (row.no_code_disposition or "").strip().lower() or None
        base = {
            "customer_id": int(row.id),
            "tmp_code": code,
            "status": "blocked",
            "outcome": None,
            "reasons": [],
            "no_code_disposition": current,
            "customer_status": row.customer_status,
        }

        if row.merged_into_customer_id is not None:
            base["reasons"] = ["row_is_merged_loser"]
            base["outcome"] = "blocked"
            results.append(base)
            continue

        if not _is_tmp_customer_code(code):
            base["reasons"] = ["code_not_tmp_cust"]
            base["outcome"] = "blocked"
            results.append(base)
            continue

        if target_value is None:
            if current is None:
                base["status"] = "skipped"
                base["outcome"] = "skipped"
                base["reasons"] = []
                results.append(base)
                continue
        else:
            if current == target_value:
                base["status"] = "skipped"
                base["outcome"] = "skipped"
                base["reasons"] = [f"already_set:{current}"]
                results.append(base)
                continue

        if dry_run:
            base["status"] = "ready"
            base["outcome"] = None
            base["reasons"] = []
            base["would_set"] = target_value
            results.append(base)
            continue

        prior_status = row.customer_status
        row.no_code_disposition = target_value
        if note_clean:
            prior = (row.notes_summary or "").strip()
            stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            label = "clear" if target_value is None else target_value
            line = f"[{stamp} {label}] {note_clean}"
            row.notes_summary = f"{prior}\n{line}".strip()[:512]
        db.add(row)
        await db.commit()
        await db.refresh(row)
        # Explicit invariant: status never mutated
        assert row.customer_status == prior_status
        base["status"] = "applied"
        base["outcome"] = "applied"
        base["reasons"] = []
        base["no_code_disposition"] = row.no_code_disposition
        base["customer_status"] = row.customer_status
        results.append(base)

    summary = {
        "ready": sum(1 for x in results if x["status"] == "ready"),
        "applied": sum(1 for x in results if x["status"] == "applied"),
        "blocked": sum(1 for x in results if x["status"] == "blocked"),
        "skipped": sum(1 for x in results if x["status"] == "skipped"),
        "total": len(results),
    }
    return {
        "dry_run": dry_run,
        "disposition": action,
        "rows": results,
        "summary": summary,
    }
