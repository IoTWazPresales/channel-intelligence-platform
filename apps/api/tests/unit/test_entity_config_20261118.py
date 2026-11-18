"""Tenant data comes from configuration, not code (alignment D9). No database."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.api.v1.endpoints import cst_steward
from app.core.config import get_settings
from app.services.commercial_planner.lineup_backfill_archive_config import (
    archive_config_for_root,
    parse_archive_relative_path,
)
from app.services.cpor.payment_evidence import overlay_read
from fastapi import HTTPException


def _clear_settings_cache():
    clear = getattr(get_settings, "cache_clear", None)
    if clear:
        clear()


def test_derive_eras_refuses_without_configured_workbook(monkeypatch) -> None:
    monkeypatch.delenv("CIP_SCM_ARTICLES_WORKBOOK_PATH", raising=False)
    _clear_settings_cache()
    try:
        with pytest.raises(HTTPException) as err:
            cst_steward.derive_eras_from_shipping(x_user_id=None)
        assert err.value.status_code == 400
        assert "CIP_SCM_ARTICLES_WORKBOOK_PATH" in str(err.value.detail)
    finally:
        _clear_settings_cache()


def test_derive_eras_reports_missing_configured_file(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CIP_SCM_ARTICLES_WORKBOOK_PATH", str(tmp_path / "absent.xlsx"))
    _clear_settings_cache()
    try:
        with pytest.raises(HTTPException) as err:
            cst_steward.derive_eras_from_shipping(x_user_id=None)
        assert err.value.status_code == 400
        assert "not found" in str(err.value.detail)
    finally:
        _clear_settings_cache()


def test_archive_config_needs_a_root(tmp_path) -> None:
    with pytest.raises(ValueError):
        archive_config_for_root("")
    cfg = archive_config_for_root(tmp_path)
    assert cfg.archive_roots == [Path(tmp_path)]


@pytest.mark.parametrize("short", ["25Q3", "27Q1"])
def test_short_quarter_folders_are_not_tied_to_one_year(short) -> None:
    meta = parse_archive_relative_path(
        Path(f"NB/{short}/lineup.xlsx"), tenant_bu_codes=frozenset({"NB"})
    )
    assert meta["quarter"] == f"Q{short[-1]}"


def test_payment_overlay_note_has_no_fixed_amounts() -> None:
    src = Path(overlay_read.__file__).read_text(encoding="utf-8")
    assert "R6.0m" not in src
    assert "R0 paid" not in src
