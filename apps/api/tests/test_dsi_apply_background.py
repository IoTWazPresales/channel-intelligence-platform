"""Unit tests for the backgrounded DSI apply orchestrator (no database I/O).

Covers ``run_dsi_apply_sync`` — the Celery/thread counterpart of the old in-request DSI apply:
pipeline (apply) → complete-to-loaded, with progress phases and graceful business-rule failure.
"""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import app.services.imports.dsi_apply_sync as apply_mod
from app.ingestion.pipeline import STAGE_FAILED, STAGE_LOADED, STAGE_VALIDATED
from app.services.imports.dsi_apply_completion import DsiApplyCompletionError


def _install_fake_session(monkeypatch, job, *, staging_count: int = 100):
    class _FakeSession:
        def get(self, _model, _id):
            return job

        def scalar(self, _stmt):
            return staging_count

        def commit(self):
            pass

    @contextmanager
    def _fake_sessionlocal():
        yield _FakeSession()

    monkeypatch.setattr(apply_mod, "SessionLocal", _fake_sessionlocal)


def test_run_dsi_apply_sync_happy_path(monkeypatch) -> None:
    job = SimpleNamespace(
        template_slug="distributor_inventory",
        stage=STAGE_VALIDATED,
        import_mode="apply",
        status="running",
    )
    _install_fake_session(monkeypatch, job)
    called = {"process": False}
    monkeypatch.setattr(
        apply_mod,
        "process_import_job_sync",
        lambda db, jid, on_progress=None: called.__setitem__("process", True),
    )

    def _complete(db, jid):
        job.stage = STAGE_LOADED
        job.status = "completed"
        return {"ok": True}

    monkeypatch.setattr(apply_mod, "complete_dsi_import_job_to_loaded", _complete)
    monkeypatch.setattr(apply_mod, "persist_clear_background_task_metadata", lambda s, j: None)

    phases: list[str] = []
    out = apply_mod.run_dsi_apply_sync(
        51, on_progress=lambda phase, label, cur, tot: phases.append(phase)
    )

    assert out == {"id": 51, "outcome": "applied"}
    assert job.stage == STAGE_LOADED
    assert called["process"] is False
    assert "finalizing_apply" in phases
    assert phases[-1] == "complete"


def test_run_dsi_apply_sync_runs_pipeline_when_no_staging(monkeypatch) -> None:
    job = SimpleNamespace(
        template_slug="distributor_inventory",
        stage="dsi_mapping_ready",
        import_mode="apply",
        status="running",
    )
    _install_fake_session(monkeypatch, job, staging_count=0)
    called = {"process": False}

    def _process(db, jid, on_progress=None):
        called["process"] = True
        job.stage = STAGE_VALIDATED

    monkeypatch.setattr(apply_mod, "process_import_job_sync", _process)
    monkeypatch.setattr(apply_mod, "complete_dsi_import_job_to_loaded", lambda db, jid: {"ok": True})
    monkeypatch.setattr(apply_mod, "persist_clear_background_task_metadata", lambda s, j: None)

    apply_mod.run_dsi_apply_sync(53)

    assert called["process"] is True


def test_run_dsi_apply_sync_rejects_non_dsi(monkeypatch) -> None:
    job = SimpleNamespace(template_slug="inbound_shipments", stage="", import_mode="", status="")
    _install_fake_session(monkeypatch, job)
    called = {"process": False}
    monkeypatch.setattr(
        apply_mod,
        "process_import_job_sync",
        lambda *a, **k: called.__setitem__("process", True),
    )

    out = apply_mod.run_dsi_apply_sync(99)

    assert out == {"id": 99, "outcome": "not_found"}
    assert called["process"] is False  # bailed before running the pipeline


def test_run_dsi_apply_sync_completion_error_marks_failed(monkeypatch) -> None:
    job = SimpleNamespace(
        template_slug="distributor_inventory",
        stage=STAGE_VALIDATED,
        import_mode="apply",
        status="running",
        error_summary=None,
        completed_at=None,
    )
    _install_fake_session(monkeypatch, job, staging_count=0)
    monkeypatch.setattr(apply_mod, "process_import_job_sync", lambda db, jid, on_progress=None: job)

    def _boom(db, jid):
        raise DsiApplyCompletionError("3 staging line(s) still blocked after refresh")

    monkeypatch.setattr(apply_mod, "complete_dsi_import_job_to_loaded", _boom)
    monkeypatch.setattr(apply_mod, "persist_clear_background_task_metadata", lambda s, j: None)

    out = apply_mod.run_dsi_apply_sync(52)

    assert out["outcome"] == "completion_error"
    assert "blocked" in out["error"]
    assert job.status == "failed"
    assert job.stage == STAGE_FAILED
    assert "blocked" in (job.error_summary or "")
