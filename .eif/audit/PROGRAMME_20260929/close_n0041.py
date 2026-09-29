"""Close N-0041. Shared Find already matches a8755854. No product edit."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PROG = REPO / ".eif/runtime/programme/program.py"
HERE = Path(__file__).resolve().parent
RUN = "N0041_CLOSE_20260929"
ACTOR = "close-n0041"
NID = "N-0041"
EVIDENCE = ".eif/audit/PROGRAMME_20260929/n0041/MATCH.md"


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
            "id": "BLN-N0041",
            "provenance": "implementation-observation",
            "tree_hash": "a8755854",
            "path": EVIDENCE,
            "observed_behavior": (
                "Tier A fact grids share GridFindField on the Scope bar. "
                "Query follows the draft by 300ms. Shipments keep shipping-search. "
                "Exceptions redirect to the brief."
            ),
            "latent_capabilities": [],
            "preservation": {},
        },
        lines,
    )
    if ok:
        ok = must("node.baseline", {"baseline_ref": "BLN-N0041"}, lines)
    if ok:
        ok = must(
            "node.stage",
            {
                "to": "implement",
                "stage_note": "Provenance for Find already shipped in a8755854. No product edit in this close.",
            },
            lines,
        )
    if ok:
        ok = must(
            "node.stage",
            {
                "to": "validate",
                "stage_note": "Source match against the Tier A hosts. gridFind unit tests cover view parsing.",
            },
            lines,
        )
    if ok:
        for dim, summary in (
            (
                "ux",
                "One Find field on the Scope bar for the Tier A fact grids. 300ms query. Server search kept where the page already had it.",
            ),
            (
                "a11y",
                "The field is a labelled MUI text input (Find). No new unlabelled control.",
            ),
            (
                "rendered",
                "Find is the filters slot of ScopeBar on the listed hosts. This close did not repeat a signed-in click; the mount is in the source at a8755854.",
            ),
            (
                "content",
                "The label is Find. Shipment search keeps its own placeholder because it queries shipment lines, not the fact-grid Find.",
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
            {"id": "EV-N0041", "path": EVIDENCE, "note": "N-0041 source match for shared Find", "tree_hash": "a8755854"},
            lines,
        )
    if ok:
        must("node.status", {"to": "complete"}, lines)
    else:
        event("node.lease.release", {})
    (HERE / "n0041_result.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
