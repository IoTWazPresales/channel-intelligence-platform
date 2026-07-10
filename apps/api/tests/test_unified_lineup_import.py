"""Unit tests for the unified multi-file lineup import dispatcher."""

import asyncio
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.commercial_planner import unified_lineup_import as mod


def _make_db():
    db = MagicMock()
    db.get = AsyncMock(return_value=None)
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    counter = {"n": 0}

    async def _refresh(obj):
        counter["n"] += 1
        obj.id = 100 + counter["n"]

    db.refresh = AsyncMock(side_effect=_refresh)
    return db


@contextmanager
def _fake_session_local():
    yield MagicMock()


def test_one_case_and_job_per_file():
    db = _make_db()
    prepare = MagicMock(side_effect=lambda *a, **k: SimpleNamespace(id=500 + k["case_id"]))
    enqueue = MagicMock(return_value={"outcome": "enqueued", "task_id": "task-x"})

    with patch.object(mod, "SessionLocal", _fake_session_local), patch.object(
        mod, "prepare_lineup_parse_import_job_sync", prepare
    ), patch.object(mod, "enqueue_lineup_parse_sync", enqueue):
        out = asyncio.run(
            mod.dispatch_unified_lineup_import(
                db,
                [("a.csv", b"sku,qty\nX,1\n"), ("b.xlsx", b"sku,qty\nY,2\n")],
                period_label="26Q1",
            )
        )

    assert out["file_count"] == 2
    assert out["dispatched"] == 2
    assert db.add.call_count == 2  # one case per file
    # each dispatch tagged unified_lineup
    for _args, kwargs in enqueue.call_args_list:
        assert kwargs["template_slug"] == "unified_lineup"
        assert kwargs["source_code"] == "unified_lineup_system"
    assert [f["outcome"] for f in out["files"]] == ["enqueued", "enqueued"]
    assert all(f.get("task_id") == "task-x" for f in out["files"])


def test_empty_file_is_skipped_without_aborting_batch():
    db = _make_db()
    prepare = MagicMock(side_effect=lambda *a, **k: SimpleNamespace(id=999))
    enqueue = MagicMock(return_value={"outcome": "enqueued", "task_id": "t"})

    with patch.object(mod, "SessionLocal", _fake_session_local), patch.object(
        mod, "prepare_lineup_parse_import_job_sync", prepare
    ), patch.object(mod, "enqueue_lineup_parse_sync", enqueue):
        out = asyncio.run(
            mod.dispatch_unified_lineup_import(db, [("empty.csv", b""), ("ok.csv", b"sku\nX\n")])
        )

    assert out["file_count"] == 2
    assert out["dispatched"] == 1
    outcomes = {f["filename"]: f["outcome"] for f in out["files"]}
    assert outcomes["empty.csv"] == "error"
    assert outcomes["ok.csv"] == "enqueued"


def test_one_file_failure_does_not_abort_batch():
    db = _make_db()

    def _enqueue(*a, **k):
        if k["case_id"] == 101:  # first file -> boom
            raise RuntimeError("dispatch boom")
        return {"outcome": "enqueued", "task_id": "t"}

    prepare = MagicMock(side_effect=lambda *a, **k: SimpleNamespace(id=k["case_id"]))

    with patch.object(mod, "SessionLocal", _fake_session_local), patch.object(
        mod, "prepare_lineup_parse_import_job_sync", prepare
    ), patch.object(mod, "enqueue_lineup_parse_sync", MagicMock(side_effect=_enqueue)):
        out = asyncio.run(
            mod.dispatch_unified_lineup_import(db, [("bad.csv", b"x"), ("good.csv", b"y")])
        )

    assert out["file_count"] == 2
    assert out["dispatched"] == 1
    assert out["files"][0]["outcome"] == "error"
    assert "boom" in out["files"][0]["error"]
    assert out["files"][1]["outcome"] == "enqueued"


def test_empty_batch_returns_zeroes():
    db = _make_db()
    out = asyncio.run(mod.dispatch_unified_lineup_import(db, []))
    assert out == {"files": [], "file_count": 0, "dispatched": 0}


def test_generic_seed_issues_template_and_source_for_unified():
    from app.services.commercial_planner.current_lineup_seed import ensure_lineup_import_seed

    db = MagicMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    asyncio.run(
        ensure_lineup_import_seed(db, template_slug="unified_lineup", source_code="unified_lineup_system")
    )
    # one template upsert + one source insert
    assert db.execute.call_count == 2
    # the source-insert params carry the unified source code
    bind_params = [call.args[1] for call in db.execute.call_args_list if len(call.args) > 1]
    assert any(p.get("code") == "unified_lineup_system" for p in bind_params)
