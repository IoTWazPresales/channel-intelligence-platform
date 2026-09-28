"""BACKLOG-133/134: import-complete merged-id leftover FLAG (no DB)."""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.models.ingestion import ImportRowResult
from app.services import customer_leftover_repair as clr
from app.services.imports import merged_leftover_flag as mlf


def _db() -> MagicMock:
    db = MagicMock()

    @contextmanager
    def _nested():
        yield

    db.begin_nested.side_effect = _nested
    return db


def _job(meta=None):
    return SimpleNamespace(id=42, staged_metadata=meta)


def _result(cust: dict[str, int], dist: dict[str, int]) -> dict:
    return {
        "customer_leftover_rows": sum(cust.values()),
        "customer_fk_counts": cust,
        "distributor_leftover_rows": sum(dist.values()),
        "distributor_fk_counts": dist,
        "total_leftover_rows": sum(cust.values()) + sum(dist.values()),
    }


def test_nonzero_leftover_is_flag_warning_not_block(monkeypatch: pytest.MonkeyPatch) -> None:
    res = _result({"customer_source_token_alias.customer_id": 2}, {"fact_sales_sellin.distributor_id": 3})
    monkeypatch.setattr(mlf, "merged_id_leftover_check", lambda db: res)
    db = _db()
    job = _job({"keep": 1})

    out = mlf.flag_merged_id_leftovers(db, job)

    assert out is res
    meta = job.staged_metadata[mlf.MERGED_LEFTOVER_META_KEY]
    assert meta["flag"] is True and meta["total_leftover_rows"] == 5
    assert job.staged_metadata["keep"] == 1
    rows = [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], ImportRowResult)]
    assert len(rows) == 1
    r = rows[0]
    assert (r.severity, r.code, r.row_number, r.job_id) == ("warning", "merged_id_leftover", 0, 42)
    assert "customer 2" in r.message and "distributor 3" in r.message
    # Detection only: nothing committed or repointed here (caller commits).
    db.commit.assert_not_called()


def test_zero_leftover_records_summary_without_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mlf, "merged_id_leftover_check", lambda db: _result({}, {}))
    db = _db()
    job = _job(None)

    mlf.flag_merged_id_leftovers(db, job)

    assert job.staged_metadata[mlf.MERGED_LEFTOVER_META_KEY]["flag"] is False
    assert not [c for c in db.add.call_args_list if isinstance(c.args[0], ImportRowResult)]


def test_check_failure_is_swallowed_and_job_untouched(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(db):
        raise RuntimeError("scan failed")

    monkeypatch.setattr(mlf, "merged_id_leftover_check", boom)
    db = _db()
    job = _job({"keep": 1})

    assert mlf.flag_merged_id_leftovers(db, job) is None
    assert job.staged_metadata == {"keep": 1}
    db.add.assert_not_called()


def test_leftover_counts_skip_self_redirect_and_use_merged_subquery() -> None:
    seen: list[str] = []

    def execute(stmt, *a, **k):
        sql = str(stmt)
        seen.append(sql)
        return SimpleNamespace(scalar=lambda: 7 if "fact_x" in sql else 0)

    db = SimpleNamespace(execute=execute)
    cols = (("fact_x", "customer_id"), ("fact_y", "customer_id"), ("dim_customer", "merged_into_customer_id"))
    counts = clr._merged_leftover_counts(db, cols, clr._LEFTOVER_SKIP, clr._MERGED_CUSTOMER_IDS_SQL)

    assert counts == {"fact_x.customer_id": 7}
    assert len(seen) == 2  # self-redirect column never scanned
    assert all("merged_into_customer_id IS NOT NULL" in s for s in seen)


def test_check_covers_customer_and_distributor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clr, "discover_customer_fk_columns", lambda db: (("customer_source_token_alias", "customer_id"),))
    monkeypatch.setattr(
        clr, "discover_distributor_fk_columns", lambda db: (("distributor_source_token_alias", "distributor_id"),)
    )

    def execute(stmt, *a, **k):
        sql = str(stmt)
        return SimpleNamespace(scalar=lambda: 1 if "customer_source_token_alias" in sql else 4)

    out = clr.merged_id_leftover_check(SimpleNamespace(execute=execute))
    assert out["customer_leftover_rows"] == 1
    assert out["distributor_leftover_rows"] == 4
    assert out["total_leftover_rows"] == 5
