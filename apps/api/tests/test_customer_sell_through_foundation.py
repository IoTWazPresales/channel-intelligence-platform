"""Customer sell-through Phase 0 foundation (mocked — no DB writes)."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.models.ingestion import ImportJob
from app.services.imports.customer_sell_through import (
    STRUCTURE_FLAT,
    STRUCTURE_MTD_DELTA,
    STRUCTURE_PIVOTED,
    STRUCTURE_WIDE_EXTRACT,
    _handle_flat,
    _handle_mtd_delta,
    _handle_pivoted,
    _handle_wide_extract,
    customer_report_config_defaults,
    customer_sellthrough_source_key,
    new_customer_sellthrough_staging_line,
    process_customer_sell_through,
)


def test_source_key_chain_level_uses_zero_in_key_null_location_fk() -> None:
    key = customer_sellthrough_source_key(
        customer_id=10,
        customer_location_id=None,
        product_id=20,
        period_start_date=date(2026, 5, 1),
    )
    assert key == "ct:10:0:20:2026-05-01"


def test_source_key_store_level_includes_location_id() -> None:
    key = customer_sellthrough_source_key(
        customer_id=10,
        customer_location_id=55,
        product_id=20,
        period_start_date=date(2026, 5, 1),
    )
    assert key == "ct:10:55:20:2026-05-01"


def test_staging_line_defaults_to_pending() -> None:
    line = new_customer_sellthrough_staging_line(
        import_job_id=1,
        source_row_number=3,
        raw_row_payload={"sku": "ABC"},
    )
    assert line.resolution_status == "pending"
    assert line.import_job_id == 1
    assert line.source_row_number == 3


def test_handle_flat_fails_without_raw_file_metadata() -> None:
    db = MagicMock()
    job = MagicMock()
    job.id = 1
    job.source = None
    job.file_name = "flat.xlsx"
    job.import_mode = "preview"
    job.staged_metadata = {"customer_id": 5}
    db.scalars.return_value.first.return_value = None
    errors = _handle_flat(db, job, pd.DataFrame(), {}, None)
    assert errors == 1
    assert job.stage == "failed"
    err = (job.staged_metadata or {}).get("customer_sellthrough_error")
    assert err.get("reason") == "parse_failed"


def test_handle_pivoted_not_implemented_message() -> None:
    with patch(
        "app.services.imports.customer_sell_through._run_structure_handler",
        side_effect=NotImplementedError("Parser not yet implemented for pivoted: Game / Makro"),
    ):
        with pytest.raises(NotImplementedError, match="pivoted") as exc:
            _handle_pivoted(MagicMock(), MagicMock(), pd.DataFrame(), {}, None)
    assert "Game" in str(exc.value)
    assert "Makro" in str(exc.value)


def test_handle_mtd_delta_not_implemented_message() -> None:
    with patch(
        "app.services.imports.customer_sell_through._run_structure_handler",
        side_effect=NotImplementedError("Parser not yet implemented for mtd_delta: FNB"),
    ):
        with pytest.raises(NotImplementedError, match="mtd_delta") as exc:
            _handle_mtd_delta(MagicMock(), MagicMock(), pd.DataFrame(), {}, None)
    assert "FNB" in str(exc.value)


def test_handle_wide_extract_not_implemented_message() -> None:
    with patch(
        "app.services.imports.customer_sell_through._run_structure_handler",
        side_effect=NotImplementedError(
            "Parser not yet implemented for wide_extract: Incredible Connections"
        ),
    ):
        with pytest.raises(NotImplementedError, match="wide_extract") as exc:
            _handle_wide_extract(MagicMock(), MagicMock(), pd.DataFrame(), {}, None)
    assert "Incredible Connections" in str(exc.value)


def test_process_catches_not_implemented_sets_metadata_and_does_not_raise() -> None:
    job = ImportJob(
        id=99,
        source_id=1,
        file_name="game.xlsx",
        template_slug="customer_sell_through",
        staged_metadata={"report_structure_type": STRUCTURE_PIVOTED},
    )
    with patch(
        "app.services.imports.customer_sell_through._handle_pivoted",
        side_effect=NotImplementedError("Parser not yet implemented for pivoted: Game retailer"),
    ):
        errors = process_customer_sell_through(MagicMock(), job, pd.DataFrame(), {})
    assert errors == 1
    assert job.stage == "failed"
    assert job.status == "completed_with_errors"
    meta = job.staged_metadata or {}
    err = meta.get("customer_sellthrough_error")
    assert isinstance(err, dict)
    assert err.get("reason") == "parser_not_implemented"
    assert err.get("structure_type") == STRUCTURE_PIVOTED
    assert "Game" in str(err.get("message"))


def test_customer_report_config_defaults() -> None:
    cfg = customer_report_config_defaults(customer_id=7)
    assert cfg.customer_id == 7
    assert cfg.reports_expected is False
    assert cfg.expected_cadence == "weekly"
    assert cfg.overdue_threshold_days == 10


def test_collect_cst_tokens_includes_sales_model_when_barcode_primary() -> None:
    from app.services.imports.customer_sell_through import collect_cst_product_lookup_tokens

    tokens = collect_cst_product_lookup_tokens(
        primary="4711636287296",
        raw_row_payload={
            "Barcode": "4711636287296",
            "Supplier Code": "E1504TA-N82B0W",
            "Tsin Title": "ASUS Vivobook",
        },
    )
    assert tokens[0] == "4711636287296"
    assert "E1504TA-N82B0W" in tokens


def test_resolve_sellthrough_falls_back_to_sales_model() -> None:
    from app.services.imports.customer_sell_through import resolve_product_id_for_sellthrough
    from app.services.imports.distributor_sales_inventory import ProductResolutionIndex
    from app.services.imports.product_resolution_standard import resolve_product_id_single_match

    idx = ProductResolutionIndex(
        sku_to_id={},
        part_number_to_ids={},
        sales_model_name_to_ids={"e1504ta-n82b0w": (2972,)},
        model_name_to_ids={},
        marketing_name_to_ids={},
        ean_to_ids={},
        upc_to_ids={},
        alias_value_to_ids={},
        steward_alias_by_key={},
        products_by_id={},
    )
    pid = resolve_product_id_for_sellthrough(
        idx,
        "4711636287296",
        raw_row_payload={"Barcode": "4711636287296", "Supplier Code": "E1504TA-N82B0W"},
    )
    assert pid == 2972
    assert resolve_product_id_single_match(idx, "4711636287296") is None


def test_resolve_sellthrough_works_without_barcode_column() -> None:
    from app.services.imports.customer_sell_through import resolve_product_id_for_sellthrough
    from app.services.imports.distributor_sales_inventory import ProductResolutionIndex

    idx = ProductResolutionIndex(
        sku_to_id={},
        part_number_to_ids={},
        sales_model_name_to_ids={"x1504vap-i716512bl1w": (99,)},
        model_name_to_ids={},
        marketing_name_to_ids={},
        ean_to_ids={},
        upc_to_ids={},
        alias_value_to_ids={},
        steward_alias_by_key={},
        products_by_id={},
    )
    pid = resolve_product_id_for_sellthrough(
        idx,
        "X1504VAP-I716512BL1W",
        raw_row_payload={"Supplier Code": "X1504VAP-I716512BL1W", "sales": 2},
    )
    assert pid == 99
