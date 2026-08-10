"""Unit tests for PO auto-link file / version display meta (BACKLOG-113)."""

from app.services.commercial_planner.lineup_po_auto_link import lineup_file_version_meta


def test_lineup_file_version_meta_prefix():
    out = lineup_file_version_meta("2. ACZA Q1 2026 NR Gaming Lineup.xlsx - Sales Team Copy.xlsx")
    assert out["version_prefix"] == "2"
    assert out["file_base"] == "ACZA Q1 2026 NR Gaming Lineup.xlsx - Sales Team Copy"
    assert out["file_name"] and out["file_name"].startswith("2.")


def test_lineup_file_version_meta_plain():
    out = lineup_file_version_meta("Q2 Gaming NR Lineup - Sales Team.xlsx")
    assert out["version_prefix"] is None
    assert out["file_base"] == "Q2 Gaming NR Lineup - Sales Team"
    assert out["file_name"] == "Q2 Gaming NR Lineup - Sales Team.xlsx"


def test_lineup_file_version_meta_empty():
    assert lineup_file_version_meta(None) == {
        "file_name": None,
        "file_base": None,
        "version_prefix": None,
    }
