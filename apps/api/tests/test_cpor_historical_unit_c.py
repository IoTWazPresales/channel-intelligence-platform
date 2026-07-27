"""Unit C — CPOR historical token surrogate, enrichment, and resolution-plan engine.

No ``cip`` writes: model-level tests use an isolated in-memory SQLite table (the surrogate
table has no JSONB/Postgres-only columns, so it round-trips cleanly); service-level tests
use plain fakes/monkeypatch instead of a real session. Real-DB verification of the migration
itself (grants, FK cascade, sequence) is deferred to the parent after ``alembic upgrade`` is
applied — this task explicitly does not run migrations.
"""

from __future__ import annotations

import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.models.cpor_historical import ImportCporHistoricalStagingLine, ImportCporHistoricalTokenSurrogate


@compiles(BigInteger, "sqlite")
def _bigint_as_integer_on_sqlite(type_, compiler, **kw):
    """SQLite only aliases a bare ``INTEGER PRIMARY KEY`` to its rowid (autoincrement).

    Postgres's ``BIGSERIAL`` has no bearing on the surrogate id's *behavior* under test here
    (get-or-create idempotency, unique constraint, race recovery) — only SQLite's DDL rendering
    needs adjusting so the in-memory table actually autoincrements.
    """
    return "INTEGER"
from app.services.cpor.historical_import import resolution_plan, resolution_plan_apply_sync, token_surrogate
from app.services.cpor.historical_import.resolution_plan import build_cpor_historical_resolution_plan_sync
from app.services.cpor.historical_import.resolve import (
    _accumulate_token,
    _new_token_aggregate,
    _raw_sample_for_token,
    enrich_unresolved_candidate,
)
from app.services.cpor.historical_import.token_surrogate import get_or_create_token_surrogate
from app.services.imports.import_background_slots import (
    KIND_CPOR_RESOLUTION_PLAN,
    SLOT_CPOR_RESOLUTION_PLAN,
    SLOT_MAIN,
    clear_all_task_slots,
    clear_task_slot_on_job,
    iter_active_slots,
    set_task_slot_on_job,
    slot_meta_keys,
)

# --- Phase 1: token surrogate get-or-create -------------------------------------------------


def _sqlite_session():
    engine = create_engine("sqlite:///:memory:")
    ImportCporHistoricalTokenSurrogate.__table__.create(engine)
    return sessionmaker(bind=engine)()


def test_get_or_create_token_surrogate_idempotent_within_session():
    db = _sqlite_session()
    try:
        id1 = get_or_create_token_surrogate(db, job_id=1, entity="product", token="X515")
        id2 = get_or_create_token_surrogate(db, job_id=1, entity="product", token="X515")
        assert id1 == id2
    finally:
        db.close()


def test_get_or_create_token_surrogate_idempotent_across_commits():
    db = _sqlite_session()
    try:
        id1 = get_or_create_token_surrogate(db, job_id=1, entity="product", token="X515")
        db.commit()
        id2 = get_or_create_token_surrogate(db, job_id=1, entity="product", token="X515")
        assert id1 == id2
    finally:
        db.close()


def test_get_or_create_token_surrogate_distinct_per_entity_and_job():
    db = _sqlite_session()
    try:
        pid = get_or_create_token_surrogate(db, job_id=1, entity="product", token="X515")
        cid = get_or_create_token_surrogate(db, job_id=1, entity="customer", token="X515")
        other_job_id = get_or_create_token_surrogate(db, job_id=2, entity="product", token="X515")
        assert len({pid, cid, other_job_id}) == 3
    finally:
        db.close()


def test_get_or_create_token_surrogate_rejects_bad_entity():
    db = _sqlite_session()
    try:
        with pytest.raises(ValueError):
            get_or_create_token_surrogate(db, job_id=1, entity="dealer", token="X")
    finally:
        db.close()


def test_token_surrogate_unique_constraint_enforced_at_db_level():
    db = _sqlite_session()
    try:
        db.add(ImportCporHistoricalTokenSurrogate(import_job_id=1, entity="product", token="X515"))
        db.commit()
        db.add(ImportCporHistoricalTokenSurrogate(import_job_id=1, entity="product", token="X515"))
        with pytest.raises(IntegrityError):
            db.commit()
    finally:
        db.rollback()
        db.close()


def test_get_or_create_token_surrogate_recovers_from_unique_violation_race(monkeypatch):
    """A concurrent insert winning the unique-constraint race must be recovered, not raised."""
    db = _sqlite_session()
    try:
        real_select = token_surrogate._select_surrogate_id
        calls = {"n": 0}

        def _fake_select(db_, *, job_id, entity, token):
            calls["n"] += 1
            if calls["n"] == 1:
                return None  # pretend the pre-check missed the row (simulated race)
            return real_select(db_, job_id=job_id, entity=entity, token=token)

        monkeypatch.setattr(token_surrogate, "_select_surrogate_id", _fake_select)

        db.add(ImportCporHistoricalTokenSurrogate(import_job_id=9, entity="customer", token="ACME"))
        db.commit()

        result_id = get_or_create_token_surrogate(db, job_id=9, entity="customer", token="ACME")
        assert result_id is not None
        assert calls["n"] == 2
    finally:
        db.close()


# --- Phase 2: enrichment fields on candidate dict -------------------------------------------


def test_enrich_candidate_includes_id_and_enrichment_fields():
    out = enrich_unresolved_candidate(
        entity="customer",
        token="Acme",
        row_count=2,
        customer_index={"ACME": [1]},
        customer_labels={1: "Acme Co"},
        candidate_id=42,
        sample_raw_values=["Acme Retail", "ACME RETAIL LTD"],
        case_codes=["C1", "C2"],
        total_units=30.0,
        total_reported_value=1234.5,
    )
    assert out["id"] == 42
    assert out["sample_raw_values"] == ["Acme Retail", "ACME RETAIL LTD"]
    assert out["case_codes"] == ["C1", "C2"]
    assert out["total_units"] == 30.0
    assert out["total_reported_value"] == 1234.5


def test_enrich_candidate_enrichment_fields_default_when_omitted():
    out = enrich_unresolved_candidate(
        entity="customer", token="NoSuch", row_count=1, customer_index={}, customer_labels={}
    )
    assert out["id"] is None
    assert out["sample_raw_values"] == []
    assert out["case_codes"] == []
    assert out["total_units"] is None
    assert out["total_reported_value"] is None


def _staging_row(**overrides) -> ImportCporHistoricalStagingLine:
    base = dict(
        import_job_id=1,
        source_key="k",
        source_row_number=1,
        sheet_name="Disti Sell out",
        channel="disti",
        case_code="C1",
        raw_source_row={},
    )
    base.update(overrides)
    return ImportCporHistoricalStagingLine(**base)


def test_accumulate_token_prefers_result_qty_over_estimate_qty():
    row = _staging_row(
        estimate_qty=10,
        result_qty=7,
        ttl_result_usd=123.45,
        raw_source_row={"Sales Model Name": "X515", "Distributor": "Mustek"},
    )
    agg = _new_token_aggregate()
    _accumulate_token(agg, row, "X515")
    assert agg["row_count"] == 1
    assert agg["total_units"] == 7.0
    assert agg["total_reported_value"] == 123.45
    assert agg["has_reported_value"] is True
    assert agg["case_codes"] == {"C1"}
    assert agg["samples"] == ["X515"]


def test_accumulate_token_falls_back_to_estimate_qty_when_result_missing():
    row = _staging_row(case_code="C2", estimate_qty=12, result_qty=None)
    agg = _new_token_aggregate()
    _accumulate_token(agg, row, "X515")
    assert agg["total_units"] == 12.0
    assert agg["has_reported_value"] is False
    assert agg["total_reported_value"] == 0.0


def test_accumulate_token_caps_samples_at_three_and_dedupes():
    agg = _new_token_aggregate()
    for i in range(5):
        row = _staging_row(source_key=f"k{i}", raw_source_row={"Sales Model Name": f"X515-{i % 2}"})
        _accumulate_token(agg, row, "X515")
    assert agg["row_count"] == 5
    assert len(agg["samples"]) <= 3
    assert len(agg["samples"]) == len(set(agg["samples"]))


def test_raw_sample_for_token_prefers_raw_row_value_else_token_fallback():
    row = _staging_row(raw_source_row={"Dealer/Retailer": "Computer Mania JHB"})
    assert _raw_sample_for_token(row, "Computer Mania JHB") == "Computer Mania JHB"
    assert _raw_sample_for_token(row, "UNKNOWN-TOKEN") == "UNKNOWN-TOKEN"


# --- Phase 4: resolution plan engine ---------------------------------------------------------


def _candidate(
    cid: int, entity: str, token: str, *, plan_class: str, suggestions: list[dict] | None = None
) -> dict:
    return {
        "id": cid,
        "entity": entity,
        "token": token,
        "row_count": 1,
        "plan_class": plan_class,
        "confidence": suggestions[0]["score"] if suggestions else None,
        "match_reason": suggestions[0]["reason"] if suggestions else None,
        "suggestions": suggestions or [],
    }


def test_plan_row_ready_when_plan_class_ready_to_map():
    cand = _candidate(
        5,
        "customer",
        "Acme",
        plan_class="ready_to_map",
        suggestions=[{"dim_id": 10, "label": "Acme Co", "score": 0.95, "reason": "prefix_match"}],
    )
    row = resolution_plan._plan_row_from_candidate(cand)
    assert row["ready"] is True
    assert row["suggested_action"] == "map_customer"
    assert row["suggested_target_id"] == 10
    assert row["resolution_blockers"] == []


def test_plan_row_not_ready_when_needs_review():
    cand = _candidate(
        6,
        "product",
        "X515",
        plan_class="needs_review",
        suggestions=[{"dim_id": 11, "label": "X515 Pro", "score": 0.8, "reason": "fuzzy_medium"}],
    )
    row = resolution_plan._plan_row_from_candidate(cand)
    assert row["ready"] is False
    assert row["suggested_action"] == "none"
    assert row["suggested_target_id"] is None
    assert row["resolution_blockers"] == ["needs_review"]


def test_plan_row_not_ready_when_no_match():
    cand = _candidate(7, "distributor", "ZZZ", plan_class="no_match")
    row = resolution_plan._plan_row_from_candidate(cand)
    assert row["ready"] is False
    assert row["suggested_target_id"] is None
    assert row["resolution_blockers"] == ["no_match"]


def test_plan_row_not_ready_when_ambiguous_even_with_suggestions():
    cand = _candidate(
        8,
        "customer",
        "Acme",
        plan_class="ambiguous_eligible",
        suggestions=[
            {"dim_id": 1, "label": "Acme A", "score": 1.0, "reason": "exact_key_collision"},
            {"dim_id": 2, "label": "Acme B", "score": 1.0, "reason": "exact_key_collision"},
        ],
    )
    row = resolution_plan._plan_row_from_candidate(cand)
    assert row["ready"] is False
    assert row["suggested_target_id"] is None


class _FakeJob:
    def __init__(self, job_id: int, template_slug: str) -> None:
        self.id = job_id
        self.template_slug = template_slug


class _FakeDb:
    def __init__(self, job: _FakeJob | None) -> None:
        self._job = job

    def get(self, _model, _id):
        return self._job


def test_build_plan_filters_by_candidate_ids(monkeypatch):
    fake_candidates = {
        "customer": [
            _candidate(
                1,
                "customer",
                "Acme",
                plan_class="ready_to_map",
                suggestions=[{"dim_id": 10, "label": "Acme Co", "score": 1.0, "reason": "exact_key"}],
            ),
            _candidate(2, "customer", "Beta", plan_class="no_match"),
        ],
        "product": [],
        "distributor": [],
    }
    monkeypatch.setattr(resolution_plan, "list_unresolved_candidates", lambda db, *, job_id: fake_candidates)

    db = _FakeDb(_FakeJob(1, "cpor_historical_cases"))
    out = build_cpor_historical_resolution_plan_sync(db, 1, candidate_ids=[1])
    assert out["summary"]["total"] == 1
    assert out["summary"]["ready"] == 1
    assert out["rows"][0]["candidate_id"] == 1
    assert out["rows"][0]["ready"] is True


def test_build_plan_full_set_when_no_candidate_ids(monkeypatch):
    fake_candidates = {
        "customer": [
            _candidate(1, "customer", "Acme", plan_class="ready_to_map", suggestions=[{"dim_id": 10, "label": "A", "score": 1.0, "reason": "exact_key"}]),
            _candidate(2, "customer", "Beta", plan_class="no_match"),
        ],
        "product": [],
        "distributor": [],
    }
    monkeypatch.setattr(resolution_plan, "list_unresolved_candidates", lambda db, *, job_id: fake_candidates)

    db = _FakeDb(_FakeJob(1, "cpor_historical_cases"))
    out = build_cpor_historical_resolution_plan_sync(db, 1)
    assert out["summary"]["total"] == 2
    assert out["summary"]["ready"] == 1
    assert out["summary"]["not_ready"] == 1


def test_build_plan_raises_for_wrong_template_slug():
    db = _FakeDb(_FakeJob(1, "distributor_inventory"))
    with pytest.raises(ValueError):
        build_cpor_historical_resolution_plan_sync(db, 1)


def test_build_plan_raises_for_missing_job():
    db = _FakeDb(None)
    with pytest.raises(ValueError):
        build_cpor_historical_resolution_plan_sync(db, 1)


# --- Phase 4: resolution plan apply (per-token, never bulk single-target) --------------------


class _FakeSession:
    def __init__(self) -> None:
        self.committed = False

    def commit(self) -> None:
        self.committed = True


def test_apply_orchestrator_applies_ready_and_skips_not_ready(monkeypatch):
    plan = {
        "rows": [
            {
                "candidate_id": 1,
                "entity": "customer",
                "token": "Acme",
                "ready": True,
                "suggested_target_id": 10,
                "plan_class": "ready_to_map",
            },
            {
                "candidate_id": 2,
                "entity": "product",
                "token": "X515",
                "ready": False,
                "suggested_target_id": None,
                "plan_class": "needs_review",
            },
        ],
        "summary": {"total": 2, "ready": 1, "not_ready": 1},
    }
    monkeypatch.setattr(
        resolution_plan_apply_sync,
        "build_cpor_historical_resolution_plan_sync",
        lambda session, job_id, candidate_ids=None: plan,
    )
    calls: list[tuple] = []

    def _fake_map(session, *, job_id, entity, token, dim_id):
        calls.append((job_id, entity, token, dim_id))
        return 3

    monkeypatch.setattr(resolution_plan_apply_sync, "map_staging_token", _fake_map)

    session = _FakeSession()
    out = resolution_plan_apply_sync.run_cpor_historical_resolution_plan_apply_orchestrator(
        session, 1, {"candidate_ids": [1, 2]}
    )
    assert out["applied"] == 1
    assert out["skipped_not_ready"] == 1
    assert out["failed"] == 0
    assert calls == [(1, "customer", "Acme", 10)]  # per-token, its own target — never bulk single-target
    statuses = {r["candidate_id"]: r["status"] for r in out["results"]}
    assert statuses[1] == "applied"
    assert statuses[2] == "skipped_not_ready"
    assert session.committed is True


def test_apply_orchestrator_two_ready_candidates_map_to_different_targets(monkeypatch):
    """D-013: per-token → its own top suggestion target — asserts no bulk single-target reuse."""
    plan = {
        "rows": [
            {"candidate_id": 1, "entity": "customer", "token": "Acme", "ready": True, "suggested_target_id": 10},
            {"candidate_id": 2, "entity": "customer", "token": "Beta", "ready": True, "suggested_target_id": 20},
        ],
        "summary": {"total": 2, "ready": 2, "not_ready": 0},
    }
    monkeypatch.setattr(
        resolution_plan_apply_sync,
        "build_cpor_historical_resolution_plan_sync",
        lambda session, job_id, candidate_ids=None: plan,
    )
    calls: list[tuple] = []
    monkeypatch.setattr(
        resolution_plan_apply_sync,
        "map_staging_token",
        lambda session, *, job_id, entity, token, dim_id: calls.append((token, dim_id)) or 1,
    )
    out = resolution_plan_apply_sync.run_cpor_historical_resolution_plan_apply_orchestrator(
        _FakeSession(), 1, {"candidate_ids": [1, 2]}
    )
    assert out["applied"] == 2
    assert calls == [("Acme", 10), ("Beta", 20)]
    assert len({dim_id for _tok, dim_id in calls}) == 2


def test_apply_orchestrator_candidate_not_found_in_plan(monkeypatch):
    monkeypatch.setattr(
        resolution_plan_apply_sync,
        "build_cpor_historical_resolution_plan_sync",
        lambda session, job_id, candidate_ids=None: {"rows": [], "summary": {"total": 0, "ready": 0, "not_ready": 0}},
    )
    out = resolution_plan_apply_sync.run_cpor_historical_resolution_plan_apply_orchestrator(
        _FakeSession(), 1, {"candidate_ids": [99]}
    )
    assert out["failed"] == 1
    assert out["results"][0]["detail"] == "candidate_not_found"


def test_apply_orchestrator_map_failure_is_isolated_per_candidate(monkeypatch):
    plan = {
        "rows": [{"candidate_id": 1, "entity": "customer", "token": "Acme", "ready": True, "suggested_target_id": 10}],
        "summary": {"total": 1, "ready": 1, "not_ready": 0},
    }
    monkeypatch.setattr(
        resolution_plan_apply_sync,
        "build_cpor_historical_resolution_plan_sync",
        lambda session, job_id, candidate_ids=None: plan,
    )

    def _boom(session, *, job_id, entity, token, dim_id):
        raise RuntimeError("db exploded")

    monkeypatch.setattr(resolution_plan_apply_sync, "map_staging_token", _boom)
    out = resolution_plan_apply_sync.run_cpor_historical_resolution_plan_apply_orchestrator(
        _FakeSession(), 1, {"candidate_ids": [1]}
    )
    assert out["failed"] == 1
    assert out["applied"] == 0
    assert "db exploded" in out["results"][0]["detail"]


# --- Task names distinct from case-apply; slot registration ----------------------------------


def test_resolution_plan_task_names_distinct_from_case_apply():
    from app.services.cpor.historical_import.resolution_plan_enqueue import (
        TASK_CPOR_RESOLUTION_PLAN_APPLY,
        TASK_CPOR_RESOLUTION_PLAN_COMPUTE,
    )

    assert TASK_CPOR_RESOLUTION_PLAN_APPLY == "imports.cpor_historical_resolution_plan_apply"
    assert TASK_CPOR_RESOLUTION_PLAN_COMPUTE == "imports.cpor_historical_resolution_plan_compute"
    assert TASK_CPOR_RESOLUTION_PLAN_APPLY != "imports.cpor_historical_apply"
    assert TASK_CPOR_RESOLUTION_PLAN_COMPUTE != "imports.cpor_historical_apply"


def test_cpor_resolution_plan_slot_is_registered_and_not_slot_main():
    assert SLOT_CPOR_RESOLUTION_PLAN != SLOT_MAIN
    assert "cpor_resolution_plan_task" in slot_meta_keys()


def test_set_and_clear_single_cpor_resolution_plan_slot():
    job = type(
        "J", (), {"id": 1, "template_slug": "cpor_historical_cases", "import_mode": None, "staged_metadata": None}
    )()
    set_task_slot_on_job(job, SLOT_CPOR_RESOLUTION_PLAN, task_id="tid-1", async_poll=True, label="Computing…")
    slots = list(iter_active_slots(job))
    assert len(slots) == 1
    assert slots[0].slot_key == SLOT_CPOR_RESOLUTION_PLAN
    assert slots[0].kind == KIND_CPOR_RESOLUTION_PLAN
    assert slots[0].task_id == "tid-1"

    clear_task_slot_on_job(job, SLOT_CPOR_RESOLUTION_PLAN)
    assert list(iter_active_slots(job)) == []


def test_clear_all_task_slots_clears_cpor_resolution_plan_slot_alongside_main():
    meta = {
        "cpor_resolution_plan_task": {"task_id": "abc", "async_poll": True},
        "celery_task_id": "main-1",
        "pipeline_queued_at": "2026-01-01T00:00:00+00:00",
    }
    cleared = clear_all_task_slots(meta)
    assert cleared is None
