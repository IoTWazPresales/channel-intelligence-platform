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


def _no_retire(monkeypatch) -> None:
    """These tests count the chunk round trips; the PO-less twin retire step has its own test below."""
    monkeypatch.setattr(
        facts_mod, "retire_po_less_twins_written_by_job", lambda db, job_id: {"retired": 0, "repointed": 0, "quantity_differs": []}
    )


def test_upsert_retires_po_less_twins_after_the_chunks(monkeypatch) -> None:
    monkeypatch.setattr(
        facts_mod,
        "_row_values_from_evidence",
        lambda line, **_: {"source_key": "k", "fact_upsert_key": f"k{id(line)}", "import_job_id": 1, "line_state": "open_order"},
    )
    monkeypatch.setattr(facts_mod, "_upsert_open_order_chunk", lambda db, tbl, rows: None)
    seen: list[int] = []

    def fake(db, job_id):
        seen.append(job_id)
        return {"retired": 2, "repointed": 0, "quantity_differs": [(5, 4.0, 3.0)]}

    monkeypatch.setattr(facts_mod, "retire_po_less_twins_written_by_job", fake)
    db = _db_with_lines(3)
    assert facts_mod.upsert_inbound_shipment_facts_for_job(db, 32) == 3
    assert seen == [32]
    db.flush.assert_called()


def test_upsert_batches_into_chunked_statements(monkeypatch) -> None:
    _no_retire(monkeypatch)
    # Replace per-line value extraction with a constant row so no real ORM line is needed.
    monkeypatch.setattr(
        facts_mod,
        "_row_values_from_evidence",
        lambda line, **_: {"source_key": "k", "fact_upsert_key": f"k{id(line)}", "import_job_id": 1, "line_state": "open_order"},
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


def test_lines_of_one_fact_key_are_never_split_across_chunks(monkeypatch) -> None:
    """Rows of one key add up inside a chunk and a later chunk replaces the key: they must share a chunk (units were lost otherwise)."""
    _no_retire(monkeypatch)
    keys = iter(["A", "B", "C", "A", "D", "B", "A", "E"])
    lines = [object() for _ in range(8)]
    by_line = {id(ln): k for ln, k in zip(lines, keys)}
    monkeypatch.setattr(
        facts_mod, "_row_values_from_evidence",
        lambda line, **_: {"source_key": by_line[id(line)], "fact_upsert_key": by_line[id(line)], "import_job_id": 1, "line_state": "shipped"},
    )
    seen: list[list[str]] = []
    monkeypatch.setattr(facts_mod, "_upsert_evidence_chunk", lambda db, tbl, chunk, values, **_: seen.append([v["fact_upsert_key"] for v in values]))
    db = MagicMock()
    db.scalars.return_value.all.return_value = lines
    assert facts_mod.upsert_inbound_shipment_facts_for_job(db, 32, chunk_size=3) == 8
    flat = [k for c in seen for k in c]
    assert sorted(flat) == sorted(by_line.values())
    for key in set(flat):
        assert sum(1 for c in seen if key in c) == 1, f"{key} was split across chunks: {seen}"
    assert all(len(c) <= 3 or len(set(c)) == 1 for c in seen)  # a chunk is full, or one key that does not fit anywhere else


def test_upsert_single_chunk_and_empty(monkeypatch) -> None:
    _no_retire(monkeypatch)
    monkeypatch.setattr(
        facts_mod,
        "_row_values_from_evidence",
        lambda line, **_: {"source_key": "k", "fact_upsert_key": f"k{id(line)}", "import_job_id": 1, "line_state": "open_order"},
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
    monkeypatch.setattr(
        apply_mod, "write_shipment_facts_and_close_book",
        lambda db, job, on_progress=None: {"fact_rows": 1200, "closed": 0, "skipped_reason": None},
    )

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
