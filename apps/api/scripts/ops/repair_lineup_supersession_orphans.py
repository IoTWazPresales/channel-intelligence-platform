#!/usr/bin/env python3
"""One-time repair: restore orphan superseded lineup cases on cip (preview then apply)."""
from __future__ import annotations

import argparse
import json
import sys

from sqlalchemy import text

from app.db.session_sync import SessionLocal
from app.models.commercial_lineup import CommercialLineupCase
from app.services.commercial_planner.lineup_case_supersession import (
    find_orphan_superseded_cases,
    restore_superseded_cases,
    superseded_child_summaries,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write restores (default: preview only)")
    args = parser.parse_args()

    with SessionLocal() as db:
        dbname = db.scalar(text("SELECT current_database()"))
        if dbname != "cip":
            print(f"STOP: current_database()={dbname!r}, expected cip", file=sys.stderr)
            return 2

        orphans = find_orphan_superseded_cases(db)
        preview = superseded_child_summaries(orphans)
        print(f"orphan_superseded_cases: {len(preview)}")
        print(json.dumps(preview, indent=2, default=str))

        if not args.apply:
            print("\nPreview only — re-run with --apply to restore to draft_imported")
            return 0

        if not orphans:
            print("Nothing to restore")
            return 0

        restored = restore_superseded_cases(db, orphans)
        db.commit()
        print("\nrestored:")
        print(json.dumps(restored, indent=2, default=str))

        remaining = find_orphan_superseded_cases(db)
        print(f"\nafter: orphan_superseded_cases={len(remaining)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
