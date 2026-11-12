"""Backup dim_customer and dim_distributor from cip before the identity split.

Does not print the connection string. Does not write to cip.
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

WORKTREE_API = Path(__file__).resolve().parents[2]
MAIN_API = Path(__file__).resolve().parents[6] / "apps" / "api"
sys.path.insert(0, str(MAIN_API))
sys.path.insert(0, str(WORKTREE_API))

from sqlalchemy import create_engine, text  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.sync_url import sqlalchemy_sync_engine_url  # noqa: E402
from scripts.ops.prove_job_delete_restore_clone import db_name, pg_bin, pg_env  # noqa: E402

OUT_DIR = Path(r"C:\Users\warren_eliason\cip-apply-logs\20261110-step8")
DUMP = OUT_DIR / "dim-customer-20261110.dump"


def main() -> int:
    settings = get_settings()
    url = sqlalchemy_sync_engine_url(settings.database_url_sync)
    source = db_name(url)
    print("source_database", source)
    if source != "cip":
        print("STOP")
        return 2
    engine = create_engine(url)
    with engine.connect() as conn:
        db = conn.execute(text("SELECT current_database()")).scalar()
        print("current_database()", db)
        if db != "cip":
            print("STOP")
            return 2
        print("alembic", [r[0] for r in conn.execute(text("SELECT version_num FROM alembic_version"))])
        print("dim_customer", conn.execute(text("SELECT count(*) FROM dim_customer")).scalar())
        print("dim_distributor", conn.execute(text("SELECT count(*) FROM dim_distributor")).scalar())
        conn.rollback()
    engine.dispose()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    args, env = pg_env(url)
    cmd = [
        pg_bin("pg_dump"),
        *args,
        "-d",
        "cip",
        "-Fc",
        "-t",
        "dim_customer",
        "-t",
        "dim_distributor",
        "-f",
        str(DUMP),
    ]
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        print("pg_dump_failed", result.returncode)
        err = (result.stderr or "").strip().splitlines()
        print("pg_dump_err_tail", err[-3:])
        return 1
    digest = hashlib.sha256(DUMP.read_bytes()).hexdigest()
    print("backup", DUMP.name, "bytes", DUMP.stat().st_size, "sha256", digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
