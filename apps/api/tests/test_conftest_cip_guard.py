"""The conftest cip guard: refuse at setup by source scan, and refuse every connection to `cip`.

No real database is reached: engines point at 127.0.0.1:1, where nothing listens, so a guard that
failed to refuse shows up as a driver connection error instead of a refusal.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import create_async_engine

import conftest as guard

_NOWHERE = "127.0.0.1:1"


@pytest.fixture(autouse=True)
def _restore_guard_state(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("ALLOW_TESTS_ON_DEV_DB", raising=False)
    saved = guard._cip_connect_refused
    yield
    guard._cip_connect_refused = saved


def _sync_connect(db: str) -> None:
    engine = create_engine(f"postgresql+psycopg://u:p@{_NOWHERE}/{db}", connect_args={"connect_timeout": 2})
    try:
        with engine.connect():
            pass
    finally:
        engine.dispose()


async def _async_connect(db: str) -> None:
    engine = create_async_engine(f"postgresql+asyncpg://u:p@{_NOWHERE}/{db}", connect_args={"timeout": 2})
    try:
        async with engine.connect():
            pass
    finally:
        await engine.dispose()


def test_sync_connection_to_cip_is_refused_before_the_driver() -> None:
    with pytest.raises(guard.CipTestDatabaseRefused, match="database 'cip'"):
        _sync_connect("cip")


def test_async_connection_to_cip_is_refused_before_the_driver() -> None:
    with pytest.raises(guard.CipTestDatabaseRefused, match="database 'cip'"):
        asyncio.run(_async_connect("cip"))


def test_connection_to_another_database_is_left_alone() -> None:
    # Reaches the driver, which fails on the closed port: the guard did not interfere.
    with pytest.raises(OperationalError):
        _sync_connect("cip_test")


def test_allow_env_lets_the_connection_through(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALLOW_TESTS_ON_DEV_DB", "1")
    with pytest.raises(OperationalError):
        _sync_connect("cip")


def test_allowlisted_module_may_connect_to_cip() -> None:
    guard._cip_connect_refused = False
    with pytest.raises(OperationalError):
        _sync_connect("cip")


def _item(tmp_path: Path, name: str, source: str) -> SimpleNamespace:
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    return SimpleNamespace(path=path, nodeid=f"tests/{name}::test_x")


@pytest.mark.parametrize(
    "source",
    [
        "from app.db.session_sync import SessionLocal\n",
        "from app.db.session import AsyncSessionLocal\n",
        "from fastapi.testclient import TestClient\nfrom app.main import app\n",
        "import sqlalchemy as sa\nengine = sa.create_engine(url)\n",
        "import psycopg\n",
    ],
)
def test_setup_refuses_an_unlisted_module_that_can_open_a_session_on_cip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: str
) -> None:
    monkeypatch.setattr(guard, "_settings_resolve_to_cip", lambda: True)
    item = _item(tmp_path, "test_unlisted_db_module.py", source)
    with pytest.raises(pytest.fail.Exception, match="Refusing test module 'test_unlisted_db_module.py'"):
        guard.pytest_runtest_setup(item)
    assert guard._cip_connect_refused is True


def test_setup_lets_a_pure_module_run_on_cip_but_keeps_the_connect_veto(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(guard, "_settings_resolve_to_cip", lambda: True)
    guard.pytest_runtest_setup(_item(tmp_path, "test_pure_unit.py", "def test_x():\n    assert 1\n"))
    assert guard._cip_connect_refused is True


def test_setup_lets_a_db_module_run_on_another_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(guard, "_settings_resolve_to_cip", lambda: False)
    guard.pytest_runtest_setup(_item(tmp_path, "test_unlisted_db_module.py", "from app.db.session import x\n"))
    assert guard._cip_connect_refused is True


def test_setup_lets_an_allowlisted_module_reach_cip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(guard, "_settings_resolve_to_cip", lambda: True)
    (name,) = guard._CIP_WRITE_ALLOWLIST
    guard.pytest_runtest_setup(_item(tmp_path, name, "from app.db.session_sync import SessionLocal\n"))
    assert guard._cip_connect_refused is False
