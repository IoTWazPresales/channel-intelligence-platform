"""Delete all rows from every table (clean slate for real data). Does not drop schema."""

from __future__ import annotations

import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from app.services.db_wipe import wipe_all_application_tables


def main() -> None:
    out = wipe_all_application_tables()
    print(f"All application tables cleared (empty database). rows_deleted={out['rows_deleted']}")


if __name__ == "__main__":
    main()
