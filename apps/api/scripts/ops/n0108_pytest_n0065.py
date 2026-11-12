"""Run the N-0065 DB tests from this worktree against cip_test."""

from __future__ import annotations

import os
import sys
from pathlib import Path

API = Path(__file__).resolve().parents[2]
os.environ["DATABASE_URL"] = "postgresql+asyncpg://cip:cip@localhost:5432/cip_test"
os.environ["DATABASE_URL_SYNC"] = "postgresql://cip:cip@localhost:5432/cip_test"
sys.path.insert(0, str(API))

import psycopg

with psycopg.connect(os.environ["DATABASE_URL_SYNC"], autocommit=True) as conn:
    conn.execute("SET default_transaction_read_only = on")
    name = conn.execute("SELECT current_database()").fetchone()[0]
    rev = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
print(f"current_database={name} alembic_version={rev}", flush=True)
if name != "cip_test":
    raise SystemExit(f"STOP: database is {name!r}, not cip_test")

os.chdir(API)

import pytest

raise SystemExit(
    pytest.main(
        [
            "--rootdir",
            str(API),
            str(API / "tests" / "test_shipment_evidence_lineage_rls_n0065_db.py"),
            str(API / "tests" / "test_product_line_rls_parity_n0065_db.py"),
            "-q",
            "--tb=line",
        ]
    )
)
