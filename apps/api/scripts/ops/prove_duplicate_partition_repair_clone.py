"""Clone gate: prove BACKLOG-066 duplicate partition repair (#39/#40).

Uses pg_dump at PostgreSQL 18 bin (BACKLOG-071). NEVER touches cip after clone create.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
API = REPO / "apps" / "api"
sys.path.insert(0, str(API))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.services.commercial_planner.lineup_duplicate_partition_repair import (
    apply_duplicate_partition,
    planned_units_by_period_bu,
    preview_duplicate_partition,
)
from app.services.data_integrity_audit import check_lineup_duplicate_ingestion

PG_BIN = Path(r"C:\Program Files\PostgreSQL\18\bin")
DUMP_PATH = REPO / ".tmp" / "cip_clone_dup066.dump"
CLONE_DB = "cip_clone_dup066"
CASE_IDS = [39, 40]
PGHOST = "127.0.0.1"
PGPORT = "5432"
CIP_USER = "cip"
CIP_PASS = "cip"
ADMIN_USER = os.environ.get("SMOKE_ADMIN_USER", "postgres")
ADMIN_PASS = os.environ.get("SMOKE_ADMIN_PASSWORD", "Exarkun4252!")


def _run(cmd: list[str], *, env: dict | None = None, label: str = "") -> None:
    print(f"RUN {label or cmd[0]}: {' '.join(cmd[:6])}...")
    r = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if r.returncode != 0:
        print("STDOUT:", r.stdout[-2000:])
        print("STDERR:", r.stderr[-2000:])
        raise SystemExit(f"Command failed ({r.returncode}): {cmd[0]}")


def _clone_cip() -> str:
    pg_dump = PG_BIN / "pg_dump.exe"
    if not pg_dump.is_file():
        raise SystemExit(f"pg_dump not found at {pg_dump}")
    DUMP_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DUMP_PATH.exists():
        DUMP_PATH.unlink()

    cip_env = os.environ.copy()
    cip_env["PGPASSWORD"] = CIP_PASS
    _run(
        [
            str(pg_dump),
            "-h",
            PGHOST,
            "-p",
            PGPORT,
            "-U",
            CIP_USER,
            "-d",
            "cip",
            "-Fc",
            "-f",
            str(DUMP_PATH),
            "--no-owner",
            "--no-privileges",
        ],
        env=cip_env,
        label="pg_dump",
    )

    admin_env = os.environ.copy()
    admin_env["PGPASSWORD"] = ADMIN_PASS
    _run(
        [str(PG_BIN / "dropdb.exe"), "-h", PGHOST, "-p", PGPORT, "-U", ADMIN_USER, "--if-exists", CLONE_DB],
        env=admin_env,
        label="dropdb",
    )
    _run(
        [str(PG_BIN / "createdb.exe"), "-h", PGHOST, "-p", PGPORT, "-U", ADMIN_USER, "-O", CIP_USER, CLONE_DB],
        env=admin_env,
        label="createdb",
    )
    _run(
        [
            str(PG_BIN / "pg_restore.exe"),
            "-h",
            PGHOST,
            "-p",
            PGPORT,
            "-U",
            CIP_USER,
            "-d",
            CLONE_DB,
            "--no-owner",
            "--no-privileges",
            str(DUMP_PATH),
        ],
        env=cip_env,
        label="pg_restore",
    )
    return f"postgresql+psycopg://{CIP_USER}:{CIP_PASS}@{PGHOST}:{PGPORT}/{CLONE_DB}"


def main() -> int:
    clone_url = _clone_cip()
    eng = create_engine(clone_url)
    CloneSession = sessionmaker(bind=eng, class_=Session, autoflush=False, autocommit=False)

    with eng.connect() as conn:
        print("current_database:", conn.execute(text("SELECT current_database()")).scalar())

    with CloneSession() as db:
        before_dup = check_lineup_duplicate_ingestion(db, sample_limit=50)
        before_25q1 = planned_units_by_period_bu(db, year=2025, quarter=1, business_units=["NR", "NV"])
        before_24q4 = planned_units_by_period_bu(db, year=2024, quarter=4, business_units=["NR", "NV", "PF"])
        preview = preview_duplicate_partition(db, case_ids=CASE_IDS)
        print("BEFORE duplicate clusters:", before_dup.count)
        print("BEFORE 25Q1 NR/NV units:", before_25q1)
        print("BEFORE 24Q4:", before_24q4)
        print("PREVIEW supersede lines:", preview["total_lines_to_supersede"])

        result = apply_duplicate_partition(db, case_ids=CASE_IDS)
        after_dup = check_lineup_duplicate_ingestion(db, sample_limit=50)
        after_25q1 = planned_units_by_period_bu(db, year=2025, quarter=1, business_units=["NR", "NV"])
        after_24q4 = planned_units_by_period_bu(db, year=2024, quarter=4, business_units=["NR", "NV", "PF"])

    out = {
        "clone_db": CLONE_DB,
        "before": {
            "duplicate_clusters": before_dup.count,
            "planned_25q1": before_25q1,
            "planned_24q4": before_24q4,
        },
        "after": {
            "duplicate_clusters": after_dup.count,
            "planned_25q1": after_25q1,
            "planned_24q4": after_24q4,
            "lines_superseded": result.get("lines_superseded"),
        },
        "pass": after_dup.count == 0 and result.get("lines_superseded", 0) > 0,
    }
    print(json.dumps(out, indent=2))

    eng.dispose()

    admin_env = os.environ.copy()
    admin_env["PGPASSWORD"] = ADMIN_PASS
    _run(
        [str(PG_BIN / "dropdb.exe"), "-h", PGHOST, "-p", PGPORT, "-U", ADMIN_USER, "--if-exists", CLONE_DB],
        env=admin_env,
        label="drop clone",
    )
    print("Clone dropped.")
    return 0 if out["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
