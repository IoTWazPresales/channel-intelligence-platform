"""Run the committed E6-E8 query tests against cip_test. Review artifact.

Run from the project root:  apps/api/.venv/Scripts/python.exe .eif/audit/E10_20261028/run_focused.py
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

API = Path(__file__).resolve().parents[3] / "apps" / "api"
os.chdir(API)
sys.path.insert(0, str(API))

from app.core.config import get_settings  # noqa: E402

s = get_settings()


def swap(url: str) -> str:
    return re.sub(r"/cip(\?|$)", r"/cip_test\1", url)


os.environ["DATABASE_URL"] = swap(s.database_url)
os.environ["DATABASE_URL_SYNC"] = swap(s.database_url_sync)
if getattr(s, "database_url_sync_migrate", None):
    os.environ["DATABASE_URL_SYNC_MIGRATE"] = swap(s.database_url_sync_migrate)
get_settings.cache_clear()

import pytest  # noqa: E402

sys.exit(
    pytest.main(
        [
            "-q",
            "-p",
            "no:cacheprovider",
            "tests/test_query_tenant_overlay_e6.py",
            "tests/test_query_model_e7_e8.py",
            "tests/test_query_model_graph.py",
            "tests/test_query_model_db.py",
        ]
    )
)
