"""Repair leftover FKs on merged dim_customer losers via the canonical full repointer.

Does not write a parallel repointer. Each loser is all-or-nothing
(``repoint_customer_footprint_full`` + ``_assert_zero_loser_refs``).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.customer_fk_discovery import discover_customer_fk_columns
from app.services.customer_full_repoint import (
    _assert_zero_loser_refs,
    count_customer_fk_refs,
    repoint_customer_footprint_full,
)
from app.services.merge_redirect import follow_customer_merge_redirect_sync

# Match the leftover audit: skip the self-redirect column on dim_customer.
_LEFTOVER_SKIP = {("dim_customer", "merged_into_customer_id")}

EXPECTED_DIRTY_LOSERS = 9
EXPECTED_LEFTOVER_ROWS = 3266
COMPUSPEED_LOSER_ID = 1152

WINNER_SNAPSHOT_IDS: tuple[tuple[int, str], ...] = (
    (788, "Esquire"),
    (299, "Amazon"),
)


class LeftoverRepairDriftError(RuntimeError):
    """Preview totals do not match the locked audit (9 / 3266)."""


def leftover_fk_counts(db: Session, customer_id: int) -> dict[str, int]:
    """Per-FK leftover counts excluding ``dim_customer.merged_into_customer_id``."""
    cid = int(customer_id)
    counts: dict[str, int] = {}
    for table, column in discover_customer_fk_columns(db):
        if (table, column) in _LEFTOVER_SKIP:
            continue
        n = int(
            db.execute(
                text(f"SELECT count(*) FROM {table} WHERE {column} = :cid"),
                {"cid": cid},
            ).scalar()
            or 0
        )
        if n:
            counts[f"{table}.{column}"] = n
    return counts


def list_merged_losers(db: Session) -> list[tuple[int, str, str, int | None, str]]:
    rows = db.execute(
        text(
            """
            SELECT id, code, name, merged_into_customer_id, coalesce(customer_status, '')
            FROM dim_customer
            WHERE merged_into_customer_id IS NOT NULL
               OR lower(coalesce(customer_status, '')) = 'merged'
            ORDER BY id
            """
        )
    ).all()
    return [
        (int(r[0]), str(r[1] or ""), str(r[2] or ""), int(r[3]) if r[3] is not None else None, str(r[4] or ""))
        for r in rows
    ]


def preview_leftover_repair(db: Session) -> dict[str, Any]:
    losers = list_merged_losers(db)
    dirty: list[dict[str, Any]] = []
    total_rows = 0
    for lid, code, name, _mid, status in losers:
        counts = leftover_fk_counts(db, lid)
        nsum = int(sum(counts.values()))
        if nsum <= 0:
            continue
        winner_id = follow_customer_merge_redirect_sync(db, lid)
        w = db.execute(
            text("SELECT id, code, name FROM dim_customer WHERE id = :i"),
            {"i": winner_id},
        ).first()
        item = {
            "loser_id": lid,
            "loser_code": code,
            "loser_name": name,
            "loser_status": status,
            "winner_id": int(winner_id) if winner_id is not None else None,
            "winner_code": str(w[1]) if w is not None else None,
            "winner_name": str(w[2]) if w is not None else None,
            "row_count": nsum,
            "fk_counts": counts,
            "compuspeed_unexplained": lid == COMPUSPEED_LOSER_ID,
        }
        dirty.append(item)
        total_rows += nsum
    dirty.sort(key=lambda x: -int(x["row_count"]))
    return {
        "database": db.execute(text("SELECT current_database()")).scalar(),
        "merged_loser_count": len(losers),
        "dirty_loser_count": len(dirty),
        "total_leftover_rows": total_rows,
        "losers": dirty,
        "winner_snapshots": {
            label: winner_snapshot(db, cid) for cid, label in WINNER_SNAPSHOT_IDS
        },
    }


def winner_snapshot(db: Session, customer_id: int) -> dict[str, int]:
    cid = int(customer_id)
    return {
        "customer_id": cid,
        "cpor_case": int(
            db.execute(text("SELECT count(*) FROM cpor_case WHERE customer_id = :c"), {"c": cid}).scalar() or 0
        ),
        "commercial_lineup_line": int(
            db.execute(
                text("SELECT count(*) FROM commercial_lineup_line WHERE customer_id = :c"),
                {"c": cid},
            ).scalar()
            or 0
        ),
        "fact_customer_sellthrough": int(
            db.execute(
                text("SELECT count(*) FROM fact_customer_sellthrough WHERE customer_id = :c"),
                {"c": cid},
            ).scalar()
            or 0
        ),
    }


def assert_preview_matches_audit(preview: dict[str, Any]) -> None:
    dirty = int(preview["dirty_loser_count"])
    rows = int(preview["total_leftover_rows"])
    if dirty != EXPECTED_DIRTY_LOSERS or rows != EXPECTED_LEFTOVER_ROWS:
        raise LeftoverRepairDriftError(
            f"leftover drift: dirty={dirty} rows={rows} "
            f"(expected {EXPECTED_DIRTY_LOSERS}/{EXPECTED_LEFTOVER_ROWS})"
        )


def leftover_row_total_across_merged_losers(db: Session) -> int:
    total = 0
    for lid, _code, _name, _mid, _status in list_merged_losers(db):
        total += int(sum(leftover_fk_counts(db, lid).values()))
    return total


def repair_dirty_losers(
    db: Session,
    *,
    preview: dict[str, Any] | None = None,
    require_audit_match: bool = True,
) -> dict[str, Any]:
    """Repoint each dirty loser onto its merge-chain survivor. One transaction."""
    prev = preview or preview_leftover_repair(db)
    if require_audit_match:
        assert_preview_matches_audit(prev)
    results: list[dict[str, Any]] = []
    for item in prev["losers"]:
        lid = int(item["loser_id"])
        kid = item["winner_id"]
        if kid is None or int(kid) == lid:
            raise LeftoverRepairDriftError(f"loser {lid} has no distinct survivor")
        stats = repoint_customer_footprint_full(
            db,
            loser_id=lid,
            keeper_id=int(kid),
            expected_counts=item["fk_counts"],
        )
        _assert_zero_loser_refs(db, lid)
        # leftover definition (audit skip) must also be empty
        remaining = leftover_fk_counts(db, lid)
        if remaining:
            raise LeftoverRepairDriftError(f"loser {lid} leftover after repoint: {remaining}")
        results.append(
            {
                "loser_id": lid,
                "winner_id": int(kid),
                "compuspeed_unexplained": bool(item["compuspeed_unexplained"]),
                "stats": stats,
            }
        )
    return {
        "repaired": results,
        "repaired_count": len(results),
        "leftover_rows_after": leftover_row_total_across_merged_losers(db),
        "strict_zero_refs": {
            int(item["loser_id"]): count_customer_fk_refs(db, int(item["loser_id"]))
            for item in prev["losers"]
        },
        "winner_snapshots_after": {
            label: winner_snapshot(db, cid) for cid, label in WINNER_SNAPSHOT_IDS
        },
    }
