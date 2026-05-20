"""dim_product duplicate cleanup: diagnostic (default) or delete identical higher-id rows.

Compares all columns except id, created_at, updated_at. Groups rows by lower(trim(sku)).

Usage (same Python env as API; from repo root often via ``node scripts/run-api-python.cjs``):

  python scripts/dim_product_duplicate_cleanup.py           # diagnostic only
  python scripts/dim_product_duplicate_cleanup.py --apply # deletes (requires current_database() == 'cip')

Do not pass ``--apply`` until you have reviewed the diagnostic output.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.session_sync import SessionLocal, sync_engine
from app.models.dimensions import DimProduct

_COMPARE_SKIP = frozenset({"id", "created_at", "updated_at"})


def _norm_sku(s: str | None) -> str:
    if s is None:
        return ""
    return str(s).strip().lower()


def _row_snapshot(obj: DimProduct) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for col in DimProduct.__table__.columns:
        if col.name in _COMPARE_SKIP:
            continue
        val = getattr(obj, col.name)
        if col.name == "specs_json" and val is not None:
            out[col.name] = json.dumps(val, sort_keys=True, default=str)
        else:
            out[col.name] = val
    return out


def _snap_equal(a: dict[str, Any], b: dict[str, Any]) -> bool:
    keys = set(a) | set(b)
    for k in keys:
        if a.get(k) != b.get(k):
            return False
    return True


def run_diagnostic(db: Session) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (duplicate_group_summaries, differing_pairs_for_review)."""
    rows = list(db.scalars(select(DimProduct).order_by(DimProduct.id)).all())
    by_norm: dict[str, list[DimProduct]] = defaultdict(list)
    for p in rows:
        by_norm[_norm_sku(p.sku)].append(p)

    summaries: list[dict[str, Any]] = []
    differing: list[dict[str, Any]] = []

    for sku_norm, group in sorted(by_norm.items(), key=lambda x: x[0]):
        if len(group) < 2:
            continue
        keeper = min(group, key=lambda r: r.id)
        ksnap = _row_snapshot(keeper)
        summaries.append(
            {
                "sku_norm": sku_norm,
                "count": len(group),
                "ids": [r.id for r in sorted(group, key=lambda r: r.id)],
                "sku_raw": [r.sku for r in sorted(group, key=lambda r: r.id)],
            }
        )
        for other in group:
            if other.id == keeper.id:
                continue
            osnap = _row_snapshot(other)
            if not _snap_equal(ksnap, osnap):
                differing.append(
                    {
                        "sku_norm": sku_norm,
                        "keeper_id": keeper.id,
                        "other_id": other.id,
                        "keeper_sku": keeper.sku,
                        "other_sku": other.sku,
                        "keeper_snapshot": ksnap,
                        "other_snapshot": osnap,
                    }
                )

    return summaries, differing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Delete duplicate rows with higher id when snapshot matches keeper (lower id).",
    )
    args = parser.parse_args()

    with sync_engine.connect() as conn:
        dbname = conn.execute(text("SELECT current_database()")).scalar_one()
    print(f"current_database={dbname!r}")

    with SessionLocal() as db:
        summaries, differing = run_diagnostic(db)

        print(f"\nDuplicate SKU groups (by lower(trim(sku))): {len(summaries)}")
        for s in summaries[:200]:
            print(f"  sku_norm={s['sku_norm']!r} count={s['count']} ids={s['ids']} sku_raw={s['sku_raw']}")
        if len(summaries) > 200:
            print(f"  ... ({len(summaries) - 200} more groups omitted)")

        print(f"\nRows that differ within a duplicate group (manual review): {len(differing)}")
        for d in differing[:50]:
            print(
                f"  sku_norm={d['sku_norm']!r} keeper_id={d['keeper_id']} other_id={d['other_id']} "
                f"keeper_sku={d['keeper_sku']!r} other_sku={d['other_sku']!r}"
            )
        if len(differing) > 50:
            print(f"  ... ({len(differing) - 50} more omitted)")

        if not args.apply:
            print("\nNo deletes performed (pass --apply to execute identical-row cleanup).")
            return 0

        if str(dbname).strip().lower() != "cip":
            print("Refusing --apply: expected current_database() == 'cip'.", file=sys.stderr)
            return 2

        to_delete: list[int] = []
        rows = list(db.scalars(select(DimProduct).order_by(DimProduct.id)).all())
        by_norm: dict[str, list[DimProduct]] = defaultdict(list)
        for p in rows:
            by_norm[_norm_sku(p.sku)].append(p)

        for _sku_norm, group in by_norm.items():
            if len(group) < 2:
                continue
            keeper = min(group, key=lambda r: r.id)
            ksnap = _row_snapshot(keeper)
            for other in group:
                if other.id <= keeper.id:
                    continue
                if _snap_equal(ksnap, _row_snapshot(other)):
                    to_delete.append(other.id)

        if not to_delete:
            print("\n--apply: nothing to delete (no identical higher-id duplicates).")
            db.commit()
            return 0

        print(f"\n--apply: deleting {len(to_delete)} row(s): {sorted(to_delete)}")
        for pid in to_delete:
            row = db.get(DimProduct, pid)
            if row is not None:
                db.delete(row)
        db.commit()
        print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
