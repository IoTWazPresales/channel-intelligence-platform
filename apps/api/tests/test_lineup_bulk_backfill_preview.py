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
