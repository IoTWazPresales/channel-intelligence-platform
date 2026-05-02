"""Pytest hooks shared by API tests.

Import-pipeline integration tests create `import_job` rows, staging lines, and storage keys
under `imports/test/...` using the same `DATABASE_URL` / `DATABASE_URL_SYNC` as local dev.
When that URL targets the default database name `cip`, those tests pollute the shared dev DB.

Guard: refuse to run those modules unless the operator explicitly opts in with
`ALLOW_TESTS_ON_DEV_DB=1`, or points settings at a different database name (e.g. `cip_test`).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# Tests that call `process_import_job_sync` / create `ImportJob` rows against the real engine.
_IMPORT_PIPELINE_DB_TEST_MODULES: frozenset[str] = frozenset(
    {
        "test_distributor_sales_inventory_import.py",
        "test_historical_lineup_import.py",
        "test_historical_lineup_resolution.py",
    }
)


def _sqlalchemy_db_name(url: str) -> str:
    """Return the path segment after the last '/' in a SQLAlchemy-style URL (strip query string)."""
    if not url or "://" not in url:
        return ""
    rest = url.split("://", 1)[1]
    if "/" not in rest:
        return ""
    db = rest.rsplit("/", 1)[-1]
    return db.split("?", 1)[0].strip()


def pytest_runtest_setup(item) -> None:  # type: ignore[no-untyped-def]
    if os.environ.get("ALLOW_TESTS_ON_DEV_DB", "").strip() == "1":
        return

    node_file = item.nodeid.split("::", 1)[0].replace("\\", "/")
    basename = Path(node_file).name
    if basename not in _IMPORT_PIPELINE_DB_TEST_MODULES:
        return

    from app.core.config import get_settings

    settings = get_settings()
    async_name = _sqlalchemy_db_name(settings.database_url)
    sync_name = _sqlalchemy_db_name(settings.database_url_sync)
    if async_name == "cip" or sync_name == "cip":
        pytest.fail(
            "Refusing import pipeline DB tests: database name is 'cip' (default shared dev DB). "
            "Use a disposable database (set DATABASE_URL / DATABASE_URL_SYNC to e.g. .../cip_test), "
            "or set ALLOW_TESTS_ON_DEV_DB=1 to acknowledge you accept writes to the current database."
        )
