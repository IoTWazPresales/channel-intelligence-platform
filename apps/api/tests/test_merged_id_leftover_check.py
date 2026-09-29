"""Merged-id leftover flag on the import-complete rail. The check does not block apply."""

from __future__ import annotations

from types import SimpleNamespace

from app.models.ingestion import ImportRowResult
from app.services.imports.merged_id_leftover_check import (
    MERGED_ID_LEFTOVER_CODE,
    apply_merged_id_leftover_flag,
    run_import_complete_rail,
)


class _FakeDb:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.commits = 0
        self.rollbacks = 0

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def _job() -> SimpleNamespace:
    return SimpleNamespace(
        id=9,
        status="completed",
        stage="loaded",
        staged_metadata={"keep": 1},
        tenant_id="default",
    )


def test_zero_leftovers_do_not_flag_or_change_job_state() -> None:
    job = _job()
    db = _FakeDb()
    stamped = apply_merged_id_leftover_flag(
        db,  # type: ignore[arg-type]
        job,  # type: ignore[arg-type]
        {"customer_leftover_rows": 0, "distributor_leftover_rows": 0, "total": 0},
    )
    assert stamped["flagged"] is False
    assert stamped["blocks_apply"] is False
    assert job.status == "completed"
    assert job.stage == "loaded"
    assert job.staged_metadata["keep"] == 1
    assert not any(isinstance(row, ImportRowResult) for row in db.added)
    assert db.commits == 1


def test_nonzero_leftovers_are_a_warning_flag() -> None:
    job = _job()
    db = _FakeDb()
    stamped = apply_merged_id_leftover_flag(
        db,  # type: ignore[arg-type]
        job,  # type: ignore[arg-type]
        {"customer_leftover_rows": 2, "distributor_leftover_rows": 1, "total": 3},
    )
    assert stamped == {
        "customer_leftover_rows": 2,
        "distributor_leftover_rows": 1,
        "total": 3,
        "flagged": True,
        "blocks_apply": False,
    }
    assert job.status == "completed"
    assert job.stage == "loaded"
    flags = [row for row in db.added if isinstance(row, ImportRowResult)]
    assert len(flags) == 1
    assert flags[0].severity == "warning"
    assert flags[0].code == MERGED_ID_LEFTOVER_CODE
    assert flags[0].severity != "error"


def test_rail_fans_out_after_a_failed_check(monkeypatch) -> None:
    calls: list[str] = []

    def boom(_db: object) -> dict[str, int]:
        raise RuntimeError("scan failed")

    def fanout(*, tenant_id: str) -> None:
        calls.append(tenant_id)

    monkeypatch.setattr(
        "app.services.imports.merged_id_leftover_check.measure_merged_id_leftovers",
        boom,
    )
    monkeypatch.setattr(
        "app.services.report_schedule_runner.dispatch_import_complete_report_fanout",
        fanout,
    )
    job = _job()
    job.tenant_id = "t1"
    db = _FakeDb()
    run_import_complete_rail(db, job)  # type: ignore[arg-type]
    assert calls == ["t1"]
    assert db.rollbacks == 1
    assert job.status == "completed"
    assert job.stage == "loaded"
