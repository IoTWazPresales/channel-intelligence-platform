"""N-0047 / BACKLOG-034: dim_product launch/retire windows (pure logic; no database)."""

from __future__ import annotations

import importlib.util
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.services.catalog.product_import_sync import _parse_date_val, _staging_tuple
from app.services.imports.product_master_workflow import pm_row_inverted_window

_REPAIR_PATH = Path(__file__).resolve().parents[1] / "scripts" / "ops" / "repair_n0047_dim_product_windows.py"
EPOCH = date(1970, 1, 1)


def _repair_module():
    spec = importlib.util.spec_from_file_location("repair_n0047", _REPAIR_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


# --- writer: Excel serials (671 rows on cip became 1970-01-01) ---------------------------------


@pytest.mark.parametrize(
    "raw, want",
    [
        (46041, date(2026, 1, 19)),
        (np.int64(45772), date(2025, 4, 25)),
        (45870.0, date(2025, 8, 1)),
        (45870.75, date(2025, 8, 1)),  # time-of-day fraction
        (datetime(2021, 7, 8, 0, 0), date(2021, 7, 8)),
        (pd.Timestamp("2019-10-31"), date(2019, 10, 31)),
        ("2025-08-01", date(2025, 8, 1)),
        (float("nan"), None),
        (None, None),
        (True, None),
        (0, None),
        (-5, None),
    ],
)
def test_parse_date_val_reads_excel_serials(raw, want):
    assert _parse_date_val(raw) == want


def test_serial_never_becomes_unix_epoch():
    assert _parse_date_val(46041) != EPOCH


def test_staging_tuple_carries_serial_dates():
    tup = _staging_tuple({"sku": "S", "name": "x", "launch_date": 46041, "end_of_life_date": 45772})
    assert tup is not None
    assert (tup[7], tup[9]) == (date(2026, 1, 19), date(2025, 4, 25))


# --- validate: inverted file window is a warning (FLAG, not BLOCK) ------------------------------


def test_inverted_window_flagged_from_file_row():
    row = pd.Series({"ttv_date": datetime(2026, 1, 19), "eop_date": datetime(2025, 12, 26)})
    assert pm_row_inverted_window(row, "ttv_date", "eop_date") == {
        "launch_date": "2026-01-19",
        "end_of_life_date": "2025-12-26",
    }


@pytest.mark.parametrize(
    "ld, eol",
    [
        (datetime(2025, 7, 16), datetime(2025, 12, 26)),
        (datetime(2025, 7, 16), datetime(2025, 7, 16)),
        (datetime(2025, 7, 16), None),
        (float("nan"), 45772),
    ],
)
def test_valid_or_open_window_not_flagged(ld, eol):
    row = pd.Series({"ttv_date": ld, "eop_date": eol})
    assert pm_row_inverted_window(row, "ttv_date", "eop_date") is None


def test_inverted_serial_window_flagged_and_unmapped_columns_ignored():
    row = pd.Series({"ttv_date": 46041, "eop_date": 45772})
    assert pm_row_inverted_window(row, "ttv_date", "eop_date") is not None
    assert pm_row_inverted_window(row, None, "eop_date") is None


# --- repair rule --------------------------------------------------------------------------------


def _row(ld, rd, sku="SKU1"):
    return {
        "id": 1,
        "sku": sku,
        "launch_date": ld,
        "retired_date": rd,
        "lifecycle_status": "Disabled",
        "product_line": "NB",
    }


def test_epoch_rederived_from_newest_file_serials():
    m = _repair_module()
    p = m.plan_row(_row(EPOCH, EPOCH), [(31, float("nan"), float("nan")), (88, 45854, 45870)])
    assert p["rule"] == "rederive_excel_serial"
    assert (p["launch_after"], p["retired_after"]) == (date(2025, 7, 16), date(2025, 8, 1))
    assert p["flag"] is None and p["source_job"] == 88
    assert m.is_write(p)


def test_epoch_rederived_inverted_is_written_and_flagged():
    m = _repair_module()
    p = m.plan_row(_row(EPOCH, EPOCH), [(88, 46041, 45772)])
    assert p["rule"] == "rederive_excel_serial"
    assert (p["launch_after"], p["retired_after"]) == (date(2026, 1, 19), date(2025, 4, 25))
    assert p["flag"] == "rederived_window_inverted_in_source"
    assert m.is_write(p)


def test_placeholder_without_serial_becomes_null_not_guessed():
    m = _repair_module()
    p = m.plan_row(_row(date(2024, 1, 1), EPOCH), [(88, datetime(2024, 1, 1), None)])
    assert p["rule"] == "null_placeholder"
    assert (p["launch_after"], p["retired_after"]) == (date(2024, 1, 1), None)
    p2 = m.plan_row(_row(EPOCH, EPOCH), [])
    assert (p2["rule"], p2["launch_after"], p2["retired_after"]) == ("null_placeholder", None, None)


def test_swap_only_with_file_evidence_of_transposition():
    m = _repair_module()
    ld, rd = date(2023, 11, 13), date(2023, 8, 7)
    hist = [
        (31, datetime(2023, 8, 7), datetime(2023, 11, 13)),
        (88, datetime(2023, 11, 13), datetime(2023, 8, 7)),
    ]
    p = m.plan_row(_row(ld, rd), hist)
    assert p["rule"] == "swap"
    assert (p["launch_after"], p["retired_after"]) == (rd, ld)


_INV = (datetime(2026, 1, 19), datetime(2025, 12, 26))


@pytest.mark.parametrize(
    "hist, reason",
    [
        ([(31, *_INV), (88, *_INV)], "same_in_every_pm_file"),
        ([(88, *_INV)], "single_pm_file"),
        ([(31, datetime(2025, 7, 16), _INV[1]), (88, *_INV)], "earlier_pm_file_valid_window"),
        ([(31, datetime(2025, 12, 27), datetime(2025, 12, 1)), (88, *_INV)], "earlier_pm_file_other_inverted"),
        ([], "no_pm_file_row"),
    ],
)
def test_other_inversions_flag_and_never_write(hist, reason):
    m = _repair_module()
    p = m.plan_row(_row(date(2026, 1, 19), date(2025, 12, 26)), hist)
    assert (p["rule"], p["flag"]) == ("flag", reason)
    assert (p["launch_after"], p["retired_after"]) == (date(2026, 1, 19), date(2025, 12, 26))
    assert not m.is_write(p)


@pytest.mark.parametrize(
    "ld, rd",
    [
        (date(2025, 7, 16), date(2025, 12, 26)),
        (date(2025, 7, 16), date(2025, 7, 16)),
        (date(2026, 8, 28), date(2099, 12, 31)),  # open-ended OEM placeholder: not inverted, untouched
        (None, None),
    ],
)
def test_valid_windows_untouched(ld, rd):
    assert _repair_module().plan_row(_row(ld, rd), []) is None


def test_repair_is_idempotent_on_its_own_output():
    m = _repair_module()
    hist = {"A": [(88, 45854, 45870)], "B": [(88, 46041, 45772)], "C": [(88, *_INV)]}
    rows = [_row(EPOCH, EPOCH, "A"), _row(EPOCH, EPOCH, "B"), _row(date(2026, 1, 19), date(2025, 12, 26), "C")]
    first = [p for p in m.plan_repair(rows, hist) if m.is_write(p)]
    assert [p["sku"] for p in first] == ["A", "B"]
    after = {p["sku"]: p for p in first}
    rows2 = [
        _row(after[r["sku"]]["launch_after"], after[r["sku"]]["retired_after"], r["sku"]) if r["sku"] in after else r
        for r in rows
    ]
    # B's re-derived serials come back from the fixed parser as the same (inverted) values: flag only.
    hist2 = {**hist, "B": [(88, 46041, 45772)]}
    assert [p for p in m.plan_repair(rows2, hist2) if m.is_write(p)] == []
    c = m.counts(rows2)
    assert (c["epoch_1970_both"], c["inverted_retired_lt_launch"]) == (0, 2)
