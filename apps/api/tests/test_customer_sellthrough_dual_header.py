"""Game dual-header / header-score regression (synthetic; no DB)."""

from __future__ import annotations

import io

import pandas as pd

from app.services.imports.parsers.customer_sell_through_flat import (
    EXPECTED_COLUMNS_META_KEY,
    _build_alias_index,
    _detect_header_row,
    _merge_dual_header_labels,
    parse_flat_report,
)

EXPECTED = {
    "units_sold": {
        "aliases": ["units_sold", "sales", "units", "qty", "sales u ty"],
        "required": True,
    },
    "raw_product_token": {
        "aliases": ["article", "ean/upc", "barcode", "sku"],
        "required": True,
    },
    "raw_location_token": {"aliases": ["site", "site_code"], "required": False},
    "raw_article_token": {"aliases": ["article"], "required": False},
}


def _alias_index():
    fm = {
        "EAN/UPC": "raw_product_token",
        "Article": "raw_article_token",
        "Site": "raw_location_token",
        "Sales U TY": "units_sold",
        EXPECTED_COLUMNS_META_KEY: EXPECTED,
    }
    return _build_alias_index(fm, EXPECTED), fm


def test_header_score_prefers_dimension_row_over_repeated_measures() -> None:
    """Six Sales U TY cells must not beat Article+Site (Game 2026 failure mode)."""
    idx, _ = _alias_index()
    measure_row = [None] * 13 + ["Sales U TY"] * 6
    dim_row = (
        ["Department", None, "Brand", None, "Category", None, "Site", None, "Article", None]
        + ["EA"] * 6
    )
    from app.services.imports.parsers.customer_sell_through_flat import _score_header_row

    assert _score_header_row(dim_row, idx) > _score_header_row(measure_row, idx)


def test_game_2026_style_triple_header_surfaces_article_and_sales() -> None:
    """Fiscal Week / Sales U TY / EA+Article band → Article + bare Sales U TY on last week."""
    # Align period band over measure cols only (SAP: Fiscal Week sits above first week code).
    rows = [
        [None, None, None, None, "Fiscal Week", "022.2026", "023.2026", "027.2026"],
        [None, None, None, None, None, "Sales U TY", "Sales U TY", "Sales U TY"],
        ["Site", None, "Article", None, "EA", "EA", "EA", "EA"],
        ["G001", "GAME TEST", "850039776", "VIVOBOOK", None, "1", "2", "4"],
        ["G002", "GAME TWO", "850016148", "ZENBOOK", None, None, None, "1"],
    ]
    df = pd.DataFrame(rows)
    idx, fm = _alias_index()
    header_row = _detect_header_row(df, idx)
    assert header_row == 2
    headers = _merge_dual_header_labels(df, header_row)
    assert "Article" in headers
    assert "Site" in headers
    assert "Sales U TY" in headers
    assert headers.count("Sales U TY") == 1
    assert any(h.startswith("Sales U TY ") for h in headers)
    assert "Fiscal Week" not in headers

    bio = io.BytesIO()
    df.to_excel(bio, index=False, header=False)
    result = parse_flat_report(
        bio.getvalue(),
        "Asus Sales W27.xlsx",
        dict(fm),
        99,
        feed_profile={"dual_header_merge": True},
    )
    assert result.error is None, result.error
    assert len(result.rows) >= 1
    tokens = {r["raw_product_token"] for r in result.rows}
    assert "850039776" in tokens or "850016148" in tokens


def test_game_week33_style_dual_header_still_merges_zar_to_sales_r() -> None:
    rows = [
        [None] * 4 + ["Sales R TY", "Sales U TY"],
        ["EAN/UPC", "Article", "Site", None, "ZAR", None],
        ["4711081465669", "834487", "G013", "GAME", "100.0", "1"],
    ]
    df = pd.DataFrame(rows)
    idx, fm = _alias_index()
    header_row = _detect_header_row(df, idx)
    assert header_row == 1
    headers = _merge_dual_header_labels(df, header_row)
    assert "EAN/UPC" in headers
    assert "Sales R TY" in headers
    assert "Sales U TY" in headers
    assert "ZAR" not in headers

    bio = io.BytesIO()
    df.to_excel(bio, index=False, header=False)
    result = parse_flat_report(
        bio.getvalue(),
        "Asus Week 33.xlsx",
        dict(fm),
        100,
        feed_profile={"dual_header_merge": True},
    )
    assert result.error is None, result.error
    assert result.rows[0]["raw_product_token"] == "4711081465669"
    assert result.rows[0]["units_sold"] == 1.0
