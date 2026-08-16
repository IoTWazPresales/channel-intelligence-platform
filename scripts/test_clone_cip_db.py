"""BACKLOG-071: clone helper refuses cip writes and resolves PG_BIN."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "ops"))

from clone_cip_db import assert_clone_db_name, resolve_pg_bin  # noqa: E402


def test_assert_clone_db_name_refuses_cip() -> None:
    with pytest.raises(SystemExit):
        assert_clone_db_name("cip")
    with pytest.raises(SystemExit):
        assert_clone_db_name("CIP")
    assert assert_clone_db_name("cip_gate_smoke") == "cip_gate_smoke"


def test_resolve_pg_bin_honors_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PG_BIN", str(tmp_path))
    assert resolve_pg_bin() == tmp_path
