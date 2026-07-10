"""BACKLOG-061 Unit BP1 — bulk customer promote via CSV/paste mapping.

Loops the single-row promote service. No mint path. No schema changes.
Partial success: per-row commit; one failure does not abort the rest.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dimensions import DimCustomer
from app.services.customer_promote import (
    CustomerPromoteError,
    _norm_code,
    confirm_customer_promote,
    preview_customer_promote,
)

BATCH_MAX_ROWS = 500


def _row_base(
    *,
    tmp_code: str,
    new_code: str,
    note: str | None,
    customer_id: int | None = None,
) -> dict[str, Any]:
    return {
        "tmp_code": tmp_code,
        "new_code": new_code,
        "note": (note or "").strip() or None,
        "customer_id": customer_id,
        "status": "blocked",
        "reasons": [],
        "collision": None,
        "warnings": [],
        "outcome": None,
    }


async def _resolve_tmp_customer(db: AsyncSession, tmp_code: str) -> DimCustomer | None:
    key = _norm_code(tmp_code).lower()
    if not key:
        return None
    return (
        await db.execute(select(DimCustomer).where(func.lower(DimCustomer.code) == key))
    ).scalars().first()


def _mark_intra_batch_duplicates(results: list[dict[str, Any]]) -> None:
    """Duplicate tmp_code or new_code (case-insensitive) blocks ALL involved rows."""
    tmp_counts: dict[str, list[int]] = {}
    new_counts: dict[str, list[int]] = {}
    for i, r in enumerate(results):
        t = _norm_code(r["tmp_code"]).lower()
        if t:
            tmp_counts.setdefault(t, []).append(i)
        n = _norm_code(r["new_code"]).lower()
        if n:
            new_counts.setdefault(n, []).append(i)

    for idxs in tmp_counts.values():
        if len(idxs) < 2:
            continue
        for i in idxs:
            results[i]["status"] = "blocked"
            if "intra_batch_duplicate_tmp" not in results[i]["reasons"]:
                results[i]["reasons"].append("intra_batch_duplicate_tmp")

    for idxs in new_counts.values():
        if len(idxs) < 2:
            continue
        for i in idxs:
            results[i]["status"] = "blocked"
            if "intra_batch_duplicate_new" not in results[i]["reasons"]:
                results[i]["reasons"].append("intra_batch_duplicate_new")


async def run_customer_bulk_promote(
    db: AsyncSession,
    *,
    rows: list[dict[str, Any]],
    dry_run: bool,
) -> dict[str, Any]:
    """Preview or confirm a batch of tmp_code → new_code mappings.

    ``rows`` items: ``{tmp_code, new_code, note?}``.
    Blank ``new_code`` → ``skipped_blank`` (not an error).
    """
    if len(rows) > BATCH_MAX_ROWS:
        raise CustomerPromoteError(
            f"Too many rows (max {BATCH_MAX_ROWS})",
            status_code=422,
            code="batch_too_large",
        )

    results: list[dict[str, Any]] = []
    for raw in rows:
        tmp = _norm_code(raw.get("tmp_code"))
        new = _norm_code(raw.get("new_code"))
        note = raw.get("note")
        results.append(_row_base(tmp_code=tmp, new_code=new, note=note if isinstance(note, str) else None))

    _mark_intra_batch_duplicates(results)

    for r in results:
        if r["status"] == "blocked" and r["reasons"]:
            continue

        if not r["tmp_code"]:
            r["status"] = "blocked"
            r["reasons"].append("tmp_code_blank")
            continue

        if not r["new_code"]:
            r["status"] = "skipped_blank"
            r["reasons"] = []
            continue

        code_u = r["tmp_code"].upper()
        if not code_u.startswith("TMP-CUST-"):
            r["status"] = "blocked"
            r["reasons"].append("tmp_code_not_tmp_cust")
            r["outcome"] = "blocked"
            continue

        row = await _resolve_tmp_customer(db, r["tmp_code"])
        if row is None:
            r["status"] = "blocked"
            r["reasons"].append("tmp_code_not_found")
            r["outcome"] = "blocked"
            continue

        r["customer_id"] = int(row.id)

        if dry_run:
            try:
                preview = await preview_customer_promote(
                    db, customer_id=int(row.id), new_code=r["new_code"]
                )
            except CustomerPromoteError as exc:
                r["status"] = "blocked"
                r["reasons"].append(exc.code)
                continue
            r["collision"] = preview.get("collision")
            r["warnings"] = list(preview.get("warnings") or [])
            if preview.get("can_confirm"):
                r["status"] = "ready"
                r["reasons"] = []
            else:
                r["status"] = "blocked"
                reasons = list((preview.get("eligibility") or {}).get("reasons") or [])
                if preview.get("collision"):
                    reasons.append("code_collision")
                r["reasons"] = reasons or ["not_eligible"]
            continue

        # Confirm path: re-preview inside confirm_customer_promote guards drift.
        try:
            applied = await confirm_customer_promote(
                db,
                customer_id=int(row.id),
                new_code=r["new_code"],
                note=r.get("note"),
            )
            r["status"] = "applied"
            r["outcome"] = "applied"
            r["reasons"] = []
            r["warnings"] = list(applied.get("warnings") or [])
            r["old_code"] = applied.get("old_code")
            r["new_status"] = applied.get("new_status")
        except CustomerPromoteError as exc:
            r["status"] = "blocked"
            r["outcome"] = "blocked"
            r["reasons"] = [exc.code]
            if exc.code == "code_collision":
                r["collision"] = {"note": exc.message}

    for r in results:
        if r["status"] == "skipped_blank":
            r["outcome"] = "skipped"
        elif r["status"] == "blocked" and r.get("outcome") is None:
            r["outcome"] = "blocked"
        elif r["status"] == "ready":
            r["outcome"] = None

    summary = {
        "ready": sum(1 for x in results if x["status"] == "ready"),
        "blocked": sum(1 for x in results if x["status"] == "blocked"),
        "skipped": sum(1 for x in results if x["status"] == "skipped_blank"),
        "applied": sum(1 for x in results if x["status"] == "applied"),
        "total": len(results),
    }
    return {
        "dry_run": dry_run,
        "rows": results,
        "summary": summary,
    }
