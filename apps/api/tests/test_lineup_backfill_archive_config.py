"""N-0040 (D-g): archive folder BU segments match the injected product-line codes."""

from __future__ import annotations

from pathlib import Path

from app.services.commercial_planner.lineup_backfill_archive_config import (
    BackfillArchiveConfig,
    iter_archive_lineup_files,
    parse_archive_relative_path,
)

_LINE_CODES = frozenset({"NB", "PF", "XB", "PT"})


def test_parse_uses_injected_codes() -> None:
    meta = parse_archive_relative_path(Path("PT/2025/Q1/lineup.xlsx"), tenant_bu_codes=_LINE_CODES)
    assert meta["business_unit"] == "PT"
    assert meta["folder_path"] == "PT\\2025\\Q1"


def test_segment_outside_codes_is_not_a_bu() -> None:
    meta = parse_archive_relative_path(Path("NX/2025/Q1/lineup.xlsx"), tenant_bu_codes=_LINE_CODES)
    assert meta["business_unit"] is None
    assert meta["folder_path"] == "2025\\Q1"


def test_config_has_no_builtin_codes_and_override_wins(tmp_path: Path) -> None:
    (tmp_path / "PT" / "2025" / "Q1").mkdir(parents=True)
    (tmp_path / "PT" / "2025" / "Q1" / "a.xlsx").write_bytes(b"x")

    config = BackfillArchiveConfig(archive_roots=[tmp_path])
    assert config.tenant_bu_codes is None
    assert config.to_dict()["tenant_bu_codes"] is None

    no_codes = list(iter_archive_lineup_files(config))
    assert no_codes[0]["archive_meta"]["business_unit"] is None

    from_catalogue = list(iter_archive_lineup_files(config, sellable_line_codes=_LINE_CODES))
    assert from_catalogue[0]["folder_path"] == "PT\\2025\\Q1"

    override = BackfillArchiveConfig(archive_roots=[tmp_path], tenant_bu_codes=frozenset({"NB"}))
    overridden = list(iter_archive_lineup_files(override, sellable_line_codes=_LINE_CODES))
    assert overridden[0]["archive_meta"]["business_unit"] is None
