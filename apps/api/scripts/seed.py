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
    args = parser.parse_args()
    with SessionLocal() as session:
        seed_demo.run(session, full_demo=args.full)
    print("Seed complete." + (" (full demo)" if args.full else " (catalog only)"))


if __name__ == "__main__":
    main()
