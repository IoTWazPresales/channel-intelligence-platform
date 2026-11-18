"""Wave 2 figure_check.py against the session's test database (cip_test). Read-only throughout.

The URL comes from settings (`database_url_sync`), as in the other DB tests; tests/conftest.py
refuses this module when that resolves to `cip`. Nothing here commits: every write attempt is
expected to fail inside a read-only transaction, and the temp table it names never exists.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import psycopg
import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify" / "figure_check.py"


def _load():
    spec = importlib.util.spec_from_file_location("wave2_figure_check_db", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclasses resolve annotations through sys.modules
    spec.loader.exec_module(mod)
    return mod


fc = _load()


def _url() -> str:
    from app.core.config import get_settings

    get_settings.cache_clear()
    return get_settings().database_url_sync


def _current_db(url: str) -> str:
    conn = fc.open_readonly(url)
    try:
        return str(conn.execute("SELECT current_database()").fetchone()[0])
    finally:
        conn.close()


def test_select_runs_read_only() -> None:
    url = _url()
    conn = fc.open_readonly(url)
    try:
        name = fc.assert_expected_db(conn, _current_db(url))
        assert name != "cip"
        check = fc.load_checks(
            [{"name": "one", "route": "/brief", "sql": "SELECT 1 + %(n)s", "params": {"n": 41}}]
        )[0]
        value, rows = fc.run_query(conn, check)
        assert (value, rows) == (42, 1)
        state = conn.execute("SHOW default_transaction_read_only").fetchone()[0]
        assert str(state).lower() == "on"
    finally:
        conn.close()


@pytest.mark.parametrize(
    "statement",
    [
        "CREATE TEMP TABLE wave2_figure_check_probe (x int)",
        "UPDATE alembic_version SET version_num = version_num WHERE false",
        "SELECT set_config('default_transaction_read_only', 'off', false)",
    ],
)
def test_raw_write_after_read_only_set_fails(statement: str) -> None:
    """Bypass the SQL screen: the session itself must refuse writes after the read-only SET."""
    conn = fc.open_readonly(_url())
    try:
        if statement.startswith("SELECT set_config"):
            # Even if a caller switched the default off, each check still runs in BEGIN READ ONLY.
            conn.execute(statement)
            with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
                with conn.transaction():
                    conn.execute("CREATE TEMP TABLE wave2_figure_check_probe (x int)")
            return
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            conn.execute(statement)
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            with conn.transaction():
                conn.execute(statement)
    finally:
        conn.close()


def test_expect_db_mismatch_refuses(tmp_path: Path) -> None:
    url = _url()
    conn = fc.open_readonly(url)
    try:
        with pytest.raises(fc.RefusedError):
            fc.assert_expected_db(conn, "not_the_session_database")
    finally:
        conn.close()

    checks = tmp_path / "checks.json"
    checks.write_text(
        json.dumps([{"name": "one", "route": "/brief", "sql": "SELECT 1", "expected": 1}]),
        encoding="utf-8",
    )
    out = tmp_path / "out"
    args = ["--checks", str(checks), "--db-url", url, "--out", str(out)]
    assert fc.main([*args, "--expect-db", "not_the_session_database"]) == 2
    assert not out.exists()
    assert fc.main([*args, "--expect-db", _current_db(url)]) == 0
    assert json.loads((out / "figure_checks.json").read_text(encoding="utf-8"))["mismatches"] == 0
