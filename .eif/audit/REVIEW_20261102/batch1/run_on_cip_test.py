"""Run a command in apps/api with DATABASE_URL / DATABASE_URL_SYNC pointed at cip_test (same host and role as .env).

Usage (from the repo root):  python .eif/audit/REVIEW_20261102/batch1/run_on_cip_test.py -m pytest -q tests/test_x.py
The arguments go to apps/api/.venv python, run in apps/api. The URL is never printed.
The target database name is forced to exactly cip_test.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

API = Path(__file__).resolve().parents[4] / "apps" / "api"
PY = API / ".venv" / "Scripts" / "python.exe"

env = dict(os.environ)
probe = subprocess.run(
    [str(PY), "-c", "from app.core.config import get_settings as g; s=g(); print(s.database_url); print(s.database_url_sync)"],
    cwd=API, capture_output=True, text=True, env=env,
)
if probe.returncode != 0:
    sys.exit("could not read settings: " + probe.stderr[-300:])
url, url_sync = probe.stdout.strip().splitlines()[-2:]


def swap(u: str) -> str:
    head, _, _ = u.rpartition("/")
    return head + "/cip_test"


env["DATABASE_URL"] = swap(url)
env["DATABASE_URL_SYNC"] = swap(url_sync)
assert env["DATABASE_URL_SYNC"].endswith("/cip_test")
sys.exit(subprocess.run([str(PY), *sys.argv[1:]], cwd=API, env=env).returncode)
