"""Run the lateral-read unit test against the worktree tree. No database."""

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
            str(API / "tests" / "test_woc_observation_latest.py"),
            str(API / "tests" / "test_parallel_reads.py"),
            str(API / "tests" / "test_woc_observation.py"),
            str(API / "tests" / "test_query_engine.py"),
            str(API / "tests" / "test_channel_ops_api.py"),
            str(API / "tests" / "test_shipment_strict_pair.py::test_channel_ops_cover_inbound_open_counts_remainder"),
            "-q",
        ]
    )
)
