"""Seal past customer merges: mint approved aliases from each merged record's name to its keeper.

Merges confirmed before the alias seal existed (BACKLOG-081) left the merged names unsealed, so a
file that still carries an old name can come back as steward work. This mints the missing aliases.
Test-fixture customers and OPEN_CHANNEL are left untouched. A name already aliased to a third
customer is reported as a conflict and never overwritten. Running it twice mints nothing new.

Usage (from apps/api):
  python scripts/ops/backfill_merged_customer_alias_seals.py                    # dry run, prints the plan
  python scripts/ops/backfill_merged_customer_alias_seals.py --apply --expect-db cip_n0095
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import text

_API_ROOT = Path(__file__).resolve().parents[2]
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from app.db.session_sync import SessionLocal  # noqa: E402
from app.services.customer_merge_alias_seal import backfill_merged_customer_alias_seals  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write the aliases (default is a dry run)")
    parser.add_argument("--expect-db", default=None, help="required with --apply; must equal current_database()")
    parser.add_argument("--detail", action="store_true", help="print every minted, moved and conflicting alias")
    args = parser.parse_args(argv)

    with SessionLocal() as db:
        current = str(db.execute(text("SELECT current_database()")).scalar() or "")
        print(f"current_database()={current}")
        if args.apply and args.expect_db != current:
            print(f"refused: --apply needs --expect-db {current!r} (got {args.expect_db!r})")
            return 2
        out = backfill_merged_customer_alias_seals(db, dry_run=not args.apply)

    summary = {k: v for k, v in out.items() if not k.startswith("alias_seal_")}
    print(json.dumps(summary, indent=2))
    for item in out["alias_seal_conflicts"]:
        print("conflict:", json.dumps(item, default=str))
    if args.detail:
        for key in ("alias_seal_minted", "alias_seal_reassigned", "alias_seal_skipped"):
            for item in out[key]:
                print(f"{key}:", json.dumps(item, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
