"""Read-only counts of proposed sites and proposed listings. NOT RUN (cloud).

Refuses to run when ``current_database()`` is ``cip``. Does not insert, update or delete.
The before/after comparison on cip_test is a local task.
"""

from __future__ import annotations

import sys

from sqlalchemy import text

from app.db.session_sync import SessionLocal


def main() -> int:
    with SessionLocal() as session:
        database = session.execute(text("SELECT current_database()")).scalar_one()
        if database == "cip":
            print("refused: current_database() is cip", file=sys.stderr)
            return 2
        sites = session.execute(
            text("SELECT count(*) FROM customer_web_site WHERE status = 'proposed'")
        ).scalar_one()
        listings = session.execute(
            text("SELECT count(*) FROM cst_listing_seed WHERE status = 'proposed'")
        ).scalar_one()
    print(f"database={database} proposed_customer_web_site={sites} proposed_cst_listing_seed={listings}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
