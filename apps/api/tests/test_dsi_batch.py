"""DSI unified multi-file batch grouping and job creation."""

from __future__ import annotations

import io

import pandas as pd
import pytest

from app.services.imports.dsi_batch import (
    batch_groups_preview_to_dict,
    normalized_header_signature,
    propose_dsi_batch_groups,
)
from app.services.imports.dsi_workbook import (
    DSI_FILE_SHEET_SEP,
    build_combined_dsi_dataframe,
    build_dsi_workbook_structure,
    make_dsi_file_sheet_key,
    parse_dsi_mapping_key,
)


def test_same_layout_files_share_signature() -> None:
    a = pd.DataFrame({"Dist": ["D1"], "SKU": ["P1"], "Qty": [1], "Date": ["2024-01-01"]})
    b = pd.DataFrame({"Dist": ["D1"], "SKU": ["P2"], "Qty": [2], "Date": ["2024-01-08"]})
    bio_a = io.BytesIO()
    bio_b = io.BytesIO()
    a.to_csv(bio_a, index=False)
    b.to_csv(bio_b, index=False)
    sig_a, _, _, unm_a = normalized_header_signature("a.csv", bio_a.getvalue())
    sig_b, _, _, unm_b = normalized_header_signature("b.csv", bio_b.getvalue())
    assert not unm_a and not unm_b
    assert sig_a == sig_b


def test_divergent_layouts_split_groups() -> None:
    sell = pd.DataFrame({"Dist": ["D1"], "SKU": ["P1"], "Qty": [1], "Date": ["2024-01-01"]})
    soh = pd.DataFrame({"Dist": ["D1"], "SKU": ["P1"], "SOH": [10], "Snap": ["2024-01-31"]})
    bio_s = io.BytesIO()
    bio_h = io.BytesIO()
    sell.to_csv(bio_s, index=False)
    soh.to_csv(bio_h, index=False)
    groups = propose_dsi_batch_groups(
        [
            ("sell.csv", bio_s.getvalue()),
            ("soh.csv", bio_h.getvalue()),
        ]
    )
    assert len(groups) == 2
    preview = batch_groups_preview_to_dict(groups)
    assert len(preview) == 2


def test_file_sheet_mapping_key_roundtrip() -> None:
    key = make_dsi_file_sheet_key("week1.xlsx", "Sellout")
    file_part, sheet_part = parse_dsi_mapping_key(key)
    assert file_part == "week1.xlsx"
    assert sheet_part == "Sellout"
    assert DSI_FILE_SHEET_SEP in key


def test_cross_file_overlap_flags_shared_grain() -> None:
    import pandas as pd
    from unittest.mock import MagicMock

    from app.services.imports.dsi_workbook import flag_dsi_cross_file_raw_overlaps

    df = pd.DataFrame(
        {
            "distributor_token": ["Makro", "Makro"],
            "product_identifier": ["SKU1", "SKU1"],
            "customer_dealer_token": ["C1", "C1"],
            "transaction_date": ["2026-07-01", "2026-07-01"],
            "invoice_no": ["", ""],
            "_dsi_source_file": ["week1.csv", "week2.csv"],
        }
    )
    job = MagicMock()
    job.id = 99
    job.staged_metadata = {}
    db = MagicMock()
    n = flag_dsi_cross_file_raw_overlaps(db, job, df)
    assert n >= 1
    assert job.staged_metadata["dsi_cross_file_overlap"]["overlap_grain_count"] == 1


def test_column_samples_in_workbook_structure() -> None:
    sell = pd.DataFrame({"Dist": ["D1"], "SKU": ["P1"], "Qty": [1], "Date": ["2024-01-01"], "Cust": ["C1"]})
    bio = io.BytesIO()
    sell.to_csv(bio, index=False)
    structure = build_dsi_workbook_structure("a.csv", bio.getvalue())
    assert structure["sheets"]
    assert "column_samples" in structure["sheets"][0]
    assert structure["sheets"][0]["column_samples"]
