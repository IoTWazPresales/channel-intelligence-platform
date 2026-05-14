"""Product Master dataframe hygiene: descriptor rows and null-like strings."""

import pandas as pd
import pytest

from app.services.imports.pm_dataframe_sanitize import (
    normalize_scalar_for_pm,
    scalar_to_clean_str,
    strip_leading_descriptor_rows,
)
from app.services.catalog.product_import_sync import _strip_optional
from app.services.imports.product_master_workflow import _row_payload_for_dim


def test_strip_leading_descriptor_row_with_humanized_labels() -> None:
    """Legend row: identity cells read like column titles, not SKU + product name."""
    df = pd.DataFrame(
        [
            {"Item ID": "Item ID", "Name": "Product Title", "UPC": "UPC Code"},
            {"Item ID": "90NB0F12", "Name": "Laptop 15", "UPC": "0123456789012"},
        ]
    )
    out, dropped = strip_leading_descriptor_rows(df, tech_col="Item ID", name_col="Name")
    assert dropped == [0]
    assert len(out) == 1


def test_strip_leading_descriptor_second_header_row() -> None:
    df = pd.DataFrame(
        [
            {
                "Item ID": "Item ID",
                "marketing_col": "marketing_name",
                "UPC": "UPC Code",
            },
            {
                "Item ID": "90NB0F12",
                "marketing_col": "Laptop 15",
                "UPC": "0123456789012",
            },
        ]
    )
    out, dropped = strip_leading_descriptor_rows(
        df, tech_col="Item ID", name_col="marketing_col"
    )
    assert dropped == [0]
    assert len(out) == 1
    assert out.iloc[0]["Item ID"] == "90NB0F12"
    assert out.iloc[0]["marketing_col"] == "Laptop 15"


def test_normalize_scalar_for_pm_string_nan() -> None:
    assert normalize_scalar_for_pm("nan") is None
    assert normalize_scalar_for_pm("NaT") is None
    assert normalize_scalar_for_pm(float("nan")) is None


def test_normalize_scalar_for_pm_unwraps_flag_value_pairs() -> None:
    assert normalize_scalar_for_pm((True, "  trimmed  ")) == "trimmed"
    assert normalize_scalar_for_pm((False, "still_value")) == "still_value"


def test_normalize_scalar_for_pm_unwraps_numpy_bool_flag() -> None:
    np = pytest.importorskip("numpy")
    assert normalize_scalar_for_pm((np.bool_(True), "sku-1")) == "sku-1"
    assert normalize_scalar_for_pm((np.bool_(False), "sku-2")) == "sku-2"


def test_scalar_to_clean_str_does_not_emit_nan_literal() -> None:
    assert scalar_to_clean_str("nan") is None
    assert scalar_to_clean_str(pd.NA) is None


def test_strip_optional_rejects_string_nan() -> None:
    assert _strip_optional("nan") is None
    assert _strip_optional("NaT") is None


def test_row_payload_skips_when_display_name_is_string_nan() -> None:
    fm = {"id": "technical_product_id", "title": "display_name"}
    row = pd.Series({"id": "X1", "title": "nan"})
    assert _row_payload_for_dim(row, fm) is None
