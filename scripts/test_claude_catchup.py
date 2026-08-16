"""Unit tests for scripts/claude_catchup.py (no DB writes)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from claude_catchup import IMPORT_JOB_FIXTURE_FILENAME_RE  # noqa: E402


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
