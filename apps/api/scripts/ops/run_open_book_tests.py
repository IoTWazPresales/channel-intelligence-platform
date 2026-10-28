"""Run the open-book pytest set against cip_test and save the log.

The database name in the process environment is rewritten to cip_test before
pytest starts. Connection strings are not printed.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy.engine.url import make_url

API_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = API_ROOT.parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

os.chdir(API_ROOT)

from app.core.config import get_settings

_TARGET = "cip_test"
_URL_ENV = (
    "DATABASE_URL",
    "DATABASE_URL_SYNC",
    "DATABASE_URL_SYNC_WRITABLE",
    "DATABASE_URL_SYNC_MIGRATE",
)


def _retarget(url: str) -> str:
    return make_url(url).set(database=_TARGET).render_as_string(hide_password=False)


def _point_at_cip_test() -> None:
    settings = get_settings()
    mapping = {
        "DATABASE_URL": settings.database_url,
        "DATABASE_URL_SYNC": settings.database_url_sync,
        "DATABASE_URL_SYNC_WRITABLE": settings.database_url_sync_writable,
        "DATABASE_URL_SYNC_MIGRATE": settings.database_url_sync_migrate,
    }
    for key, value in mapping.items():
        if not value:
            continue
        os.environ[key] = _retarget(value)
    get_settings.cache_clear()
    current = make_url(get_settings().database_url_sync).database
    if current != _TARGET:
        raise SystemExit(f"refusing to test: sync database is {current!r}")


_FILES = [
    "tests/test_shipment_open_book.py",
    "tests/test_shipment_change_events.py",
    "tests/test_shipment_evidence_detect.py",
    "tests/test_shipment_evidence_observations.py",
    "tests/test_shipment_invoice_graduation.py",
    "tests/test_shipment_strict_pair.py",
    "tests/test_channel_ops_derived_stock.py",
    "tests/test_channel_ops_api.py",
    "tests/test_supply_plan_unit_coverage.py",
    "tests/test_e10_calendar_values_db.py",
    "tests/test_query_tenant_overlay_e6.py",
    "tests/test_query_model_e7_e8.py",
    "tests/test_query_model_graph.py",
    "tests/test_query_model_db.py",
]


def main(argv: list[str] | None = None) -> int:
    _point_at_cip_test()
    chosen = list(argv) if argv else list(_FILES)
    out = REPO_ROOT / ".eif" / "audit" / "OPEN_BOOK_20261028" / "tests.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *chosen, "--tb=short", "-q"],
        cwd=API_ROOT,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
    )
    out.write_text(proc.stdout + "\n" + proc.stderr, encoding="utf-8")
    tail = "\n".join((proc.stdout + proc.stderr).strip().splitlines()[-40:])
    print(tail)
    print(f"pytest_exit={proc.returncode}")
    return int(proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
