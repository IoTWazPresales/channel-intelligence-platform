"""Run the N-0065 DB tests from the integration tip against cip_test.

The tip does not contain migration 20261104_0057. cip_test may already be at
that revision. This runner only reports what those tests do; it does not change
the tip.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

OLD = Path(__file__).resolve().parents[4] / "old-tip" / "apps" / "api"
if not (OLD / "tests").is_dir():
    raise SystemExit(f"STOP: old tip tests not found at {OLD}")

os.environ["DATABASE_URL"] = "postgresql+asyncpg://cip:cip@localhost:5432/cip_test"
os.environ["DATABASE_URL_SYNC"] = "postgresql://cip:cip@localhost:5432/cip_test"
sys.path.insert(0, str(OLD))

import psycopg

with psycopg.connect(os.environ["DATABASE_URL_SYNC"], autocommit=True) as conn:
    conn.execute("SET default_transaction_read_only = on")
    name = conn.execute("SELECT current_database()").fetchone()[0]
    rev = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
print(f"current_database={name} alembic_version={rev}", flush=True)
if name != "cip_test":
    raise SystemExit(f"STOP: database is {name!r}, not cip_test")

# alembic.ini uses script_location = alembic, resolved from the process folder.
os.chdir(OLD)

import pytest

raise SystemExit(
    pytest.main(
        [
            "--rootdir",
            str(OLD),
            str(OLD / "tests" / "test_shipment_evidence_lineage_rls_n0065_db.py"),
            str(OLD / "tests" / "test_product_line_rls_parity_n0065_db.py"),
            "-q",
            "--tb=line",
        ]
    )
)
