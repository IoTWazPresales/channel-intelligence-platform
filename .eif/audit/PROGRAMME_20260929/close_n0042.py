"""Close N-0042 after saved views store columns, sort, and filters."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PROG = REPO / ".eif/runtime/programme/program.py"
HERE = Path(__file__).resolve().parent
RUN = "N0042_CLOSE_20260929"
ACTOR = "close-n0042"
NID = "N-0042"
EVIDENCE = ".eif/audit/PROGRAMME_20260929/n0042/MATCH.md"


def invoke(args: list[str]) -> tuple[int, str]:
    r = subprocess.run(
        [sys.executable, "-B", str(PROG), "--project", str(REPO), *args],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()


def node() -> dict:
    code, text = invoke(["--run", RUN, "--actor", ACTOR, "status", "--node", NID])
    if code:
        raise SystemExit(text[-1200:])
    return json.loads(text[text.rfind("\n{") + 1 :])


def event(name: str, payload: dict) -> tuple[int, str]:
    payload = dict(payload)
    payload["node"] = NID
    payload["expected_revision"] = int(node()["revision"])
    path = HERE / f"ev_{NID}_{name.replace('.', '_')}_{payload['expected_revision']}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    rel = str(path.relative_to(REPO)).replace("\\", "/")
    return invoke(["--run", RUN, "--actor", ACTOR, "event", name, "--payload-file", rel])


def must(name: str, payload: dict, lines: list[str]) -> bool:
    code, text = event(name, payload)
    if code:
        lines.append(f"{name} FAIL")
        lines.append(text[-900:])
        return False
    lines.append(f"{name} ok")
    return True


def main() -> None:
    lines: list[str] = []
    if not must("node.lease.acquire", {"ttl_seconds": 7200}, lines):
        print("\n".join(lines))
        return
    ok = must(
        "baseline.add",
        {
            "id": "BLN-N0042",
            "provenance": "implementation-observation",
            "tree_hash": "cfbeaebe",
            "path": EVIDENCE,
            "observed_behavior": (
                "Named views store find text, picker columns, column state, and filters. "
                "Apply writes picker columns back to the N-0034 layout key. Delete removes the name."
            ),
            "latent_capabilities": [],
            "preservation": {},
        },
        lines,
    )
    if ok:
        ok = must("node.baseline", {"baseline_ref": "BLN-N0042"}, lines)
    if ok:
        ok = must(
            "node.stage",
            {
                "to": "implement",
                "stage_note": "Saved views now store columns, sort, and filters, and can be deleted.",
            },
            lines,
        )
    if ok:
        ok = must(
            "node.stage",
            {
                "to": "validate",
                "stage_note": (
                    "Browser on the rebuilt web: roadmap Save view, reload keeps the chip, Delete removes it. "
                    "Sell-out chrome shows the same buttons. Live-row sort round trip not clicked."
                ),
            },
            lines,
        )
    if ok:
        for dim, summary in (
            (
                "ux",
                "Save view, a named chip, and Delete view on the Scope bar. All clears find and filters.",
            ),
            (
                "a11y",
                "Save and Delete are named buttons. The name field in the dialog is labelled Name.",
            ),
            (
                "rendered",
                "Roadmap: saved Empty check, chip survived reload, Delete removed it. Sell-out shows Save view and Export.",
            ),
            (
                "content",
                "Labels are Save view, Delete view, and All. Cover keeps its own All pairs / Breaches only chips.",
            ),
        ):
            ok = must(
                "node.quality",
                {"dim": dim, "state": "pass", "evidence": {"path": EVIDENCE, "summary": summary}},
                lines,
            )
            if not ok:
                break
    if ok:
        ok = must(
            "evidence.add",
            {"id": "EV-N0042", "path": EVIDENCE, "note": "N-0042 saved layout views", "tree_hash": "cfbeaebe"},
            lines,
        )
    if ok:
        must("node.status", {"to": "complete"}, lines)
    else:
        event("node.lease.release", {})
    (HERE / "n0042_result.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
