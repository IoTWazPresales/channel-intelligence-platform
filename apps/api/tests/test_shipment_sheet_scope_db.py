"""BACKLOG-046 mapping persistence on cip_test; the shared fixture rolls back commits."""

from __future__ import annotations

import io
from uuid import uuid4

import pytest
from openpyxl import Workbook
from sqlalchemy import text

from app.models.iam import Tenant
from app.models.ingestion import ImportJob, ImportTemplate, RawFileMetadata, SourceDefinition
from app.services.imports import shipment_field_mapping as sfm
from tests.store_dc_fixture import session as session  # noqa: F401 - cip_test/savepoint fixture


SHIPPED_COLS = ["Operating Unit", "Delivery No", "Invoice Line", "Qty", "Item", "Bill To"]


def _job(session, monkeypatch, sheets, selected):
    assert session.scalar(text("SELECT current_database()")) == "cip_test"
    print("current_database() = cip_test")
    token = uuid4().hex
    tenant_id = f"scope-{token}"
    session.add(Tenant(id=tenant_id, name="Sheet scope test"))
    template = ImportTemplate(
        slug=f"scope-{token}", display_name="Sheet scope test",
        pipeline_handler="shipment_evidence_import",
    )
    session.add(template)
    session.flush()
    source = SourceDefinition(
        tenant_id=tenant_id, import_template_id=template.id,
        code=f"scope-{token}", name="Sheet scope test", source_kind="file",
    )
    session.add(source)
    session.flush()
    job = ImportJob(
        tenant_id=tenant_id, source_id=source.id, template_slug="inbound_shipments",
        file_name="book.xlsx",
        staged_metadata={
            "available_sheets": list(sheets),
            "selected_sheets": selected,
            "sheet_selection_confirmed": True,
        },
    )
    session.add(job)
    session.flush()
    storage_key = f"imports/test/sheet-scope/{token}.xlsx"
    session.add(RawFileMetadata(job_id=job.id, storage_key=storage_key))
    session.flush()

    workbook = Workbook()
    workbook.remove(workbook.active)
    for name, columns in sheets.items():
        sheet = workbook.create_sheet(name)
        sheet.append(columns)
        sheet.append(["v"] * len(columns))
    buffer = io.BytesIO()
    workbook.save(buffer)
    workbook.close()
    data = buffer.getvalue()

    class Storage:
        def read(self, key):
            assert key == storage_key
            return data

    monkeypatch.setattr(sfm, "get_storage_backend", Storage)
    return job


def _infer_and_reload(session, job):
    job_id = job.id
    sfm.infer_shipment_import_job_sync(session, job_id)
    session.expunge_all()
    return session.get(ImportJob, job_id)


@pytest.mark.parametrize("selected", [["A", "B"], []])
def test_empty_scope_persists_no_headers_mapping_or_samples(session, monkeypatch, selected):
    job = _job(
        session, monkeypatch, {"A": ["Item", "Bill To", "Qty"], "B": ["Model Name"]}, selected
    )
    job = _infer_and_reload(session, job)
    state = sfm.shipment_mapping_state_dict(job)
    assert state["file_headers"] == []
    assert state["field_mapping"] == {}
    assert state["column_samples"] == {}
    assert state["mapping_valid"] is False
    assert job.staged_metadata["shipment_mapping_auto"] is False
    assert all(not sheet["in_scope"] for sheet in job.inferred_schema["sheets"])
    reason = sfm.SKIP_UNRECOGNISED_LAYOUT if selected else sfm.SKIP_NOT_SELECTED
    assert state["skipped_sheets"] == [
        {"sheet": "A", "reason": reason},
        {"sheet": "B", "reason": reason},
    ]


def test_mixed_scope_persists_only_operational_headers_and_samples(session, monkeypatch):
    job = _job(
        session, monkeypatch,
        {"Notes": ["Comment"], "Data": SHIPPED_COLS, "Cover": ["Title"]},
        ["Notes", "Data"],
    )
    job = _infer_and_reload(session, job)
    state = sfm.shipment_mapping_state_dict(job)
    assert state["file_headers"] == SHIPPED_COLS
    assert set(state["column_samples"]) == set(SHIPPED_COLS)
    assert state["mapping_valid"] is True
    assert state["skipped_sheets"] == [
        {"sheet": "Cover", "reason": sfm.SKIP_NOT_SELECTED},
        {"sheet": "Notes", "reason": sfm.SKIP_UNRECOGNISED_LAYOUT},
    ]


def test_reselection_persists_cleared_mapping_and_samples(session, monkeypatch):
    job = _job(
        session, monkeypatch, {"Data": SHIPPED_COLS, "Notes": ["Comment"]}, ["Data"]
    )
    job = _infer_and_reload(session, job)
    assert sfm.shipment_mapping_state_dict(job)["mapping_valid"] is True
    job.staged_metadata = {**job.staged_metadata, "selected_sheets": ["Notes"]}
    session.flush()
    job = _infer_and_reload(session, job)
    state = sfm.shipment_mapping_state_dict(job)
    assert state["file_headers"] == []
    assert state["field_mapping"] == {}
    assert state["column_samples"] == {}
    assert state["mapping_valid"] is False
    assert state["skipped_sheets"] == [
        {"sheet": "Data", "reason": sfm.SKIP_NOT_SELECTED},
        {"sheet": "Notes", "reason": sfm.SKIP_UNRECOGNISED_LAYOUT},
    ]


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="BACKLOG-046 PARTIAL-DEFERRED: shared detector needs an approved exception-sheet policy",
)
def test_selected_summary_with_operational_headers_must_be_ignored(session, monkeypatch):
    job = _job(session, monkeypatch, {"Summary": SHIPPED_COLS}, ["Summary"])
    job = _infer_and_reload(session, job)
    assert job.inferred_schema["sheets"][0]["in_scope"] is False
    assert job.file_headers == []
