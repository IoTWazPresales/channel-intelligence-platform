"""BACKLOG-061 B4 — remap orphan customer_status='verified' → 'active'.

Warren approved 2026-07-10. SELECT first; UPDATE only when --confirm.
Never touches merged_into_* or codes.
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import text

from app.db.session_sync import SessionLocal


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm", action="store_true", help="Apply UPDATE (default is dry-run)")
    args = parser.parse_args()

    with SessionLocal() as session:
        db = session.execute(text("SELECT current_database()")).scalar()
        print("current_database=", db)
        if db != "cip":
            print("REFUSING: not cip", file=sys.stderr)
            return 2

        rows = session.execute(
            text(
                """
                SELECT id, code, customer_status
                FROM dim_customer
                WHERE customer_status = 'verified'
                ORDER BY id
                """
            )
        ).all()
        print("orphan_verified_count=", len(rows))
        for r in rows:
            print(f"  id={r[0]} code={r[1]} status={r[2]}")

        if not args.confirm:
            print("dry_run=true (pass --confirm to UPDATE)")
            return 0

        result = session.execute(
            text(
                """
                UPDATE dim_customer
                SET customer_status = 'active'
                WHERE customer_status = 'verified'
                """
            )
        )
        session.commit()
        print("updated_rows=", result.rowcount)
        left = session.execute(
            text("SELECT count(*) FROM dim_customer WHERE customer_status = 'verified'")
        ).scalar()
        print("remaining_verified=", left)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
