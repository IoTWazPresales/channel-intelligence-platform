"""Advance N-0090 through acceptance. One programme command per subprocess."""
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
    "RUN-20261011-N0090-IMPL",
    "--actor",
    "gov-001",
]
NODE = "N-0090"
OUT = Path(__file__).resolve().parent


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
    data = json.loads(text[start:])
    return int(data["revision"])


def emit(event: str, body: dict) -> None:
    body = dict(body)
    if event != "baseline.add":
        body["node"] = NODE
        body["expected_revision"] = revision()
    path = OUT / f"_tmp_{event.replace('.', '_')}.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    result = subprocess.run(
        CLI + ["event", event, "--payload-file", str(path)],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    print(event, result.returncode, (result.stdout or "").strip(), (result.stderr or "").strip()[-500:])
    if result.returncode != 0:
        raise SystemExit(1)


def main() -> None:
    note_base = "Late and missing customer sell-through slots are an Attention row. The row opens the CST steward slots tab. A zero count adds no row."
    emit("node.stage", {"stage": "discovery", "stage_note": note_base + " pytest tests/test_brief_signals.py 2 passed."})
    emit("node.stage", {"stage": "challenge", "stage_note": "The worklist stays the steward page. Attention only points at it."})
    emit("node.stage", {"stage": "design", "stage_note": "One signal id cst_reports_late_missing. Link /admin/cst-steward?tab=slots."})
    emit(
        "node.stage",
        {
            "stage": "implement",
            "stage_note": "Shipped in eb230ccf. Live signed-in Overview on 2026-10-11 showed 7 missing customer sell-through reports.",
        },
    )
    emit(
        "evidence.add",
        {
            "path": ".eif/audit/PROGRAMME_20261011/N0090_ACCEPT.md",
            "note": "N-0090 live Attention row and CST slots page, Warren accepted 2026-10-11.",
            "provenance": "implementation-observation",
        },
    )
    evidence = {"path": ".eif/audit/PROGRAMME_20261011/N0090_ACCEPT.md", "summary": "Live row and slots page. pytest 2 passed."}
    for dim, rationale in (
        ("testing", "tests/test_brief_signals.py 2 passed on 2026-10-11."),
        ("observability", "The row is the signal. It is visible on Overview and in GET /api/v1/brief/signals."),
        ("ux", "The row names the count and opens the existing slots worklist."),
        ("a11y", "Text row and link in the existing Attention list. No separate axe run."),
        ("rendered", "Signed-in Overview and CST steward slots rendered in the browser, dark, 1440."),
        ("content", "Wording is customer sell-through reports are missing. The slots table shows status missing."),
    ):
        emit("node.quality", {"dim": dim, "state": "pass", "evidence": evidence, "rationale": rationale})
    emit(
        "node.stage",
        {
            "stage": "validate",
            "stage_note": "Self-checked R1. Warren accepted the live pages on 2026-10-11.",
        },
    )
    emit(
        "node.verification",
        {
            "kind": "behavioral",
            "state": "pass",
            "evidence": ".eif/audit/PROGRAMME_20261011/N0090_ACCEPT.md",
        },
    )
    emit(
        "node.stage",
        {
            "stage": "verify",
            "stage_note": "R1 self-verification in RUN-20261011-N0090-IMPL. Warren accepted the live Attention row and the slots page.",
        },
    )
    emit("node.accept", {})
    emit("node.status", {"status": "complete"})
    emit("node.lease.release", {})
    print("node_revision", revision())


if __name__ == "__main__":
    main()
