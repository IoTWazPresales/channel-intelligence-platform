"""Lifecycle trio: Celery PROGRESS metas carry progress_at."""

from app.worker.tasks import _celery_progress_meta


def test_celery_progress_meta_includes_progress_at():
    meta = _celery_progress_meta(phase="validate", phase_label="Validating", current_row=1, total_rows=10, pct=10)
    assert meta["phase"] == "validate"
    assert meta["pct"] == 10
    assert isinstance(meta.get("progress_at"), str)
    assert "T" in meta["progress_at"]
