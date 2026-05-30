"""Product Master mapping: allow-list, dispositions, validate vs commit guards."""

import json
from datetime import datetime
from unittest.mock import MagicMock

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app

from app.services.imports.pm_commit_catalog import commit_catalog_and_eav
from app.services.imports.product_master_workflow import (
    STAGE_PM_COMMITTED,
    STAGE_PM_MAPPING,
    STAGE_PM_VALIDATED,
    STATUS_PM_VALIDATE_RUNNING,
    build_pm_import_progress,
    commit_product_master_sync,
    inferred_schema_for_state_payload,
    reconcile_stale_pm_validate_sync,
    save_mapping_sync,
    suggest_mapping_decisions,
    validate_mapping_payload,
    validate_product_master_sync,
)


def test_validate_mapping_rejects_unknown_target() -> None:
    headers = ["a", "b", "c"]
    cols = [
        {"header": "a", "target": "technical_product_id"},
        {"header": "b", "target": "display_name"},
        {"header": "c", "target": "not_a_real_field"},
    ]
    errs = validate_mapping_payload(headers, cols)
    assert any("Unknown canonical target" in e for e in errs)


def test_validate_mapping_requires_disposition_when_unmapped() -> None:
    headers = ["id_col", "name_col", "extra"]
    cols = [
        {"header": "id_col", "target": "technical_product_id"},
        {"header": "name_col", "target": "display_name"},
        {"header": "extra", "disposition": ""},
    ]
    errs = validate_mapping_payload(headers, cols)
    assert any("needs disposition" in e for e in errs)


def test_validate_mapping_stage_raw_and_attribute_candidate_ok() -> None:
    headers = ["id", "title", "junk", "maybe"]
    cols = [
        {"header": "id", "target": "technical_product_id"},
        {"header": "title", "target": "display_name"},
        {"header": "junk", "disposition": "ignore"},
        {"header": "maybe", "disposition": "attribute_candidate"},
    ]
    assert validate_mapping_payload(headers, cols) == []


def test_validate_mapping_duplicate_identity_generic() -> None:
    headers = ["a", "b", "c"]
    cols = [
        {"header": "a", "target": "technical_product_id"},
        {"header": "b", "target": "sku"},
        {"header": "c", "target": "display_name"},
    ]
    # legacy sku normalizes to technical_product_id → duplicate
    errs = validate_mapping_payload(headers, cols)
    assert any("more than once" in e for e in errs)


def test_validate_mapping_requires_display_and_identity_once() -> None:
    headers = ["x", "y"]
    cols = [{"header": "x", "target": "technical_product_id"}, {"header": "y", "disposition": "ignore"}]
    errs = validate_mapping_payload(headers, cols)
    assert any("display_name" in e.lower() or "required" in e.lower() for e in errs)

    headers2 = ["a", "b", "c"]
    cols2 = [
        {"header": "a", "target": "technical_product_id"},
        {"header": "b", "target": "display_name"},
        {"header": "c", "target": "display_name"},
    ]
    errs2 = validate_mapping_payload(headers2, cols2)
    assert any("more than once" in e for e in errs2)


def test_suggest_mapping_uses_template_and_inferred() -> None:
    source = MagicMock()
    source.import_template = MagicMock()
    source.expected_template = None
    source.import_template.expected_columns = {
        "sku": {"aliases": ["Item SKU"]},
        "name": {"aliases": ["Title"]},
    }
    headers = ["Item SKU", "Title", "Random vendor notes"]
    inf = {
        "columns": [
            {"name": "Item SKU", "dtype": "object", "sample": ["90NB0F12-M00000"]},
            {"name": "Title", "dtype": "object", "sample": ["Laptop 15"]},
        ]
    }
    out = suggest_mapping_decisions(headers, source, inf)
    assert out["Item SKU"]["target"] == "technical_product_id"
    assert out["Title"]["target"] == "display_name"
    assert out["Random vendor notes"]["disposition"] == "ignore"


def test_suggest_mapping_exact_header_wins_form_factor_and_series() -> None:
    """Exact/near-legacy header matches must dominate weak fuzzy and template `name` noise."""
    source = MagicMock()
    source.import_template = MagicMock()
    source.expected_template = None
    source.import_template.expected_columns = {
        "sku": {"aliases": ["Item SKU"]},
        "name": {"aliases": ["Title"]},
    }
    headers = ["form_factor", "series_name"]
    inf = {
        "columns": [
            {"name": "form_factor", "dtype": "object", "sample": ["Notebook - Standard"]},
            {"name": "series_name", "dtype": "object", "sample": ["ROG Strix"]},
        ]
    }
    out = suggest_mapping_decisions(headers, source, inf)
    assert out["form_factor"]["target"] == "form_factor"
    assert out["series_name"]["target"] == "series"
    assert "exact_header_match" in (out["form_factor"].get("reasons") or [])


def test_suggest_mapping_memory_capacity_range_not_series() -> None:
    """Regression: lone `range` substring must not map capacity columns to series."""
    source = MagicMock()
    source.import_template = MagicMock()
    source.expected_template = None
    source.import_template.expected_columns = {}
    headers = ["memory_capacity_range"]
    inf = {"columns": [{"name": "memory_capacity_range", "dtype": "object", "sample": ["8 - 16 GB"]}]}
    out = suggest_mapping_decisions(headers, source, inf)
    assert out["memory_capacity_range"].get("target") != "series"


def test_validate_product_master_requires_mapping_stage() -> None:
    db = MagicMock()
    job = MagicMock()
    job.template_slug = "product_master"
    job.stage = "pm_headers_ready"
    job.mapping_decisions = {"x": {"target": "technical_product_id"}}
    db.get.return_value = job
    with pytest.raises(ValueError, match="save mapping"):
        validate_product_master_sync(db, 1)


def test_commit_requires_validated_and_passed() -> None:
    db = MagicMock()

    def _exec_result(j):
        r = MagicMock()
        r.scalar_one_or_none.return_value = j
        return r

    job = MagicMock()
    job.template_slug = "product_master"
    job.stage = STAGE_PM_MAPPING
    job.validation_passed = None
    db.execute.return_value = _exec_result(job)
    with pytest.raises(ValueError, match="validate successfully"):
        commit_product_master_sync(db, 99, confirm_destructive=False)

    job2 = MagicMock()
    job2.template_slug = "product_master"
    job2.stage = STAGE_PM_VALIDATED
    job2.validation_passed = False
    db.execute.return_value = _exec_result(job2)
    with pytest.raises(ValueError, match="validate successfully"):
        commit_product_master_sync(db, 99, confirm_destructive=False)


def test_product_master_api_requires_admin() -> None:
    with TestClient(app) as client:
        r = client.get("/api/v1/imports/product-master/jobs/1/state")
        assert r.status_code == 403
        assert "admin" in r.json().get("detail", "").lower()


def test_commit_catalog_skips_without_product_catalog_id() -> None:
    db = MagicMock()
    job = MagicMock(id=1, template_slug="product_master")
    source = MagicMock(product_catalog_id=None)
    df = pd.DataFrame([{"sku": "A", "name": "N"}])
    n = commit_catalog_and_eav(
        db,
        job,
        source,
        df,
        mapping_decisions={},
        staged_row_values={},
        technical_id_col="sku",
        name_col="name",
    )
    assert n == 0
    db.scalars.assert_not_called()


def test_namespace_for_catalog_staged_is_deterministic() -> None:
    from app.services.imports import pm_commit_catalog as m

    assert m._namespace_for(5, "staged", "Foo Bar!!") == "catalog:5:staged:foo_bar"
    assert m._namespace_for(5, "candidate", "Foo Bar!!") == "catalog:5:candidate:foo_bar"


def test_validate_product_master_staged_metadata_is_json_serializable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression: staged_metadata JSONB must not contain raw datetime (psycopg serialization)."""
    df = pd.DataFrame(
        {
            "sku": ["A1"],
            "name": ["Widget"],
            "ship_date": [datetime(2024, 6, 15, 14, 30, 0)],
        }
    )

    monkeypatch.setattr(
        "app.services.imports.product_master_workflow.read_tabular",
        lambda fn, data: df,
    )
    monkeypatch.setattr(
        "app.services.imports.product_master_workflow.get_storage_backend",
        lambda: MagicMock(read=lambda key: b""),
    )

    job = MagicMock()
    job.id = 42
    job.template_slug = "product_master"
    job.stage = STAGE_PM_MAPPING
    job.mapping_decisions = {
        "sku": {"target": "technical_product_id"},
        "name": {"target": "display_name"},
        "ship_date": {"disposition": "stage_raw"},
    }
    job.file_headers = ["sku", "name", "ship_date"]
    job.file_name = "t.csv"

    raw_meta = MagicMock(storage_key="k")
    scal_raw = MagicMock()
    scal_raw.one.return_value = raw_meta
    scal_ch = MagicMock()
    scal_ch.all.return_value = []

    db = MagicMock()
    db.get.return_value = job
    job.status = "validate_running"
    db.scalars.side_effect = [scal_raw, scal_ch]
    db.execute = MagicMock()

    validate_product_master_sync(db, 42, from_worker=True)

    assert db.execute.called

    json.dumps(job.staged_metadata)
    assert str(job.staged_metadata["0"]["ship_date"]).startswith("2024-06-15")


def test_build_pm_import_progress_committed() -> None:
    job = MagicMock()
    job.stage = STAGE_PM_COMMITTED
    job.validation_passed = True
    job.inferred_schema = {"row_count": 120}
    job.staged_metadata = {"0": {"x": 1}}
    job.error_summary = None
    job.started_at = None
    job.updated_at = None
    job.completed_at = None
    out = build_pm_import_progress(job, {"info": 2, "warning": 1, "error": 0})
    assert out["phase_id"] == "committed"
    assert out["rail_index"] == 4
    assert all(s["state"] == "complete" for s in out["steps"])


def test_save_mapping_rejects_wrong_stage() -> None:
    db = MagicMock()
    job = MagicMock()
    job.template_slug = "product_master"
    job.stage = "pm_committed"
    job.file_headers = ["id", "title"]
    db.get.return_value = job
    cols = [
        {"header": "id", "target": "technical_product_id"},
        {"header": "title", "target": "display_name"},
    ]
    with pytest.raises(ValueError, match="editable mapping stage"):
        save_mapping_sync(db, 1, cols)


def test_inferred_schema_for_state_payload_trims_samples() -> None:
    big = {"columns": [{"name": "a", "dtype": "object", "sample": list(range(20))}], "row_count": 1}
    slim = inferred_schema_for_state_payload(big)
    assert isinstance(slim, dict)
    assert len(slim["columns"][0]["sample"]) == 2


def test_reconcile_stale_pm_validate_clears_abandoned_running() -> None:
    from datetime import datetime, timedelta, timezone

    from app.models.ingestion import ImportJob

    old = datetime.now(timezone.utc) - timedelta(minutes=45)
    job = ImportJob(
        template_slug="product_master",
        stage=STAGE_PM_MAPPING,
        status=STATUS_PM_VALIDATE_RUNNING,
        staged_metadata={
            "pm_validate_task": {
                "task_id": "dead-task-id",
                "queued_at": old.isoformat(),
                "async_poll": True,
            }
        },
    )
    db = MagicMock()
    db.add = MagicMock()
    db.commit = MagicMock()

    changed = reconcile_stale_pm_validate_sync(db, job)
    assert changed is True
    assert job.status == "draft"
    assert job.staged_metadata is None or "pm_validate_task" not in (job.staged_metadata or {})
