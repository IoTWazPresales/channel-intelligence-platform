"""Seed database. Default: catalog dimensions only (no sample facts). Use --full for legacy demo data."""

import argparse
import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from app.db.session_sync import SessionLocal
from app.services import seed_demo


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed regions/channels/distributors; optional full demo dataset.")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Also load sample customers, products, facts, and derived rows (legacy demo).",
    )
    parser.add_argument(
        "--commercial-system-reference-only",
        action="store_true",
        help=(
            "Idempotent: ensure dim_customer OPEN_CHANNEL + dim_distributor UNASSIGNED only. "
            "Does not wipe the database (unlike default seed)."
        ),
    )
    args = parser.parse_args()
    if args.commercial_system_reference_only:
        from app.services.commercial_planner.reference_bootstrap import (
            ensure_commercial_planner_system_reference_data_sync,
        )

        with SessionLocal() as session:
            ensure_commercial_planner_system_reference_data_sync(session.connection())
            session.commit()
        print("Commercial planner system reference dimensions ensured (OPEN_CHANNEL, UNASSIGNED).")
        return
    with SessionLocal() as session:
        seed_demo.run(session, full_demo=args.full)
    print("Seed complete." + (" (full demo)" if args.full else " (catalog only — wipes DB first)")))


if __name__ == "__main__":
    main()
