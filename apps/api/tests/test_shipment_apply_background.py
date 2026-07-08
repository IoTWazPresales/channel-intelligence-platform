"""Unit tests for the backgrounded + batched shipment apply path (no database I/O).

Covers the two behavior changes:
  * ``upsert_inbound_shipment_facts_for_job`` writes in chunked multi-row statements (N+1 fix)
    and reports progress once per chunk.
  * ``run_shipment_apply_sync`` orchestrates auto-map → upsert → ``loaded`` with progress phases.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import app.services.imports.shipment_apply_sync as apply_mod
import app.services.imports.shipment_inbound_facts as facts_mod
from app.ingestion.pipeline import STAGE_LOADED


def _db_with_lines(n: int) -> MagicMock:
    db = MagicMock()
    scalars_result = MagicMock()
    scalars_result.all.return_value = [object() for _ in range(n)]
    db.scalars.return_value = scalars_result
    return db


def test_upsert_batches_into_chunked_statements(monkeypatch) -> None:
    # Replace per-line value extraction with a constant row so no real ORM line is needed.
    monkeypatch.setattr(
        facts_mod,
        "_row_values_from_evidence",
        lambda line: {"source_key": "k", "fact_upsert_key": "k", "import_job_id": 1, "line_state": "open_order"},
    )
    monkeypatch.setattr(facts_mod, "_upsert_shipped_chunk", lambda db, tbl, rows: None)
    monkeypatch.setattr(facts_mod, "_upsert_open_order_chunk", lambda db, tbl, rows: db.execute(MagicMock()) or None)
    db = _db_with_lines(1200)
    progress: list[tuple[int, int]] = []

    n = facts_mod.upsert_inbound_shipment_facts_for_job(
        db, 32, on_progress=lambda cur, tot: progress.append((cur, tot)), chunk_size=500
    )

    assert n == 1200
    # 1200 rows / 500 per chunk -> 3 execute calls (not 1200 round-trips).
    assert db.execute.call_count == 3
    assert progress == [(500, 1200), (1000, 1200), (1200, 1200)]
    db.flush.assert_called_once()


def test_upsert_single_chunk_and_empty(monkeypatch) -> None:
    monkeypatch.setattr(
        facts_mod,
        "_row_values_from_evidence",
        lambda line: {"source_key": "k", "fact_upsert_key": "k", "import_job_id": 1, "line_state": "open_order"},
    )
    monkeypatch.setattr(facts_mod, "_upsert_shipped_chunk", lambda db, tbl, rows: None)
    monkeypatch.setattr(facts_mod, "_upsert_open_order_chunk", lambda db, tbl, rows: db.execute(MagicMock()) or None)

    db = _db_with_lines(3)
    progress: list[tuple[int, int]] = []
    n = facts_mod.upsert_inbound_shipment_facts_for_job(
        db, 32, on_progress=lambda cur, tot: progress.append((cur, tot)), chunk_size=500
    )
    assert n == 3
    assert db.execute.call_count == 1
    assert progress == [(3, 3)]

    db_empty = _db_with_lines(0)
    progress_empty: list[tuple[int, int]] = []
    n0 = facts_mod.upsert_inbound_shipment_facts_for_job(
        db_empty, 32, on_progress=lambda cur, tot: progress_empty.append((cur, tot))
    )
    assert n0 == 0
    db_empty.execute.assert_not_called()
    assert progress_empty == []


def test_run_shipment_apply_sync_orchestration(monkeypatch) -> None:
    job = MagicMock()
    job.template_slug = "inbound_shipments"
    db = MagicMock()
    db.get.return_value = job
    db.scalar.return_value = 0

    monkeypatch.setattr(apply_mod, "persist_pipeline_worker_started_at", lambda s, j: None)
    monkeypatch.setattr(apply_mod, "persist_clear_background_task_metadata", lambda s, j: None)
    monkeypatch.setattr(apply_mod, "apply_high_confidence_shipment_mapping_candidates", lambda job_id: 2)
    monkeypatch.setattr(apply_mod, "upsert_inbound_shipment_facts_for_job", lambda db, job_id, on_progress=None: 1200)

    phases: list[str] = []
    out = apply_mod.run_shipment_apply_sync(
        db, 32, on_progress=lambda phase, label, cur, tot: phases.append(phase)
    )

    assert out == {
        "id": 32,
        "outcome": "applied",
        "auto_applied_candidate_count": 2,
        "fact_rows": 1200,
        "unresolved_product_rows": 0,
    }
    assert job.stage == STAGE_LOADED
    assert job.status == "completed"
    assert job.completed_at is not None
    # Phases drive the progress UI: mappings first, fact write, then complete.
    assert phases[0] == "applying_mappings"
    assert "writing_facts" in phases
    assert phases[-1] == "complete"
    assert db.commit.call_count >= 2


def test_run_shipment_apply_sync_rejects_non_shipment_job() -> None:
    job = MagicMock()
    job.template_slug = "distributor_inventory"
    db = MagicMock()
    db.get.return_value = job

    out = apply_mod.run_shipment_apply_sync(db, 99)

    assert out == {"id": 99, "outcome": "not_found"}
    db.commit.assert_not_called()
