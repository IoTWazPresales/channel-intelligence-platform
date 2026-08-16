"""Log a git SHA + parser mtime so stale Celery workers are visible (BACKLOG-111)."""

from __future__ import annotations

import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
_PARSER = (
    _REPO_ROOT
    / "apps"
    / "api"
    / "app"
    / "services"
    / "commercial_planner"
    / "lineup_case_parser.py"
)


def describe_worker_code_pin() -> str:
    sha = "unknown"
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=_REPO_ROOT,
            text=True,
            timeout=5,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        pass
    mtime = f"{_PARSER.stat().st_mtime:.0f}" if _PARSER.is_file() else "missing"
    return f"celery worker code pin sha={sha} lineup_case_parser_mtime={mtime}"
