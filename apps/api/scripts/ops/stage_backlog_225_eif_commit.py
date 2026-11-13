#!/usr/bin/env python3
"""Stage BACKLOG-225 EIF control-plane commit in the current worktree."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[4]
    rels = [
        ".gitattributes",
        ".eif/PROJECT_MANIFEST.md",
        ".eif/ENVIRONMENT_POLICY.md",
        ".cursor/eif-runtime-manifest.json",
        ".cursor/eif-runtime-policy.json",
        ".cursor/hooks/eif_guard.cmd",
        ".cursor/hooks/eif_guard.py",
        ".cursor/hooks/eif_session.py",
        ".cursor/hooks/eif_reason_codes.py",
        ".cursor/hooks/eif_state.py",
        ".cursor/rules/eif-core.mdc",
        ".cursor/rules/eif-project-adapter.mdc",
        ".eif/RUNTIME_CAPABILITIES.md",
        "docs/BACKLOG.md",
        "apps/api/scripts/ops/apply_backlog_225_eif_decision_b.py",
        "apps/api/scripts/ops/stage_backlog_225_eif_commit.py",
    ]
    rels += [
        f".eif/runtime/programme/eif_program/{name}"
        for name in (
            "__init__.py",
            "clock.py",
            "design_artifacts.py",
            "engine.py",
            "errors.py",
            "facet_map.yaml",
            "facets.py",
            "journeys.py",
            "migrate.py",
            "store.py",
            "views.py",
        )
    ]
    rels += [
        ".eif/runtime/programme/eif_reason_codes.py",
        ".eif/runtime/programme/eiflib.py",
        ".eif/runtime/programme/manifest.json",
        ".eif/runtime/programme/program.py",
    ]
    subprocess.check_call(["git", "-C", str(root), "update-index", "--chmod=+x", ".cursor/hooks/eif_guard.cmd"])
    subprocess.check_call(["git", "-C", str(root), "add", *rels])
    subprocess.check_call(["git", "-C", str(root), "status", "-sb"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
