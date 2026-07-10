"""BACKLOG-061-U-B3a — no-code disposition batch for distributors (park / exclude / clear).

Mutates no_code_disposition only. Never changes distributor_status, code, or FKs.
Never auto-creates dim_distributor. Mirrors customer_disposition.py.
Note stamps go on merge_note (distributor's existing note column; no notes_summary on dim).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dimensions import DimDistributor
from app.services.distributor_promote import (
    DistributorPromoteError,
    TMP_DISTRIBUTOR_CODE_PREFIX,
    _norm_code,
)

DISPOSITION_BATCH_MAX = 500
DispositionAction = Literal["parked", "excluded", "clear"]
ALLOWED_DISPOSITIONS = frozenset({"parked", "excluded", "clear"})


def _is_tmp_distributor_code(code: str) -> bool:
    return code.startswith(f"{TMP_DISTRIBUTOR_CODE_PREFIX}-")


async def run_distributor_disposition_batch(
    db: AsyncSession,
    *,
    distributor_ids: list[int],
    disposition: str,
    note: str | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    action = (disposition or "").strip().lower()
    if action not in ALLOWED_DISPOSITIONS:
        raise DistributorPromoteError(
            f"Invalid disposition {disposition!r}; expected parked|excluded|clear",
            status_code=422,
            code="invalid_disposition",
        )
    if len(distributor_ids) > DISPOSITION_BATCH_MAX:
        raise DistributorPromoteError(
            f"Too many ids (max {DISPOSITION_BATCH_MAX})",
            status_code=422,
            code="batch_too_large",
        )

    target_value: str | None = None if action == "clear" else action
    note_clean = (note or "").strip() or None
    results: list[dict[str, Any]] = []

    for raw_id in distributor_ids:
        try:
            did = int(raw_id)
        except (TypeError, ValueError):
            results.append(
                {
                    "distributor_id": raw_id,
                    "tmp_code": None,
                    "status": "blocked",
                    "outcome": "blocked",
                    "reasons": ["not_found"],
                    "no_code_disposition": None,
                }
            )
            continue

        row = await db.get(DimDistributor, did)
        if row is None:
            results.append(
                {
                    "distributor_id": did,
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
            "distributor_id": int(row.id),
            "tmp_code": code,
            "status": "blocked",
            "outcome": None,
            "reasons": [],
            "no_code_disposition": current,
            "distributor_status": row.distributor_status,
        }

        if row.merged_into_distributor_id is not None:
            base["reasons"] = ["row_is_merged_loser"]
            base["outcome"] = "blocked"
            results.append(base)
            continue

        if not _is_tmp_distributor_code(code):
            base["reasons"] = ["code_not_tmp_dist"]
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

        prior_status = row.distributor_status
        row.no_code_disposition = target_value
        if note_clean:
            prior = (row.merge_note or "").strip()
            stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            label = "clear" if target_value is None else target_value
            line = f"[{stamp} {label}] {note_clean}"
            row.merge_note = f"{prior}\n{line}".strip()
        db.add(row)
        await db.commit()
        await db.refresh(row)
        assert row.distributor_status == prior_status
        base["status"] = "applied"
        base["outcome"] = "applied"
        base["reasons"] = []
        base["no_code_disposition"] = row.no_code_disposition
        base["distributor_status"] = row.distributor_status
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
