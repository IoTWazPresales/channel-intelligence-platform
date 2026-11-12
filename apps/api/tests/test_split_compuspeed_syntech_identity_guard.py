"""--expect-db guard of the Compuspeed/Syntech identity split script.

No database is touched: the engine, the Session and ``run`` are all replaced.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "ops"
    / "split_compuspeed_syntech_identity.py"
)


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


class _FakeSession:
    """Stands in for sqlalchemy.orm.Session; records commit/rollback, no I/O."""

    current_db = "cip"
    instances: list[_FakeSession] = []

    def __init__(self, engine):
        self.engine = engine
        self.commits = 0
        self.rollbacks = 0
        _FakeSession.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, *_args, **_kwargs):
        return _FakeResult(_FakeSession.current_db)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class _FakeEngine:
    def dispose(self):
        pass


@pytest.fixture()
def script(monkeypatch):
    spec = importlib.util.spec_from_file_location("split_identity_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    import app.core.config as config

    monkeypatch.setattr(
        config,
        "get_settings",
        lambda: SimpleNamespace(database_url_sync="postgresql://u:p@localhost:5432/cip"),
    )
    monkeypatch.setattr(module, "create_engine", lambda *_a, **_k: _FakeEngine())
    monkeypatch.setattr(module, "Session", _FakeSession)
    _FakeSession.instances = []
    calls: list[bool] = []

    def fake_run(db, *, apply):
        calls.append(apply)
        return 0

    monkeypatch.setattr(module, "run", fake_run)
    module.run_calls = calls
    return module


def _argv(monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["split_compuspeed_syntech_identity.py", *args])


def test_expect_db_mismatch_stops_before_run(script, monkeypatch, capsys):
    _FakeSession.current_db = "cip"
    _argv(monkeypatch, "--expect-db", "cip_queue_s6", "--apply")

    code = script.main()

    out = capsys.readouterr().out
    assert code != 0
    assert script.run_calls == []
    assert "STOP" in out
    assert "cip_queue_s6" in out and "cip" in out
    session = _FakeSession.instances[0]
    assert session.commits == 0
    assert session.rollbacks >= 1


def test_expect_db_match_proceeds_to_run(script, monkeypatch):
    _FakeSession.current_db = "cip_queue_s6"
    _argv(monkeypatch, "--expect-db", "cip_queue_s6")

    code = script.main()

    assert code == 0
    assert script.run_calls == [False]
    assert _FakeSession.instances[0].commits == 0


def test_expect_db_match_with_apply_commits(script, monkeypatch):
    _FakeSession.current_db = "cip_queue_s6"
    _argv(monkeypatch, "--expect-db", "cip_queue_s6", "--apply")

    code = script.main()

    assert code == 0
    assert script.run_calls == [True]
    assert _FakeSession.instances[0].commits == 1
