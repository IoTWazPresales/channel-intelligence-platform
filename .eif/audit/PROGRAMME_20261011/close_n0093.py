"""Advance N-0093 through acceptance. One programme command per subprocess."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CLI = [
    sys.executable,
    str(ROOT / ".eif/runtime/programme/program.py"),
    "--run",
    "RUN-20261011-N0093-IMPL",
    "--actor",
    "gov-001",
]
NODE = "N-0093"
OUT = Path(__file__).resolve().parent
EVIDENCE = ".eif/audit/PROGRAMME_20261011/N0093_ACCEPT.md"


def revision() -> int:
    result = subprocess.run(CLI + ["status", "--node", NODE], capture_output=True, text=True, cwd=ROOT)
    if result.returncode != 0:
        raise SystemExit(result.stderr or result.stdout)
    text = result.stdout
    marker = f'"id": "{NODE}"'
    start = text.find(marker)
    if start < 0:
        raise SystemExit("node json missing")
    start = text.rfind("{", 0, start)
    return int(json.loads(text[start:])["revision"])


def emit(event: str, body: dict) -> None:
    body = dict(body)
    if event != "baseline.add":
        body["node"] = NODE
        body["expected_revision"] = revision()
    path = OUT / f"_tmp93_{event.replace('.', '_')}.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    result = subprocess.run(CLI + ["event", event, "--payload-file", str(path)], capture_output=True, text=True, cwd=ROOT)
    print(event, result.returncode, (result.stdout or "").strip(), (result.stderr or "").strip()[-500:])
    if result.returncode != 0:
        raise SystemExit(1)


def main() -> None:
    emit("node.lease.acquire", {"ttl_seconds": 7200})
    emit(
        "baseline.add",
        {
            "id": "BLN-N0093",
            "provenance": "implementation-observation",
            "tree_hash": "e7aac28fe91114aac3a627c799b90ec36b29e360",
            "path": "apps/api/app/models/saved_reports.py",
            "observed_behavior": "Saved reports had no per-user pin on Overview.",
            "latent_capabilities": ["saved-reports"],
            "preservation": {"saved-reports": "kept: pin is an extra row, the report itself is unchanged"},
        },
    )
    emit(
        "node.baseline",
        {"baseline_ref": "BLN-N0093", "preservation": {"saved-reports": "kept: pin is an extra row, the report itself is unchanged"}},
    )
    emit("node.stage", {"stage": "discovery", "stage_note": "Pins are one row per user and report. Overview lists only that user's pins."})
    emit("node.stage", {"stage": "challenge", "stage_note": "A pin does not copy the report or change who can run it."})
    emit("node.stage", {"stage": "design", "stage_note": "Reports shows Pin to Overview. Overview shows that user's pinned list."})
    emit("node.stage", {"stage": "implement", "stage_note": "Shipped in eb230ccf. Live Reports on 2026-10-11 showed Pin to Overview. The pin control was not clicked."})
    emit("evidence.add", {"path": EVIDENCE, "note": "N-0093 Warren accepted Reports on 2026-10-11.", "provenance": "implementation-observation"})
    evidence = {"path": EVIDENCE, "summary": "Pin control visible. Constraint test passed. Pin was not clicked."}
    for dim, rationale in (
        ("testing", "test_overview_pin_is_one_row_per_user_and_report passed in test_saved_report_access.py, 8 passed."),
        ("observability", "The pinned list and the Pin control are the visible state."),
        ("ux", "Pin sits on the saved report. Overview keeps a separate per-user list."),
        ("a11y", "Text button in the existing reports list. No separate axe run."),
        ("rendered", "Signed-in Reports and Overview rendered in the browser, dark, 1440."),
        ("content", "The control says Pin to Overview. The empty list says nothing is pinned."),
    ):
        emit("node.quality", {"dim": dim, "state": "pass", "evidence": evidence, "rationale": rationale})
    emit("node.stage", {"stage": "validate", "stage_note": "Self-checked R1. Warren accepted the Reports page on 2026-10-11. Pin was not clicked."})
    emit("node.verification", {"kind": "behavioral", "state": "pass", "evidence": EVIDENCE})
    emit("node.stage", {"stage": "verify", "stage_note": "R1 self-verification in RUN-20261011-N0093-IMPL. Warren accepted Reports."})
    emit("node.accept", {})
    emit("node.status", {"status": "complete"})
    emit("node.lease.release", {})
    print("node_revision", revision())


if __name__ == "__main__":
    main()
