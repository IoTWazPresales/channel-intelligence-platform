"""Create ``cip_alembic_smoke`` if missing (local migration smoke only)."""

from __future__ import annotations

import sys

from sqlalchemy import create_engine, text

SMOKE_DB = "cip_alembic_smoke"
ADMIN_URL = "postgresql://cip:cip@localhost:5432/postgres"


def main() -> int:
    engine = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": SMOKE_DB},
        ).fetchone()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{SMOKE_DB}"'))
            print(f"created database {SMOKE_DB}")
        else:
            print(f"database {SMOKE_DB} already exists")
    return 0


if __name__ == "__main__":
    sys.exit(main())
