"""Run the needs-a-look regression file and the parallel-read unit test on cip_test."""

from __future__ import annotations

import os
import sys
from pathlib import Path

API = Path(__file__).resolve().parents[2]
os.environ["DATABASE_URL"] = "postgresql+asyncpg://cip:cip@localhost:5432/cip_test"
os.environ["DATABASE_URL_SYNC"] = "postgresql://cip:cip@localhost:5432/cip_test"
sys.path.insert(0, str(API))

import pytest

raise SystemExit(
    pytest.main(
        [
            "--rootdir",
            str(API),
            str(API / "tests" / "test_parallel_reads.py"),
            str(API / "tests" / "test_on_the_water_db.py"),
            "-q",
        ]
    )
)
