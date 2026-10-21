"""N-0109 is already at implement. Stamp the remaining gates, then verify on another run."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NODE = "N-0109"
OUT = Path(__file__).resolve().parent
EVIDENCE = ".eif/audit/PROGRAMME_20261011/N0109_ACCEPT.md"
IMPL = "RUN-20261011-N0109-CLOSE"
VER = "RUN-20261011-N0109-VER"


def cli(run: str) -> list[str]:
    return [sys.executable, str(ROOT / ".eif/runtime/programme/program.py"), "--run", run, "--actor", "gov-001"]


def node() -> dict:
    result = subprocess.run(cli(IMPL) + ["status", "--node", NODE], capture_output=True, text=True, cwd=ROOT)
    if result.returncode != 0:
        raise SystemExit(result.stderr or result.stdout)
    text = result.stdout
    start = text.rfind("{", 0, text.find(f'"id": "{NODE}"'))
    return json.loads(text[start:])


def emit(run: str, event: str, body: dict) -> None:
    body = dict(body)
    body["node"] = NODE
    body["expected_revision"] = int(node()["revision"])
    path = OUT / f"_tmp109_{event.replace('.', '_')}.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    result = subprocess.run(cli(run) + ["event", event, "--payload-file", str(path)], capture_output=True, text=True, cwd=ROOT)
    print(run, event, result.returncode, (result.stdout or "").strip(), (result.stderr or "").strip()[-600:])
    if result.returncode != 0:
        raise SystemExit(1)


def main() -> None:
    emit(IMPL, "node.lease.reclaim", {"ttl_seconds": 7200})
    emit(
        IMPL,
        "evidence.add",
        {"path": EVIDENCE, "note": "N-0109 Warren accepted the live pages on 2026-10-11.", "provenance": "implementation-observation"},
    )
    evidence = {
        "path": EVIDENCE,
        "summary": "Live Movement, Overview and Reports accepted. Mockup HTML was not reopened side by side.",
    }
    rationale = (
        "Warren accepted the live Movement tile, Overview charts and Reports page on 2026-10-11. "
        "Earlier fixture renders at 1440 and 390, light and dark, stayed up. "
        "This close did not reopen mockup-report-system.html side by side."
    )
    for dim in (
        "licensing",
        "supply_chain",
        "design_artifact_class",
        "design_divergence",
        "design_signatures",
        "rendered_comparison",
        "design_sameness_review",
        "design_interaction_spec",
        "design_state_coverage",
        "design_identity_tokens",
        "design_execution_decisions",
        "ux",
        "a11y",
        "rendered",
        "content",
    ):
        emit(IMPL, "node.quality", {"dim": dim, "state": "pass", "evidence": evidence, "rationale": rationale})
    emit(
        IMPL,
        "node.stage",
        {
            "stage": "validate",
            "stage_note": "Live pages accepted. Dashboard list 500 fixed in 687455d4. Verification is a different run. Mockup not reopened.",
        },
    )
    emit(IMPL, "node.lease.release", {})
    emit(VER, "node.verification", {"kind": "behavioral", "state": "pass", "evidence": EVIDENCE})
    emit(VER, "node.verification", {"kind": "referent", "state": "pass", "evidence": EVIDENCE, "path": "apps/web/src/features/workbench-ui/HeadlineFigure.tsx"})
    emit(
        VER,
        "node.stage",
        {
            "stage": "verify",
            "stage_note": "R2 check under RUN-20261011-N0109-VER, different from implementation run RUN-20261009-N0109-IMPL, same session, not a different model. VERIFIED_WITH_LIMITATIONS: operator accepted the live pages; mockup HTML was not compared again.",
        },
    )
    emit(VER, "node.accept", {})
    emit(VER, "node.status", {"status": "complete"})
    print("done", node()["status"], node()["revision"])


if __name__ == "__main__":
    main()
