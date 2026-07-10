"""BACKLOG-061-U-B3a — bulk distributor promote via CSV map or system mint.

Loops the single-row promote service. Never auto-creates dim_distributor.
Partial success: per-row commit; one failure does not abort the rest.
Mirrors customer_bulk_promote.py.
"""

from __future__ import annotations

from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dimensions import DimDistributor
from app.services.distributor_code_mint import mint_next_distributor_code
from app.services.distributor_promote import (
    DistributorPromoteError,
    _norm_code,
    confirm_distributor_promote,
    preview_distributor_promote,
)

BATCH_MAX_ROWS = 500
BulkPromoteMode = Literal["map", "mint"]


def _row_base(
    *,
    tmp_code: str,
    new_code: str,
    note: str | None,
    distributor_id: int | None = None,
) -> dict[str, Any]:
    return {
        "tmp_code": tmp_code,
        "new_code": new_code,
        "note": (note or "").strip() or None,
        "distributor_id": distributor_id,
        "status": "blocked",
        "reasons": [],
        "collision": None,
        "warnings": [],
        "outcome": None,
    }


async def _resolve_tmp_distributor(db: AsyncSession, tmp_code: str) -> DimDistributor | None:
    key = _norm_code(tmp_code).lower()
    if not key:
        return None
    return (
        await db.execute(select(DimDistributor).where(func.lower(DimDistributor.code) == key))
    ).scalars().first()


def _mark_intra_batch_duplicates(
    results: list[dict[str, Any]],
    *,
    mode: BulkPromoteMode,
) -> None:
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

    if mode == "map":
        for idxs in new_counts.values():
            if len(idxs) < 2:
                continue
            for i in idxs:
                results[i]["status"] = "blocked"
                if "intra_batch_duplicate_new" not in results[i]["reasons"]:
                    results[i]["reasons"].append("intra_batch_duplicate_new")


async def run_distributor_bulk_promote(
    db: AsyncSession,
    *,
    rows: list[dict[str, Any]],
    dry_run: bool,
    mode: BulkPromoteMode = "map",
) -> dict[str, Any]:
    """Preview or confirm a batch of promotes.

    mode=map: ``{tmp_code, new_code, note?}`` — blank new_code → skipped_blank.
    mode=mint: ``{tmp_code, note?}`` — new_code must be blank; service mints DIST-######.
    """
    if mode not in ("map", "mint"):
        raise DistributorPromoteError(
            f"Unsupported mode {mode!r}",
            status_code=422,
            code="invalid_mode",
        )

    if len(rows) > BATCH_MAX_ROWS:
        raise DistributorPromoteError(
            f"Too many rows (max {BATCH_MAX_ROWS})",
            status_code=422,
            code="batch_too_large",
        )

    results: list[dict[str, Any]] = []
    for raw in rows:
        tmp = _norm_code(raw.get("tmp_code"))
        new = _norm_code(raw.get("new_code"))
        note = raw.get("note")
        results.append(
            _row_base(tmp_code=tmp, new_code=new, note=note if isinstance(note, str) else None)
        )

    _mark_intra_batch_duplicates(results, mode=mode)

    mint_reserved: set[str] = set()
    mint_start_seq: int | None = None

    for r in results:
        if r["status"] == "blocked" and r["reasons"]:
            continue

        if not r["tmp_code"]:
            r["status"] = "blocked"
            r["reasons"].append("tmp_code_blank")
            continue

        if mode == "mint":
            if r["new_code"]:
                r["status"] = "blocked"
                r["reasons"].append("new_code_not_allowed_in_mint")
                r["outcome"] = "blocked"
                continue
        else:
            if not r["new_code"]:
                r["status"] = "skipped_blank"
                r["reasons"] = []
                continue

        code_u = r["tmp_code"].upper()
        if not code_u.startswith("TMP-DIST-"):
            r["status"] = "blocked"
            r["reasons"].append("tmp_code_not_tmp_dist")
            r["outcome"] = "blocked"
            continue

        row = await _resolve_tmp_distributor(db, r["tmp_code"])
        if row is None:
            r["status"] = "blocked"
            r["reasons"].append("tmp_code_not_found")
            r["outcome"] = "blocked"
            continue

        r["distributor_id"] = int(row.id)

        if mode == "mint":
            disp = (getattr(row, "no_code_disposition", None) or "").strip().lower()
            if disp:
                r["status"] = "blocked"
                r["reasons"].append(f"disposition_{disp}")
                r["outcome"] = "blocked"
                continue
            try:
                minted, used_seq = await mint_next_distributor_code(
                    db,
                    dry_run=dry_run,
                    reserved=mint_reserved,
                    start_seq=mint_start_seq if dry_run else None,
                )
            except DistributorPromoteError as exc:
                r["status"] = "blocked"
                r["reasons"].append(exc.code)
                r["outcome"] = "blocked"
                continue
            r["new_code"] = minted
            mint_reserved.add(minted.lower())
            if dry_run:
                mint_start_seq = used_seq + 1

        if dry_run:
            try:
                preview = await preview_distributor_promote(
                    db, distributor_id=int(row.id), new_code=r["new_code"]
                )
            except DistributorPromoteError as exc:
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

        try:
            applied = await confirm_distributor_promote(
                db,
                distributor_id=int(row.id),
                new_code=r["new_code"],
                note=r.get("note"),
            )
            r["status"] = "applied"
            r["outcome"] = "applied"
            r["reasons"] = []
            r["warnings"] = list(applied.get("warnings") or [])
            r["old_code"] = applied.get("old_code")
            r["new_status"] = applied.get("new_status")
        except DistributorPromoteError as exc:
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
        "mode": mode,
        "rows": results,
        "summary": summary,
    }
