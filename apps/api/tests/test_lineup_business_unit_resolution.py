"""Unit tests for lineup business_unit derivation (Spec C Step A)."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text

from app.services.commercial_planner.lineup_business_unit_resolution import (
    LineupRowProductTokens,
    infer_business_unit_from_folder_path,
    infer_business_unit_from_sheet_code,
    resolve_lineup_business_unit,
    resolve_row_product_id,
)
from app.services.imports.distributor_sales_inventory import ProductResolutionIndex
from app.services.imports.product_resolution_standard import resolve_product_id_single_match


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


def _row(sku: str | None = None, part: str | None = None, model: str | None = None) -> LineupRowProductTokens:
    return LineupRowProductTokens(sku_raw=sku, part_number_raw=part, model_raw=model)


def test_product_tier_majority_bu_wins() -> None:
    idx = _idx(sku_to_id={"sku-a": 1, "sku-b": 2, "sku-c": 3})
    bu_map = {1: "NB", 2: "NB", 3: "NR"}
    rows = [_row("sku-a"), _row("sku-b"), _row("sku-c")]

    report = resolve_lineup_business_unit(
        rows=rows,
        product_index=idx,
        business_unit_by_product_id=bu_map,
    )

    assert report.business_unit == "NB"
    assert report.source_tier == "product"
    assert report.product_resolution_rate == 1.0
    assert "bu_multi_bu_in_sheet" in report.flags


def test_catalogue_miss_falls_through_to_shipment() -> None:
    idx = _idx()
    rows = [_row("unknown-sku")] * 4

    report = resolve_lineup_business_unit(
        rows=rows,
        product_index=idx,
        business_unit_by_product_id={},
        shipment_business_units=["NR", "NR", "Gaming"],
        sheet_name="Sheet1",
    )

    assert report.business_unit == "NR"
    assert report.source_tier == "shipment"
    assert report.product_resolution_rate == 0.0
    assert "bu_likely_not_lineup" in report.flags


def test_sheet_fallback_when_product_and_shipment_miss() -> None:
    idx = _idx()
    rows = [_row("x")] * 3

    report = resolve_lineup_business_unit(
        rows=rows,
        product_index=idx,
        business_unit_by_product_id={},
        sheet_name="NR",
    )

    assert report.business_unit == "NR"
    assert report.source_tier == "sheet"


def test_folder_fallback() -> None:
    report = resolve_lineup_business_unit(
        rows=[],
        product_index=_idx(),
        business_unit_by_product_id={},
        folder_path=r"NB\2025\Q1\1. ACZA Q1 2025 Consumer Lineup.xlsx",
    )

    assert report.business_unit == "NB"
    assert report.source_tier == "folder"


def test_label_vs_product_mismatch_flag() -> None:
    idx = _idx(sku_to_id={"a": 1, "b": 2, "c": 3, "d": 4})
    bu_map = {1: "NB", 2: "NB", 3: "NB", 4: "NB"}
    rows = [_row("a"), _row("b"), _row("c"), _row("d")]

    report = resolve_lineup_business_unit(
        rows=rows,
        product_index=idx,
        business_unit_by_product_id=bu_map,
        sheet_name="NR",
    )

    assert report.business_unit == "NB"
    assert report.source_tier == "product"
    assert "bu_label_product_mismatch" in report.flags
    assert report.label_bu == "NR"


def test_multi_bu_in_one_sheet_flag() -> None:
    idx = _idx(sku_to_id={"a": 1, "b": 2})
    bu_map = {1: "NB", 2: "NR"}
    rows = [_row("a"), _row("b")]

    report = resolve_lineup_business_unit(
        rows=rows,
        product_index=idx,
        business_unit_by_product_id=bu_map,
    )

    assert "bu_multi_bu_in_sheet" in report.flags
    assert report.business_unit in ("NB", "NR")


def test_likely_not_lineup_near_zero_resolution() -> None:
    idx = _idx(sku_to_id={"only": 1})
    bu_map = {1: "NB"}
    rows = [_row("only")] + [_row(f"missing-{i}") for i in range(40)]

    report = resolve_lineup_business_unit(
        rows=rows,
        product_index=idx,
        business_unit_by_product_id=bu_map,
        sheet_name="PF",
    )

    assert "bu_likely_not_lineup" in report.flags
    assert report.product_resolution_rate is not None
    assert report.product_resolution_rate < 0.05


def test_unresolved_sku_never_raises() -> None:
    idx = _idx()
    rows = [_row("totally-unknown")] * 5

    report = resolve_lineup_business_unit(
        rows=rows,
        product_index=idx,
        business_unit_by_product_id={},
    )

    assert report.business_unit is None
    assert report.source_tier is None
    assert isinstance(report.flags, list)


def test_manual_tier_wins_over_all() -> None:
    idx = _idx(sku_to_id={"a": 1})
    report = resolve_lineup_business_unit(
        rows=[_row("a")],
        product_index=idx,
        business_unit_by_product_id={1: "NB"},
        manual_business_unit="NV",
    )
    assert report.business_unit == "NV"
    assert report.source_tier == "manual"


def test_resolve_row_product_id_uses_shared_tiers() -> None:
    idx = _idx(
        sku_to_id={},
        part_number_to_ids={"part-x": (9,)},
        sales_model_name_to_ids={"model-y": (10, 11)},
    )
    assert resolve_row_product_id(idx, _row(part="part-x")) == 9
    assert resolve_row_product_id(idx, _row(model="model-y")) is None
    assert resolve_product_id_single_match(idx, "model-y") is None


def test_sheet_and_folder_helpers() -> None:
    assert infer_business_unit_from_sheet_code("nb") == "NB"
    assert infer_business_unit_from_sheet_code("Sheet1") is None
    assert infer_business_unit_from_folder_path(r"NR\2025\Q2\file.xlsx") == "NR"


def _alembic_script_head() -> str:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    heads = set(ScriptDirectory.from_config(Config("alembic.ini")).get_heads())
    assert len(heads) == 1, f"expected single alembic head, got {sorted(heads)}"
    return next(iter(heads))


def test_migration_0064_column_on_disposable_db() -> None:
    """Smoke: business_unit column exists after upgrade on disposable clone — never cip."""
    from sqlalchemy import create_engine, text

    smoke_url = os.environ.get(
        "CIP_SMOKE_DATABASE_URL_SYNC",
        "postgresql+psycopg://cip:cip@127.0.0.1:5432/cip_alembic_smoke",
    )
    if "cip_alembic_smoke" not in smoke_url and os.environ.get("ALLOW_TESTS_ON_DEV_DB") != "1":
        pytest.skip("Set CIP_SMOKE_DATABASE_URL_SYNC to a disposable DB for migration smoke.")

    expected_tip = _alembic_script_head()
    with create_engine(smoke_url).connect() as conn:
        current = conn.execute(text("SELECT current_database()")).scalar_one()
        assert current != "cip", "Refusing migration smoke against cip"
        row = conn.execute(
            text(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'commercial_lineup_case' AND column_name = 'business_unit'
                """
            )
        ).first()
        rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
        assert rev == expected_tip, f"expected tip {expected_tip} on smoke DB, got {rev}"
        assert row is not None, "business_unit column missing after tip migrate on smoke DB"
