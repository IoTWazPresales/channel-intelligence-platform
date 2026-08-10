"""BACKLOG-010 — truncate legacy ``product_attribute_value`` (PAV) rows.

Canonical product specs live on ``dim_product.specs_json``. PAV is write-only
legacy EAV (gated by ``PM_WRITE_LEGACY_EAV``, default off). This script:

1. Asserts ``current_database() = 'cip'`` (or ``--allow-db NAME``).
2. Refuses to run when ``PM_WRITE_LEGACY_EAV`` / settings.pm_write_legacy_eav is on
   (unless ``--force-with-legacy-eav-on``).
3. Optionally writes a JSONL restore snapshot of remaining rows.
4. ``TRUNCATE product_attribute_value RESTART IDENTITY`` when ``--confirm``.

Usage (from ``apps/api``, venv active)::

  python scripts/ops/drop_legacy_product_attribute_value.py
  python scripts/ops/drop_legacy_product_attribute_value.py --backup-path ../../.tmp/pav_backup.jsonl
  python scripts/ops/drop_legacy_product_attribute_value.py --confirm --backup-path ../../.tmp/pav_backup.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

from app.core.config import get_settings
from app.db.session_sync import SessionLocal


def _snapshot_rows(db, limit: int | None = None) -> list[dict]:
    sql = """
        SELECT id, catalog_product_id, attribute_definition_id, value_json,
               created_at, updated_at
        FROM product_attribute_value
        ORDER BY id
    """
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    rows = db.execute(text(sql)).mappings().all()
    out: list[dict] = []
    for r in rows:
        d = dict(r)
        for k, v in list(d.items()):
            if hasattr(v, "isoformat"):
                d[k] = v.isoformat()
        out.append(d)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--confirm",
        action="store_true",
        help="Execute TRUNCATE (otherwise preview only).",
    )
    ap.add_argument(
        "--allow-db",
        default="cip",
        help="Required current_database() name (default: cip).",
    )
    ap.add_argument(
        "--backup-path",
        type=Path,
        default=None,
        help="Write JSONL snapshot of current PAV rows before truncate.",
    )
    ap.add_argument(
        "--backup-max-rows",
        type=int,
        default=None,
        help="Cap snapshot rows (default: all). Use for smoke dumps of huge tables.",
    )
    ap.add_argument(
        "--force-with-legacy-eav-on",
        action="store_true",
        help="Allow truncate even if pm_write_legacy_eav is enabled.",
    )
    args = ap.parse_args()

    settings = get_settings()
    if settings.pm_write_legacy_eav and not args.force_with_legacy_eav_on:
        print(
            "REFUSE: pm_write_legacy_eav / PM_WRITE_LEGACY_EAV is ON. "
            "Turn it off, or pass --force-with-legacy-eav-on.",
            file=sys.stderr,
        )
        return 2

    with SessionLocal() as db:
        db_name = db.execute(text("SELECT current_database()")).scalar()
        if db_name != args.allow_db:
            print(
                f"REFUSE: current_database()={db_name!r}, expected {args.allow_db!r}",
                file=sys.stderr,
            )
            return 2

        before = int(db.execute(text("SELECT COUNT(*) FROM product_attribute_value")).scalar() or 0)
        size = db.execute(
            text("SELECT pg_size_pretty(pg_total_relation_size('product_attribute_value'))")
        ).scalar()
        print(
            json.dumps(
                {
                    "database": db_name,
                    "pm_write_legacy_eav": bool(settings.pm_write_legacy_eav),
                    "pav_count_before": before,
                    "relation_size": size,
                    "confirm": bool(args.confirm),
                    "ts_utc": datetime.now(timezone.utc).isoformat(),
                },
                indent=2,
            )
        )

        if args.backup_path is not None:
            args.backup_path.parent.mkdir(parents=True, exist_ok=True)
            rows = _snapshot_rows(db, limit=args.backup_max_rows)
            with args.backup_path.open("w", encoding="utf-8") as fh:
                meta = {
                    "_meta": True,
                    "database": db_name,
                    "pav_count": before,
                    "rows_written": len(rows),
                    "capped": args.backup_max_rows is not None and before > len(rows),
                    "ts_utc": datetime.now(timezone.utc).isoformat(),
                }
                fh.write(json.dumps(meta) + "\n")
                for row in rows:
                    fh.write(json.dumps(row, default=str) + "\n")
            print(f"backup_written={args.backup_path} rows={len(rows)}")

        if not args.confirm:
            print("preview_only: re-run with --confirm to TRUNCATE product_attribute_value")
            return 0

        db.execute(text("TRUNCATE TABLE product_attribute_value RESTART IDENTITY"))
        db.commit()
        after = int(db.execute(text("SELECT COUNT(*) FROM product_attribute_value")).scalar() or 0)
        print(json.dumps({"pav_count_after": after, "status": "truncated_ok"}))
        if after != 0:
            print("ERROR: truncate left rows", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
