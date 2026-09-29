"""Implementer evidence + quality (self-verification) + finding.defer + validate + lease.release for N-0053.

Do not complete: GOV-008 independent verification (referent, R2) is a later, different run.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
PROG = REPO / ".eif/runtime/programme/program.py"
RUN = "N0053_IMPL_20260929"
ACTOR = "impl-n0053"
NODE = "N-0053"
HERE = Path(__file__).resolve().parent
IMPL = ".eif/audit/PROGRAMME_20260924/n0053/IMPL.md"
DESIGN = ".eif/audit/PROGRAMME_20260924/n0053/DESIGN.md"
PAYLOAD_DIR = HERE / "payloads" / "validate"
URL = "http://localhost:3000/stock?lens=movement"


def run(args: list[str]) -> str:
    r = subprocess.run(
        [sys.executable, "-B", str(PROG), "--project", str(REPO), *args],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    out = (r.stdout or "") + (r.stderr or "")
    print(out.strip())
    if r.returncode:
        raise SystemExit(r.returncode)
    return out


def node_rev() -> int:
    out = run(["--run", RUN, "--actor", ACTOR, "status", "--node", NODE])
    m = re.search(r'"revision":\s*(\d+)', out)
    if not m:
        raise SystemExit("no revision")
    return int(m.group(1))


def event(name: str, payload: dict) -> None:
    payload = dict(payload)
    payload["node"] = NODE
    payload["expected_revision"] = node_rev()
    PAYLOAD_DIR.mkdir(parents=True, exist_ok=True)
    path = PAYLOAD_DIR / f"{NODE}_{name.replace('.', '_')}_{payload['expected_revision']}_{payload.get('dim') or payload.get('kind') or payload.get('id') or payload.get('code') or 'x'}.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    run(
        [
            "--run",
            RUN,
            "--actor",
            ACTOR,
            "event",
            name,
            "--payload-file",
            str(path.relative_to(REPO)).replace("\\", "/"),
        ]
    )


def load(name: str) -> dict:
    return json.loads((HERE / name).read_text(encoding="utf-8"))


def main() -> None:
    event("evidence.add", load("ev_design.json"))
    event("evidence.add", load("ev_impl.json"))

    quals = [
        (
            "ux",
            {
                "path": IMPL,
                "summary": "both = two real identity columns pinned where the welded column sat; picker excludes what the preference pins and offers the complement under Line identity; flip back restores one column. Self-verification in the implementation run.",
            },
        ),
        (
            "a11y",
            {
                "path": IMPL,
                "summary": "Identity columns are ordinary AG Grid columns (header sort button, filter menu, keyboard nav inherited from EnterpriseDataGrid defaultColDef). Picker group uses the existing FactColumnPicker checkbox list. No axe/keyboard full pass this run.",
            },
        ),
        (
            "rendered",
            {
                "path": IMPL,
                "url": URL,
                "viewports": ["1024x576"],
                "summary": "channel-ops Inventory grid (Mustek) under both: SKU + Sales model columns, filter icons, Sales model header sort; picker shows Fact fields + Reference only. Under sku: one SKU column; picker leads with Line identity > Sales model. Settings save + reload keep the value. Self-verification, not independent.",
            },
        ),
        (
            "content",
            {
                "path": IMPL,
                "summary": "Settings option label: 'SKU and sales model number (two columns)'. Column headers fixed 'SKU' / 'Sales model'; empty cells render an em dash. Text-slot consumers keep 'SKU · Sales model' (deferred finding).",
            },
        ),
    ]
    for dim, evidence in quals:
        event("node.quality", {"dim": dim, "state": "pass", "evidence": evidence})

    event(
        "node.verification",
        {
            "kind": "rendered",
            "state": "pass",
            "evidence": {
                "path": IMPL,
                "url": URL,
                "independence": "self-verification (same run/actor as implementation)",
                "checks": [
                    "settings both saved + reload",
                    "inventory grid two identity columns sortable/filterable",
                    "picker excludes pinned pair under both",
                    "flip back to sku: one column, Line identity offers Sales model",
                ],
            },
        },
    )

    event("finding.defer", load("finding_textslot.json"))

    event("node.stage", {"to": "validate"})
    event(
        "node.stage_note",
        {
            "stage_note": (
                "Implementer validate (run N0053_IMPL_20260929): both renders two real field columns via "
                "lineIdentifierColumns through useFactColumns.identityColDefs (N-0034 picker mechanism), "
                "registry identity group on 10 hosts, 7 non-picker AG Grid hosts + 2 MUI-table files on the same helper. "
                "tsc 0, eslint 0 errors, focused vitest 58/58, pytest 91. Browser smoke on channel-ops Inventory + settings "
                "(self-verification). Found + fixed stale runtime: orphaned uvicorn (5 days) and stale next build. "
                "Text-slot single-cell consumers deferred (finding). Independent GOV-008 referent/rendered not recorded; "
                "Opus CONSULT stays BACKLOG-209 until Anthropic usage is available. Do not complete."
            )
        },
    )
    event("node.lease.release", {})
    run(["--run", RUN, "--actor", ACTOR, "status", "--node", NODE])


if __name__ == "__main__":
    main()
