"""Unit tests for bulk lineup backfill preview engine (no DB writes)."""

from __future__ import annotations

import io

import pandas as pd
import pytest

from app.services.commercial_planner.lineup_bulk_backfill_preview import (
    CaseProposal,
    aggregate_catalogue_miss_worklist,
    build_case_proposals_for_file,
    detect_supersession_collisions,
    existing_case_sheet_matches_proposal,
)
from app.services.commercial_planner.lineup_bulk_backfill_preview import BulkFileInput
from app.services.imports.distributor_sales_inventory import ProductResolutionIndex


def _idx(**kwargs) -> ProductResolutionIndex:
    base = dict(
        sku_to_id={},
        part_number_to_ids={},
        sales_model_name_to_ids={},
        model_name_to_ids={},
        marketing_name_to_ids={},
        ean_to_ids={},
        upc_to_ids={},
        alias_value_to_ids={},
        steward_alias_by_key={},
        products_by_id={},
    )
    base.update(kwargs)
    return ProductResolutionIndex(**base)


def _minimal_xlsx(*, sheets: dict[str, list[list]]) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for name, rows in sheets.items():
            pd.DataFrame(rows).to_excel(writer, sheet_name=name, index=False, header=False)
    return buf.getvalue()


def test_multi_bu_sheet_fan_out_proposes_split_groups():
    """Two product BUs on one sheet → multiple case proposals after fan-out."""
    xlsx = _minimal_xlsx(
        sheets={
            "NB": [
                ["SKU", "Qty", "Customer"],
                ["sku-nb", "10", "Amazon"],
                ["sku-nr", "5", "Amazon"],
            ],
        }
    )
    idx = _idx(sku_to_id={"sku-nb": 1, "sku-nr": 2})
    bu_map = {1: "NB", 2: "NR"}
    proposals, misses, _ = build_case_proposals_for_file(
        "f0",
        BulkFileInput(
            filename="test.xlsx",
            file_bytes=xlsx,
            folder_path=r"NB\2026\Q1",
        ),
        product_index=idx,
        business_unit_by_product_id=bu_map,
        customer_map={},
    )
    ready = [p for p in proposals if p.status == "ready"]
    assert len(ready) >= 2, [p.to_dict() for p in proposals]
    bus = {p.business_unit for p in ready}
    assert "NB" in bus and "NR" in bus
    row_counts = {p.business_unit: p.row_count for p in ready}
    assert row_counts.get("NB") == 1 and row_counts.get("NR") == 1


def test_likely_not_lineup_needs_attention():
    rows = [["SKU", "Qty", "Customer"]]
    rows.append(["only-one", "1", "Amazon"])
    rows.extend([["missing-token", "1", "Amazon"] for _ in range(40)])
    xlsx = _minimal_xlsx(sheets={"NB": rows})
    proposals, _, _ = build_case_proposals_for_file(
        "f0",
        BulkFileInput(filename="lineup.xlsx", file_bytes=xlsx, folder_path=r"NB\2026\Q1"),
        product_index=_idx(sku_to_id={"only-one": 1}),
        business_unit_by_product_id={1: "NB"},
        customer_map={},
    )
    assert proposals
    assert any(
        "bu_likely_not_lineup" in p.attention_reasons or "bu_likely_not_lineup" in p.flags for p in proposals
    )


def test_folder_q1_title_1h_fan_out_two_quarters_with_allocation():
    xlsx = _minimal_xlsx(
        sheets={
            "NB": [
                ["2026 1H NEW PLAN", "", ""],
                ["SKU", "Qty", "Customer"],
                ["sku-nb", "11", "Amazon"],
            ],
        }
    )
    proposals, _, _ = build_case_proposals_for_file(
        "f0",
        BulkFileInput(filename="lineup.xlsx", file_bytes=xlsx, folder_path=r"NB\2026\26Q1"),
        product_index=_idx(sku_to_id={"sku-nb": 1}),
        business_unit_by_product_id={1: "NB"},
        customer_map={},
    )
    ready = [p for p in proposals if p.status == "ready"]
    periods = {p.period_label for p in ready}
    assert "2026 Q1" in periods and "2026 Q2" in periods
    assert any("period_scope=1h_split" in (p.period_flags or []) for p in ready)
    with_alloc = [p for p in ready if p.allocation_summary]
    assert with_alloc
    assert with_alloc[0].allocation_summary["sum_invariant"] is True
    assert with_alloc[0].allocation_summary["q1_allocated_units"] == 6.0


def test_collision_detection_latest_wins_member():
    proposals = [
        CaseProposal(
            proposal_key="a",
            file_key="f0",
            filename="1_older.xlsx",
            folder_path=None,
            sheet_name="NB",
            period_label="2026 Q1",
            period_start="2026-01-01",
            period_source_tier="filename",
            period_flags=[],
            business_unit="NB",
            bu_report={},
            customer_token="Amazon",
            customer_id=1,
            row_count=10,
            resolved_product_count=10,
            unresolved_product_count=0,
            status="ready",
            supersession_group_key="2026-01-01|1|NB",
        ),
        CaseProposal(
            proposal_key="b",
            file_key="f1",
            filename="2_newer.xlsx",
            folder_path=None,
            sheet_name="NB",
            period_label="2026 Q1",
            period_start="2026-01-01",
            period_source_tier="filename",
            period_flags=[],
            business_unit="NB",
            bu_report={},
            customer_token="Amazon",
            customer_id=1,
            row_count=12,
            resolved_product_count=12,
            unresolved_product_count=0,
            status="ready",
            supersession_group_key="2026-01-01|1|NB",
        ),
    ]
    collisions = detect_supersession_collisions(proposals)
    assert len(collisions) == 1
    assert collisions[0]["winner_proposal_key"] == "b"


def test_catalogue_miss_worklist_aggregates():
    entries = [
        {"token": "MISS-1", "field": "sku_raw", "filename": "a.xlsx", "sheet_name": "NB"},
        {"token": "MISS-1", "field": "sku_raw", "filename": "b.xlsx", "sheet_name": "NR"},
    ]
    wl = aggregate_catalogue_miss_worklist(entries)
    assert len(wl) == 1
    assert wl[0]["reference_count"] == 2


def test_out_of_catalogue_still_parses_ready_with_misses():
    xlsx = _minimal_xlsx(
        sheets={
            "NB": [
                ["SKU", "Qty", "Customer"],
                ["known-sku", "10", "Amazon"],
                ["unknown-sku", "5", "Amazon"],
            ],
        }
    )
    proposals, misses, _ = build_case_proposals_for_file(
        "f0",
        BulkFileInput(filename="mix.xlsx", file_bytes=xlsx, folder_path=r"NB\2026\Q1"),
        product_index=_idx(sku_to_id={"known-sku": 1}),
        business_unit_by_product_id={1: "NB"},
        customer_map={},
    )
    assert any(p.status == "ready" for p in proposals)
    assert len(misses) >= 1
    assert any(m["token"] == "unknown-sku" for m in misses)


def test_d034_multi_bu_native_slice_source_rows_with_parser_ctx():
    """D-034: multi-BU split emits native parser#2 source_row_number — no aligner."""
    xlsx = _minimal_xlsx(
        sheets={
            "NR": [
                ["SKU", "Qty", "Customer"],
                ["sku-nb", "10", "Amazon"],
                ["sku-nr", "5", "Amazon"],
            ],
        }
    )
    idx = _idx(sku_to_id={"sku-nb": 1, "sku-nr": 2})
    bu_map = {1: "NB", 2: "NR"}
    parser_ctx = {
        "product_map": {},
        "customer_map": {},
        "distributor_map": {},
        "customer_alias_map": {},
        "customers_by_id": {},
    }
    proposals, _, _ = build_case_proposals_for_file(
        "f0",
        BulkFileInput(filename="nr.xlsx", file_bytes=xlsx, folder_path=r"NR\2026\26Q3"),
        product_index=idx,
        business_unit_by_product_id=bu_map,
        customer_map={},
        parser_ctx=parser_ctx,
    )
    ready = [p for p in proposals if p.status == "ready"]
    assert len(ready) >= 2
    by_bu = {p.business_unit: p for p in ready}
    assert by_bu["NB"].row_count == 1 and by_bu["NR"].row_count == 1
    assert by_bu["NB"].slice_source_rows is not None
    assert by_bu["NR"].slice_source_rows is not None
    assert set(by_bu["NB"].slice_source_rows) | set(by_bu["NR"].slice_source_rows) == {1, 2}
    assert all("slice_row_mapping_failed" not in (p.attention_reasons or []) for p in proposals)


def test_sheet1_subset_of_primary_sheet_excluded():
    """Warren Unit3: Sheet1 content ⊆ NR → excluded (no double-count)."""
    xlsx = _minimal_xlsx(
        sheets={
            "NR": [
                ["SKU", "Qty", "Customer"],
                ["sku-a", "10", "Amazon"],
                ["sku-b", "5", "Amazon"],
            ],
            "Sheet1": [
                ["SKU", "Qty", "Customer"],
                ["sku-a", "10", "Amazon"],
            ],
        }
    )
    idx = _idx(sku_to_id={"sku-a": 1, "sku-b": 2})
    parser_ctx = {
        "product_map": {},
        "customer_map": {},
        "distributor_map": {},
        "customer_alias_map": {},
        "customers_by_id": {},
    }
    proposals, _, _ = build_case_proposals_for_file(
        "f0",
        BulkFileInput(filename="nr.xlsx", file_bytes=xlsx, folder_path=r"NR\2026\26Q3"),
        product_index=idx,
        business_unit_by_product_id={1: "NR", 2: "NR"},
        customer_map={},
        parser_ctx=parser_ctx,
    )
    sheet1 = [p for p in proposals if p.sheet_name == "Sheet1"]
    assert sheet1
    assert all(p.status == "excluded" for p in sheet1)
    assert any("sheet_content_subset_of:NR" in (p.attention_reasons or []) for p in sheet1)
    nr = [p for p in proposals if p.sheet_name == "NR" and p.status == "ready"]
    assert nr
    assert sum(p.row_count for p in nr) == 2


def test_null_notes_wildcard_matches_sheet1_and_nb():
    """BACKLOG-104: notes=NULL must not skip collisions against Sheet1/NB proposals."""
    assert existing_case_sheet_matches_proposal(None, "Sheet1") is True
    assert existing_case_sheet_matches_proposal(None, "NB") is True
    assert existing_case_sheet_matches_proposal("", "Sheet1") is True
    assert existing_case_sheet_matches_proposal("unrelated notes", "Sheet1") is True
    assert existing_case_sheet_matches_proposal("sheet=NB; period=2026Q1", "NB") is True
    assert existing_case_sheet_matches_proposal("sheet=NB; period=2026Q1", "Sheet1") is False
