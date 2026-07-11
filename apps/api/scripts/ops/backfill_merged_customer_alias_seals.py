"""Backfill global approved aliases for soft-redirected customers (post-merge seal).

Safety defaults:
  - dry-run only unless --apply AND --i-understand are both passed
  - refuses to run unless current_database() == 'cip' (or --allow-non-cip)
  - never overwrites a third-party alias (conflicts are reported only)

Usage (from apps/api, venv active):
  python scripts/ops/backfill_merged_customer_alias_seals.py
  python scripts/ops/backfill_merged_customer_alias_seals.py --limit 50
  python scripts/ops/backfill_merged_customer_alias_seals.py --apply --i-understand
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import text

# Ensure apps/api is on path when run as a script.
_API_ROOT = Path(__file__).resolve().parents[2]
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from app.db.session_sync import SessionLocal  # noqa: E402
from app.services.customer_merge_alias_seal import backfill_merged_customer_alias_seals  # noqa: E402


def _current_database(session) -> str:
    return str(session.execute(text("SELECT current_database()")).scalar() or "")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Perform writes (default is dry-run).",
    )
    parser.add_argument(
        "--i-understand",
        action="store_true",
        help="Required together with --apply to mint/reassign aliases on cip.",
    )
    parser.add_argument(
        "--allow-non-cip",
        action="store_true",
        help="Allow running against a database other than cip (still needs --apply for writes).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional cap on merged customers scanned (for smoke).",
    )
    parser.add_argument(
        "--json-out",
        type=str,
        default=None,
        help="Optional path to write full JSON report.",
    )
    args = parser.parse_args()

    dry_run = not args.apply
    if args.apply and not args.i_understand:
        print("Refusing --apply without --i-understand", file=sys.stderr)
        return 2

    with SessionLocal() as session:
        db_name = _current_database(session)
        if db_name != "cip" and not args.allow_non_cip:
            print(f"Refusing: current_database()={db_name!r} (expected 'cip')", file=sys.stderr)
            return 2
        print(f"database={db_name} dry_run={dry_run} limit={args.limit}")

        report = backfill_merged_customer_alias_seals(
            session,
            dry_run=dry_run,
            audit_note="ops backfill merged customer alias seal",
            limit=args.limit,
        )

    summary = {
        "dry_run": report["dry_run"],
        "merged_customers_scanned": report["merged_customers_scanned"],
        "survivors_touched": report["survivors_touched"],
        "would_mint_or_minted": report["would_mint_or_minted"],
        "would_reassign_or_reassigned": report["would_reassign_or_reassigned"],
        "conflicts": report["conflicts"],
        "skipped": report["skipped"],
    }
    print(json.dumps(summary, indent=2))

    # Show a small sample of conflicts / mints for human review.
    conflicts = report["alias_seal_conflicts"][:15]
    if conflicts:
        print("\nconflict sample (up to 15):")
        for c in conflicts:
            print(
                f"  loser={c.get('loser_id')} {c.get('loser_name')!r} "
                f"token={c.get('normalized_token')!r} "
                f"existing_customer={c.get('existing_customer_id')} "
                f"target={c.get('target_customer_id')}"
            )

    mints = report["alias_seal_minted"][:10]
    if mints:
        print("\nmint sample (up to 10):")
        for m in mints:
            print(
                f"  loser={m.get('loser_id')} token={m.get('normalized_token')!r} "
                f"raw={m.get('raw_token')!r}"
            )

    if args.json_out:
        out_path = Path(args.json_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"\nwrote {out_path}")

    if dry_run:
        print(
            "\nDry-run only. To apply after review:\n"
            "  python scripts/ops/backfill_merged_customer_alias_seals.py "
            "--apply --i-understand"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
