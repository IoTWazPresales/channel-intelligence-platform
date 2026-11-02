#!/usr/bin/env python3
"""Run alembic as the table owner on a named database (default cip_test; cip only with --allow-cip). The owner login comes from PG_OWNER
(or CIP_CLONE_ADMIN_URL) and is never printed. Refuses ``cip``.

  python scripts/ops/_alembic_owner.py --db cip_test upgrade head
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(API_ROOT))

from app.core.config import get_settings  # noqa: E402
from scripts.ops.prove_job_delete_restore_clone import alembic, swap_db  # noqa: E402
from scripts.ops.prove_on_the_water_clone import admin_url  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default="cip_test")
    p.add_argument("--allow-cip", action="store_true", help="needed to run on cip (an explicit go from Warren)")
    p.add_argument("args", nargs="+")
    a = p.parse_args()
    if a.db == "cip" and not a.allow_cip:
        raise SystemExit("STOP: cip needs --allow-cip")
    s = get_settings()
    app_sync = swap_db(s.database_url_sync, a.db)
    env = dict(os.environ, DATABASE_URL=swap_db(s.database_url, a.db), DATABASE_URL_SYNC=app_sync,
               DATABASE_URL_SYNC_MIGRATE=swap_db(admin_url(s), a.db))
    print(a.db, "->", alembic(env, *a.args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
