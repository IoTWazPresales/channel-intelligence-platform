"""Unit tests for scripts/claude_catchup.py (no DB writes)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from claude_catchup import (  # noqa: E402
    IMPORT_JOB_FIXTURE_FILENAME_RE,
    collect_junit_artifacts,
)


@pytest.mark.parametrize(
    "name, match",
    [
        ("dsi", True),
        ("dsi.csv", True),
        ("dsi.xlsx", True),
        ("dsi_a.csv", True),
        ("dsi_1.xlsx", True),
        ("dsi_week32.xlsx", False),
        ("DSI_WEEK32.XLSX", False),
        ("dsi.foo.xlsx", False),
        ("weekly_dsi.xlsx", False),
        ("run1.xlsx", True),
        ("validate.xlsx", True),
        ("historical_lineup.xlsx", True),
        ("bulk_lineup_preview_session", True),
    ],
)
def test_fixture_filename_re_does_not_match_weekly_dsi(name: str, match: bool) -> None:
    assert bool(re.fullmatch(IMPORT_JOB_FIXTURE_FILENAME_RE, name, re.I)) is match


def test_collect_junit_reads_tmp_api_junit_despite_skip(tmp_path: Path) -> None:
    hidden = tmp_path / ".tmp"
    hidden.mkdir()
    xml = hidden / "api-junit.xml"
    xml.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<testsuite name="pytest" tests="2" failures="0" errors="0" skipped="1">
  <testcase classname="t" name="pass_one"/>
  <testcase classname="t" name="skip_one"><skipped message="x"/></testcase>
</testsuite>
""",
        encoding="utf-8",
    )
    found = collect_junit_artifacts(tmp_path, floor_ts=10**12)
    assert xml.resolve() in {p.resolve() for p in found}
