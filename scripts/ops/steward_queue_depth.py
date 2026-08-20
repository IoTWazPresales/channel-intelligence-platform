#!/usr/bin/env python3
"""Launcher for the read-only steward + CPOR queue-depth script.

The implementation lives under apps/api/scripts/ops so it can import app.*.
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TARGET = REPO / "apps" / "api" / "scripts" / "ops" / "steward_queue_depth.py"
sys.path.insert(0, str(REPO / "apps" / "api"))
runpy.run_path(str(TARGET), run_name="__main__")
