"""BACKLOG-046: mapping headers come only from in-scope sheets; skipped sheets carry a reason."""

from __future__ import annotations

import pandas as pd
import pytest
from app.services.imports.shipment_evidence_report_detect import (
    LINE_OPEN_ORDER,
    LINE_SHIPPED,
    REPORT_ACZA_BOM,
    REPORT_UNKNOWN,
    REPORT_XXOMRPT0025,
    detect_report_type,
)
from app.services.imports.shipment_field_mapping import (
    SKIP_NOT_SELECTED,
    SKIP_UNRECOGNISED_LAYOUT,
    _union_frame_headers,
    skipped_sheets,
)

SHIPPED_COLS = ["Operating Unit", "Delivery No", "Invoice Line", "Qty"]


def _frame(name: str, cols: list[str]):
    df = pd.DataFrame([[1] * len(cols)], columns=cols)
    rt, ls = detect_report_type({c.lower() for c in cols}, sheet_name=name, file_name="x.xlsx")
    return (name, df, rt, ls)


def test_detector_fixture_shapes():
    assert _frame("Data", SHIPPED_COLS)[2:] == (REPORT_XXOMRPT0025, LINE_SHIPPED)
    assert _frame("Notes", ["Comment", "Owner"])[2:] == (REPORT_UNKNOWN, LINE_OPEN_ORDER)


def test_union_leaves_out_an_unrecognised_sheet():
    frames = [_frame("Data", SHIPPED_COLS), _frame("Notes", ["Comment", "Owner"])]
    assert _union_frame_headers(frames) == SHIPPED_COLS


def test_union_is_empty_when_none_is_recognised():
    frames = [_frame("A", ["One", "Two"]), _frame("B", ["Two", "Three"])]
    assert _union_frame_headers(frames) == []
    assert _union_frame_headers([]) == []


def test_union_dedupes_across_in_scope_sheets_in_order():
    frames = [_frame("Data", SHIPPED_COLS), _frame("Data 2", [*SHIPPED_COLS, "Extra"])]
    assert _union_frame_headers(frames) == [*SHIPPED_COLS, "Extra"]


def test_skipped_sheets_lists_unselected_then_unrecognised():
    frames = [_frame("Data", SHIPPED_COLS), _frame("Notes", ["Comment"])]
    out = skipped_sheets(frames, ["Cover", "Data", "Notes", "Archive"])
    assert out == [
        {"sheet": "Cover", "reason": SKIP_NOT_SELECTED},
        {"sheet": "Archive", "reason": SKIP_NOT_SELECTED},
        {"sheet": "Notes", "reason": SKIP_UNRECOGNISED_LAYOUT},
    ]


def test_skipped_sheets_reports_every_unknown_even_without_a_recognised_sheet():
    frames = [_frame("A", ["One"]), _frame("B", ["Two"])]
    assert skipped_sheets(frames, ["A", "B", "Cover"]) == [
        {"sheet": "Cover", "reason": SKIP_NOT_SELECTED},
        {"sheet": "A", "reason": SKIP_UNRECOGNISED_LAYOUT},
        {"sheet": "B", "reason": SKIP_UNRECOGNISED_LAYOUT},
    ]
    assert skipped_sheets(frames, None) == [
        {"sheet": "A", "reason": SKIP_UNRECOGNISED_LAYOUT},
        {"sheet": "B", "reason": SKIP_UNRECOGNISED_LAYOUT},
    ]


def test_skipped_sheets_csv_and_no_available_list():
    frames = [(None, pd.DataFrame(columns=["One"]), REPORT_UNKNOWN, LINE_OPEN_ORDER)]
    assert skipped_sheets(frames, None) == []
    assert _union_frame_headers(frames) == []


class _FakeStorage:
    def __init__(self, data: bytes):
        self.data = data

    def read(self, _key):
        return self.data


class _FakeScalars:
    def __init__(self, row):
        self.row = row

    def first(self):
        return self.row


class _FakeSession:
    def __init__(self, job, raw):
        self.job, self.raw = job, raw

    def scalar(self, _stmt):
        return self.job

    def scalars(self, _stmt):
        return _FakeScalars(self.raw)

    def add(self, _obj):
        pass

    def commit(self):
        pass

    def refresh(self, _obj):
        pass


def _workbook(sheets: dict[str, list[str]]) -> bytes:
    import io

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        for name, cols in sheets.items():
            pd.DataFrame([["v"] * len(cols)], columns=cols).to_excel(
                xw, sheet_name=name, index=False
            )
    return buf.getvalue()


def _infer_workbook(monkeypatch, sheets, selected):
    from types import SimpleNamespace

    import app.services.imports.shipment_field_mapping as sfm

    data = _workbook(sheets)
    job = SimpleNamespace(
        id=1,
        template_slug="inbound_shipments",
        file_name="book.xlsx",
        source=None,
        staged_metadata={
            "available_sheets": list(sheets),
            "selected_sheets": selected,
            "sheet_selection_confirmed": True,
        },
        file_headers=None,
        field_mapping=None,
        inferred_schema=None,
        stage=None,
        status=None,
        error_summary=None,
    )
    monkeypatch.setattr(sfm, "get_storage_backend", lambda: _FakeStorage(data))
    return sfm.infer_shipment_import_job_sync(_FakeSession(job, SimpleNamespace(storage_key="k")), 1)


def test_infer_maps_only_in_scope_sheets_and_reports_skipped(monkeypatch):
    import app.services.imports.shipment_field_mapping as sfm

    out = _infer_workbook(
        monkeypatch,
        {"Data": SHIPPED_COLS, "Notes": ["Comment", "Owner"], "Cover": ["Title"]},
        ["Data", "Notes"],
    )
    assert out.file_headers == SHIPPED_COLS
    sheets = {s["sheet"]: s["in_scope"] for s in out.inferred_schema["sheets"]}
    assert sheets == {"Data": True, "Notes": False}
    state = sfm.shipment_mapping_state_dict(out)
    assert state["skipped_sheets"] == [
        {"sheet": "Cover", "reason": SKIP_NOT_SELECTED},
        {"sheet": "Notes", "reason": SKIP_UNRECOGNISED_LAYOUT},
    ]


@pytest.mark.parametrize("selected", [["A", "B"], []])
def test_infer_without_in_scope_sheets_has_no_mapping_or_samples(monkeypatch, selected):
    import app.services.imports.shipment_field_mapping as sfm

    out = _infer_workbook(
        monkeypatch, {"A": ["Item", "Bill To", "Qty"], "B": ["Model Name"]}, selected
    )
    state = sfm.shipment_mapping_state_dict(out)
    assert state["file_headers"] == []
    assert state["field_mapping"] == {}
    assert state["column_samples"] == {}
    assert state["mapping_valid"] is False
    assert out.staged_metadata["shipment_mapping_auto"] is False
    assert all(not sheet["in_scope"] for sheet in out.inferred_schema["sheets"])
    assert "tabular_column_infer" not in out.inferred_schema
    reason = SKIP_UNRECOGNISED_LAYOUT if selected else SKIP_NOT_SELECTED
    assert state["skipped_sheets"] == [
        {"sheet": "A", "reason": reason},
        {"sheet": "B", "reason": reason},
    ]


def test_samples_skip_an_unknown_sheet_before_the_operational_sheet(monkeypatch):
    import app.services.imports.shipment_field_mapping as sfm

    out = _infer_workbook(
        monkeypatch,
        {"Notes": ["Comment", "Owner"], "Data": SHIPPED_COLS},
        ["Notes", "Data"],
    )
    state = sfm.shipment_mapping_state_dict(out)
    assert state["file_headers"] == SHIPPED_COLS
    assert set(state["column_samples"]) == set(SHIPPED_COLS)


def test_reinfer_clears_previous_headers_mapping_and_samples(monkeypatch):
    from types import SimpleNamespace

    import app.services.imports.shipment_field_mapping as sfm

    out = _infer_workbook(
        monkeypatch, {"Data": SHIPPED_COLS, "Notes": ["Comment"]}, ["Data"]
    )
    assert out.field_mapping
    assert out.inferred_schema["column_samples"]
    out.staged_metadata["selected_sheets"] = ["Notes"]
    sfm.infer_shipment_import_job_sync(_FakeSession(out, SimpleNamespace(storage_key="k")), 1)
    state = sfm.shipment_mapping_state_dict(out)
    assert state["file_headers"] == []
    assert state["field_mapping"] == {}
    assert state["column_samples"] == {}
    assert state["mapping_valid"] is False
    assert state["skipped_sheets"] == [
        {"sheet": "Data", "reason": SKIP_NOT_SELECTED},
        {"sheet": "Notes", "reason": SKIP_UNRECOGNISED_LAYOUT},
    ]


def test_explicit_bom_selection_keeps_its_dedicated_report_type(monkeypatch):
    out = _infer_workbook(
        monkeypatch,
        {"BOM Not Ready": ["Order No.", "Sales Model Name", "Item", "Bill To"]},
        ["BOM Not Ready"],
    )
    assert out.inferred_schema["sheets"][0]["report_type"] == REPORT_ACZA_BOM
    assert out.inferred_schema["sheets"][0]["in_scope"] is True
    assert out.inferred_schema["skipped_sheets"] == []


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="BACKLOG-046 PARTIAL-DEFERRED: shared detector needs an approved exception-sheet policy",
)
@pytest.mark.parametrize("name", ["Summary", "Exceptions", "Index"])
@pytest.mark.parametrize("cols", [SHIPPED_COLS, ["Order No.", "Sales Model Name", "Item"]])
def test_exception_tabs_with_operational_headers_must_not_be_operational(name, cols):
    # Desired contract, deliberately outstanding; do not bless the inherited classification.
    assert _frame(name, cols)[2] == REPORT_UNKNOWN
