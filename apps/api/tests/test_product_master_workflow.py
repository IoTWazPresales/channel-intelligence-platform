"""Product Master mapping: allow-list, dispositions, validate vs commit guards."""

import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app

from app.services.imports.pm_commit_catalog import commit_catalog_and_eav
from app.services.imports.pm_staging import PM_STAGED_ROW_COUNT_KEY, pm_staged_row_count_from_metadata
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
        r = client.get(
            "/api/v1/imports/product-master/jobs/1/state",
            headers={"X-User-Role": "viewer"},
        )
        assert r.status_code == 403
        assert r.json().get("detail") == "Insufficient role"


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
        products_by_sku={},
        technical_id_col="sku",
        name_col="name",
    )
    assert n == 0
    db.scalars.assert_not_called()


def test_namespace_for_catalog_staged_is_deterministic() -> None:
    from app.services.imports import pm_commit_catalog as m

    assert m._namespace_for(5, "staged", "Foo Bar!!") == "catalog:5:staged:foo_bar"
    assert m._namespace_for(5, "candidate", "Foo Bar!!") == "catalog:5:candidate:foo_bar"


class _RecordingSession:
    """Minimal sync-Session stand-in that records added objects and assigns ids on flush."""

    def __init__(self) -> None:
        self.added: list[object] = []
        self._next_id = 0

    def scalars(self, *_a, **_k):
        m = MagicMock()
        m.all.return_value = []
        m.first.return_value = None
        return m

    def add(self, obj) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                self._next_id += 1
                obj.id = self._next_id


def _eav_fixture():
    from app.models.product_catalog import CatalogProduct, ProductAttributeValue

    df = pd.DataFrame(
        {
            "sku": ["SKU-1", "SKU-2"],
            "name": ["Alpha", "Beta"],
            "color": ["Red", "Blue"],
            "warranty": ["24mo", "12mo"],
        }
    )
    mapping = {
        "sku": {"target": "technical_product_id"},
        "name": {"target": "display_name"},
        "color": {"disposition": "stage_raw"},
        "warranty": {"disposition": "attribute_candidate"},
    }
    products = {
        "SKU-1": SimpleNamespace(id=101, sku="SKU-1"),
        "SKU-2": SimpleNamespace(id=102, sku="SKU-2"),
    }
    job = SimpleNamespace(id=7, template_slug="product_master")
    source = SimpleNamespace(product_catalog_id=10)
    return df, mapping, products, job, source, CatalogProduct, ProductAttributeValue


def test_commit_catalog_skips_eav_by_default_but_writes_catalog_product() -> None:
    df, mapping, products, job, source, CatalogProduct, ProductAttributeValue = _eav_fixture()
    db = _RecordingSession()

    n = commit_catalog_and_eav(
        db,
        job,
        source,
        df,
        mapping_decisions=mapping,
        products_by_sku=products,
        technical_id_col="sku",
        name_col="name",
        # write_attribute_values defaults to False
    )

    assert n == 2
    assert any(isinstance(o, CatalogProduct) for o in db.added), "catalog_product must still be written"
    assert not any(
        isinstance(o, ProductAttributeValue) for o in db.added
    ), "legacy EAV rows must NOT be written by default"


def test_commit_catalog_writes_eav_when_flag_enabled() -> None:
    df, mapping, products, job, source, CatalogProduct, ProductAttributeValue = _eav_fixture()
    db = _RecordingSession()

    commit_catalog_and_eav(
        db,
        job,
        source,
        df,
        mapping_decisions=mapping,
        products_by_sku=products,
        technical_id_col="sku",
        name_col="name",
        write_attribute_values=True,
    )

    assert any(
        isinstance(o, ProductAttributeValue) for o in db.added
    ), "legacy EAV rows must be written when the flag is on"


def test_validate_persists_staged_row_count_not_row_index_map(monkeypatch: pytest.MonkeyPatch) -> None:
    """Validate stores pm_staged_row_count only; staging values are derived at commit from the file."""
    df = pd.DataFrame(
        {
            "sku": ["90NB0F12-M00000", "90NB0F12-M00001"],
            "name": ["Widget Alpha", "Gadget Beta"],
            "ship_date": [datetime(2024, 6, 15, 14, 30, 0), datetime(2024, 7, 1)],
            "notes": ["n1", "n2"],
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

    job = SimpleNamespace(
        id=42,
        template_slug="product_master",
        stage=STAGE_PM_MAPPING,
        status="validate_running",
        mapping_decisions={
            "sku": {"target": "technical_product_id"},
            "name": {"target": "display_name"},
            "ship_date": {"disposition": "stage_raw"},
            "notes": {"disposition": "stage_raw"},
        },
        file_headers=["sku", "name", "ship_date", "notes"],
        file_name="t.csv",
        staged_metadata={"pm_validate_task": {"task_id": "t1"}},
        validation_passed=None,
        error_summary=None,
    )

    raw_meta = MagicMock(storage_key="k")
    scal_raw = MagicMock()
    scal_raw.one.return_value = raw_meta
    scal_ch = MagicMock()
    scal_ch.all.return_value = []

    db = MagicMock()
    db.get.return_value = job
    db.scalars.side_effect = [scal_raw, scal_ch]
    db.execute = MagicMock()
    db.refresh = MagicMock()

    validate_product_master_sync(db, 42, from_worker=True)

    assert db.execute.called
    meta = job.staged_metadata
    assert isinstance(meta, dict)
    assert meta.get(PM_STAGED_ROW_COUNT_KEY) == 2
    assert "0" not in meta
    assert "1" not in meta
    assert "pm_validate_task" not in meta
    json.dumps(meta)


def test_validate_caps_detail_per_code_and_emits_code_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    """A systemic row error (here: blank display_name) must not persist ~all rows: detail is
    capped per code, and the summary row carries accurate code_counts for the UI breakdown."""
    from app.services.imports import product_master_workflow as pmw

    n = 130  # > PM_VALIDATION_DETAIL_CAP_PER_CODE
    df = pd.DataFrame(
        {
            "sku": [f"SKU-{i:05d}" for i in range(n)],
            "name": [""] * n,  # blank display_name → systemic blank_display_name error
        }
    )
    monkeypatch.setattr(pmw, "read_tabular", lambda fn, data: df)
    monkeypatch.setattr(pmw, "get_storage_backend", lambda: MagicMock(read=lambda key: b""))

    captured: dict[str, list] = {}
    monkeypatch.setattr(pmw, "_bulk_insert_row_results", lambda db, rows, **kw: captured.update(rows=rows))

    job = SimpleNamespace(
        id=77,
        template_slug="product_master",
        stage=STAGE_PM_MAPPING,
        status="validate_running",
        mapping_decisions={
            "sku": {"target": "technical_product_id"},
            "name": {"target": "display_name"},
        },
        file_headers=["sku", "name"],
        file_name="t.csv",
        staged_metadata={"pm_validate_task": {"task_id": "t1"}},
        validation_passed=None,
        error_summary=None,
    )

    raw_meta = MagicMock(storage_key="k")
    scal_raw = MagicMock()
    scal_raw.one.return_value = raw_meta

    db = MagicMock()
    db.get.return_value = job
    db.scalars.side_effect = [scal_raw]

    validate_product_master_sync(db, 77, from_worker=True)

    rows = captured["rows"]
    blank_detail = [r for r in rows if r["code"] == "blank_display_name" and r["row_number"] != 0]
    assert len(blank_detail) == pmw.PM_VALIDATION_DETAIL_CAP_PER_CODE  # capped, not 130
    summary = next(r for r in rows if r["code"] == "pm_validation_summary")
    parsed = json.loads(summary["message"])
    assert parsed["row_errors"] == n
    assert parsed["code_counts"]["blank_display_name"] == n  # true total preserved for the UI
    assert job.validation_passed is False
    assert job.status == "validation_failed"


def test_commit_derives_import_staging_without_per_row_product_select(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Commit applies import_staging from file; dim_product SELECT count is O(chunks) not O(rows)."""
    from app.services.imports import product_master_workflow as pmw

    df = pd.DataFrame(
        {
            "sku": ["90NB0F12-M00000", "90NB0F12-M00001"],
            "name": ["Widget Alpha", "Gadget Beta"],
            "color": ["Red", "Blue"],
            "warranty": ["24mo", "12mo"],
        }
    )

    monkeypatch.setattr(pmw, "read_tabular", lambda fn, data: df)
    monkeypatch.setattr(pmw, "get_storage_backend", lambda: MagicMock(read=lambda key: b""))
    monkeypatch.setattr(
        pmw,
        "sync_bulk_upsert_products_from_rows",
        lambda db, payloads: {"created": len(payloads), "updated": 0, "total": len(payloads)},
    )

    eav_calls: dict[str, object] = {}

    def fake_eav(*a, **k):
        eav_calls.update(k)
        return 0

    monkeypatch.setattr(pmw, "commit_catalog_and_eav", fake_eav)

    products = {
        "90NB0F12-M00000": SimpleNamespace(id=1, sku="90NB0F12-M00000", name="Widget Alpha", specs_json={}),
        "90NB0F12-M00001": SimpleNamespace(id=2, sku="90NB0F12-M00001", name="Gadget Beta", specs_json={}),
    }

    def fake_batch_load(db, skus, **kwargs):
        return {s: products[s] for s in skus if s in products}

    monkeypatch.setattr(pmw, "batch_load_dim_products_by_sku", fake_batch_load)

    job = SimpleNamespace(
        id=7,
        template_slug="product_master",
        stage=STAGE_PM_VALIDATED,
        status="validated",
        validation_passed=True,
        mapping_decisions={
            "sku": {"target": "technical_product_id"},
            "name": {"target": "display_name"},
            "color": {"disposition": "stage_raw"},
            "warranty": {"disposition": "attribute_candidate"},
        },
        file_name="t.csv",
        staged_metadata={PM_STAGED_ROW_COUNT_KEY: 2},
        source=SimpleNamespace(import_template=None, product_catalog_id=1),
        pm_commit_meta=None,
        error_summary=None,
        completed_at=None,
        archived_at=None,
        import_mode="validate",
    )

    raw_meta = MagicMock(storage_key="k")
    scal_raw = MagicMock()
    scal_raw.one.return_value = raw_meta

    exec_result = MagicMock()
    exec_result.scalar_one_or_none.return_value = job

    db = MagicMock()
    db.execute.return_value = exec_result
    db.scalars.return_value = scal_raw

    dim_selects: list[str] = []

    def count_scalars(stmt, *a, **kw):
        text = str(stmt)
        if "dim_product" in text.lower() and "sku" in text.lower():
            dim_selects.append(text)
        if "raw_file_metadata" in text.lower():
            return scal_raw
        return MagicMock(all=MagicMock(return_value=[]), first=MagicMock(return_value=None))

    db.scalars.side_effect = count_scalars

    commit_product_master_sync(db, 7, confirm_destructive=False)

    assert products["90NB0F12-M00000"].specs_json.get("import_staging") == {"color": "Red"}
    assert products["90NB0F12-M00001"].specs_json.get("import_staging") == {"color": "Blue"}
    # attribute_candidate columns land under a distinct specs_json key (kept usable + distinguishable)
    assert products["90NB0F12-M00000"].specs_json.get("attribute_candidates") == {"warranty": "24mo"}
    assert products["90NB0F12-M00001"].specs_json.get("attribute_candidates") == {"warranty": "12mo"}
    # legacy EAV write is off by default — commit must pass write_attribute_values=False
    assert eav_calls.get("write_attribute_values") is False
    # batch_load is mocked; commit must not issue per-row DimProduct SELECT by sku
    assert len(dim_selects) == 0


def test_build_pm_import_progress_committed() -> None:
    job = MagicMock()
    job.stage = STAGE_PM_COMMITTED
    job.validation_passed = True
    job.inferred_schema = {"row_count": 120}
    job.staged_metadata = {PM_STAGED_ROW_COUNT_KEY: 1}
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
