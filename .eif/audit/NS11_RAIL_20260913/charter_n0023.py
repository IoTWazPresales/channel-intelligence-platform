"""Charter N-0023: port LabShell BACKLOG-181 rail treatment into production CapabilityRail.

IA (rail expand vs in-page tabs) is D-0010 — proposed after source+render evidence; not implemented here.
Do not reopen N-0013. D-0002 untouched. No writes to cip.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PROG = REPO / ".eif/runtime/programme/program.py"
RUN = "NS11_RAIL_20260913"
NODE = "N-0023"
ACTOR = "gov-001"

ACS = [
    "Governing visual input: LabShell rail as implemented in apps/web/src/design-lab/shell/LabShell.tsx (commits 1f434e4, 130189e). Production apps/web/src/features/shell/CapabilityRail.tsx is the old LabShell; port the current lab treatment. Do not cite a frozen design-language version or grammar number.",
    "Port: raised opaque surface on the expanded domain header; sticky group header inside the scrolling list; nested guide rail removed (indent kept); active leaf carried by a 3px rounded bar plus text weight, not a Mui-selected fill.",
    "Collapsed-active domain (active but manually collapsed) treatment is decided and recorded. Do not leave it implicit.",
    "D-0010 (rail expand vs in-page LensTabs) is chartered with source and render evidence. Operator accepts or rejects before any IA change. This node does not collapse the rail, remove tabs, or change navGroups hrefs/labels/order.",
    "Preserve RAIL_WIDTH 252, role gating, leafIsActive, expand/collapse IconButton and aria-label, badges, directory footer, localStorage group-expanded state, production testids, and label wrap. D-0002 mapping-queue disposition untouched. N-0006 and N-0013 not reopened.",
    "Browser-verify 1280x800 vs lab rail. Rail also appears in the md-down Drawer — verify 390x844 drawer. Do not use browser_cdp. NUMBER RULE does not apply (no headline figures).",
    "target_artifact_class: high_fidelity",
    "Independent GOV-008 vs this node's implementation_run",
]

PRESERVATION = {
    "customer_account_sell_out_gap": "brief signal unchanged; not rail chrome",
    "pipeline_fill_pct": "stock Cover regime strip unchanged; not rail chrome",
    "response_container_badge": "unchanged this node",
    "rail_width": "RAIL_WIDTH remains 252",
    "nav_groups": "navConfig ids, labels, hrefs, order, role gates, leaf status vocabulary unchanged",
    "rail_expand_state": "NAV_STORAGE_GROUP_EXPANDED localStorage contract unchanged",
    "lens_tabs": "in-page LensTabs unchanged until D-0010 is accepted",
    "d0002": "mapping-queue disposition untouched",
    "n0006": "not reopened",
    "n0013": "not reopened",
}


def prog(args: list[str]) -> str:
    r = subprocess.run([sys.executable, str(PROG), *args], cwd=REPO, capture_output=True, text=True)
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    print(out)
    if r.returncode:
        raise SystemExit(r.returncode)
    return out


def node_rev(nid: str = NODE) -> int:
    r = subprocess.run(
        [sys.executable, str(PROG), "status", "--node", nid],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    m = re.search(r'"revision":\s*(\d+)', r.stdout or "")
    if not m:
        print(r.stdout, r.stderr)
        raise SystemExit("no revision")
    return int(m.group(1))


def main() -> None:
    prog(["status"])
    prog(["frontier"])
    prog(
        [
            "--run",
            RUN,
            "--actor",
            ACTOR,
            "event",
            "node.add",
            "--payload",
            json.dumps(
                {
                    "id": NODE,
                    "title": "Port BACKLOG-181 LabShell rail treatment into production",
                    "class": "redesign",
                    "origin": "decomposition",
                    "status": "ready",
                    "facets": ["design_experience", "ui"],
                    "risk": "R2",
                    "touches_existing": True,
                    "acceptance": "auto",
                    "acceptance_criteria": ACS,
                    "depends_on": ["N-0013", "N-0022"],
                    "target_artifact_class": "high_fidelity",
                }
            ),
        ]
    )
    rev = node_rev()
    prog(
        [
            "--run",
            RUN,
            "--actor",
            ACTOR,
            "event",
            "node.lease.acquire",
            "--payload",
            json.dumps({"node": NODE, "expected_revision": rev, "ttl_seconds": 14400}),
        ]
    )
    rev = node_rev()
    prog(
        [
            "--run",
            RUN,
            "--actor",
            ACTOR,
            "event",
            "node.baseline",
            "--payload",
            json.dumps(
                {
                    "node": NODE,
                    "expected_revision": rev,
                    "baseline_ref": "BLN-0001",
                    "preservation": PRESERVATION,
                }
            ),
        ]
    )
    rev = node_rev()
    prog(
        [
            "--run",
            RUN,
            "--actor",
            ACTOR,
            "event",
            "node.stage",
            "--payload",
            json.dumps({"node": NODE, "expected_revision": rev, "to": "implement"}),
        ]
    )
    prog(["status", "--node", NODE])
    prog(["frontier"])


if __name__ == "__main__":
    main()
