"""Per-file DSI inventory snapshot period stamps (Application Date banner)."""

from __future__ import annotations

from datetime import date

import pandas as pd

from app.services.imports.dsi_file_snapshot import (
    apply_file_snapshot_stamps_to_dataframe,
    file_snapshot_periods_all_confirmed,
    resolve_snapshot_period_token,
    sniff_banner_application_date_token_from_grid,
    snapshot_identity_satisfied,
)
from app.services.imports.dsi_mapping_workflow import dsi_mapping_gate_errors
from app.services.imports.parsers.customer_sell_through_period import classify_period_header


def test_classify_period_accepts_asus_nodash_week() -> None:
    kind, d, _ = classify_period_header("2026W26")
    assert kind == "iso_week"
    assert d == date.fromisocalendar(2026, 26, 1)
    assert d == date(2026, 6, 22)


def test_resolve_snapshot_period_token_monday() -> None:
    d, reason = resolve_snapshot_period_token("2026W26")
    assert reason == "banner_application_date"
    assert d == date(2026, 6, 22)


def test_sniff_banner_application_date() -> None:
    grid = pd.DataFrame(
        [
            ["ASUS Weekly Inventory Report", None],
            ["Company Name", "MUSTEK-ZA-C"],
            ["Application Date", "2026W26"],
            ["Method", "SYS"],
        ]
    )
    assert sniff_banner_application_date_token_from_grid(grid) == "2026W26"


def test_gate_inventory_needs_snapshot_stamp() -> None:
    mapping = {
        "Model": "product_identifier",
        "INVENTORY": "stock_on_hand",
    }
    errs = dsi_mapping_gate_errors(mapping, file_distributor_satisfied=True, file_snapshot_satisfied=False)
    assert any(e["code"] == "missing_snapshot_period_for_inventory_file" for e in errs)
    errs_ok = dsi_mapping_gate_errors(mapping, file_distributor_satisfied=True, file_snapshot_satisfied=True)
    assert not any(e["code"] == "missing_snapshot_period_for_inventory_file" for e in errs_ok)
    assert not any(e["code"] == "missing_column_mapping_date" for e in errs_ok)


def test_gate_inventory_allows_transaction_date_as_snapshot_fallback() -> None:
    mapping = {
        "Model": "product_identifier",
        "Date": "transaction_date",
        "INVENTORY": "stock_on_hand",
    }
    errs = dsi_mapping_gate_errors(mapping, file_distributor_satisfied=True, file_snapshot_satisfied=False)
    assert not any(e["code"] == "missing_snapshot_period_for_inventory_file" for e in errs)


def test_gate_sellout_still_needs_transaction_date() -> None:
    mapping = {
        "Model": "product_identifier",
        "Qty": "quantity_sold",
    }
    errs = dsi_mapping_gate_errors(mapping, file_distributor_satisfied=True, file_snapshot_satisfied=False)
    assert any(e["code"] == "missing_column_mapping_date" for e in errs)


def test_stamp_snapshot_rows_by_source_file() -> None:
    class _Job:
        staged_metadata = {
            "dsi_file_snapshot_periods": {
                "mustek.xls": {
                    "token": "2026W26",
                    "resolved_date": "2026-06-22",
                    "confirmed": True,
                    "reason": "banner_application_date",
                    "source": "banner",
                },
                "pinnacle.xlsx": {
                    "token": "2025W24",
                    "resolved_date": "2025-06-09",
                    "confirmed": True,
                    "reason": "banner_application_date",
                    "source": "banner",
                },
            },
            "dsi_batch_filenames": ["mustek.xls", "pinnacle.xlsx"],
        }
        field_mapping = {}
        file_name = None

    df = pd.DataFrame(
        {
            "_dsi_source_file": ["mustek.xls", "pinnacle.xlsx", "mustek.xls"],
            "stock_on_hand": [1, 2, 3],
        }
    )
    out = apply_file_snapshot_stamps_to_dataframe(_Job(), df)  # type: ignore[arg-type]
    assert out["snapshot_date"].tolist() == ["2026-06-22", "2025-06-09", "2026-06-22"]


def test_mixed_job_snapshot_all_confirmed_only_inventory_files() -> None:
    class _Job:
        staged_metadata = {
            "dsi_file_snapshot_periods": {
                "inv.xls": {
                    "token": "2026W26",
                    "resolved_date": "2026-06-22",
                    "confirmed": True,
                    "reason": "banner_application_date",
                    "source": "banner",
                },
                "sell.xlsx": {
                    "token": None,
                    "resolved_date": None,
                    "confirmed": False,
                    "reason": "missing",
                    "source": "banner",
                },
            },
            "dsi_batch_filenames": ["inv.xls", "sell.xlsx"],
        }
        field_mapping = {
            "inv.xls::__single__": {
                "Model": "product_identifier",
                "INVENTORY": "stock_on_hand",
            },
            "sell.xlsx::__single__": {
                "Model": "product_identifier",
                "Qty": "quantity_sold",
                "Date": "transaction_date",
            },
        }
        file_name = None

    job = _Job()
    assert file_snapshot_periods_all_confirmed(job)  # type: ignore[arg-type]
    assert snapshot_identity_satisfied(
        job,  # type: ignore[arg-type]
        job.field_mapping["inv.xls::__single__"],
        mapping_key="inv.xls::__single__",
    )
    # Sell-out sheet does not use snapshot stamp for date satisfaction
    assert (
        snapshot_identity_satisfied(
            job,  # type: ignore[arg-type]
            job.field_mapping["sell.xlsx::__single__"],
            mapping_key="sell.xlsx::__single__",
        )
        is False
    )
    errs = dsi_mapping_gate_errors(
        job.field_mapping["sell.xlsx::__single__"],
        file_distributor_satisfied=True,
        file_snapshot_satisfied=False,
    )
    assert not any(e["code"] == "missing_snapshot_period_for_inventory_file" for e in errs)
    assert not any(e["code"] == "missing_column_mapping_date" for e in errs)
