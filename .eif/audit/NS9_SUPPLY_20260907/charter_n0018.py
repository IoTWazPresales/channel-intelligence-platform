"""Charter N-0018 Supply & Inbound against D-0008 lab SupplySurface. Do not reject/recharter N-0011."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PROG = REPO / ".eif/runtime/programme/program.py"
RUN = "NS9_SUPPLY_20260907"
NODE = "N-0018"
ACTOR = "gov-001"

ACS = [
    "Governing design input: D-0008 Supply & Inbound as implemented in apps/web/src/design-lab/surfaces/DomainOverviewSurface.tsx SupplySurface (and labNav leaves at /design-lab/supply). Do not cite a frozen design-language version or grammar number.",
    "Production mounts that lab chrome; relocate existing inbound shipments workspace, shipment-evidence, and PO management — do not delete.",
    "Coverage-map every production Supply & Inbound route COVERED / PARTIAL / UNCOVERED; migrate COVERED and PARTIAL; record UNCOVERED. Lab SOURCE is primary; a comparison naming no source file is not a comparison.",
    "NUMBER RULE on every headline figure: print current_database() first; classify (i) label (ii) computation (iii) real signal. Never change a number to make two surfaces agree.",
    "Browser-verify 1280x800 vs lab. Supply is not a named DIRECTION 390px workflow — 1280 only unless a named workflow is on a surface you touch.",
    "Keep Partly built and Planned markers. D-0002 mapping-queue disposition untouched.",
    "target_artifact_class: high_fidelity",
    "Independent GOV-008 vs this node's implementation_run",
]

PRESERVATION = {
    "customer_account_sell_out_gap": "brief signal unchanged; not Supply & Inbound",
    "pipeline_fill_pct": "stock regime strip unchanged; not Supply & Inbound",
    "response_container_badge": "spine response badge unchanged until Administration/Overview",
    "stock_cover_movement_execution": "Stock lenses other than inbound stay as shipped; not this node",
    "inbound_shipments_workspace": "existing InboundShipmentsWorkspace relocated under Supply, not deleted",
    "shipment_evidence": "/admin/shipment-evidence remains the Receipts & POD leaf (partial honesty kept)",
    "po_management": "/admin/po-management remains reachable; not deleted",
    "import_column_mapping": "CanonicalColumnMappingPanel remains desktop-first",
    "d0002": "mapping-queue disposition untouched",
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
                    "title": "NS-8 Supply & Inbound from design-lab",
                    "class": "redesign",
                    "origin": "decomposition",
                    "status": "ready",
                    "facets": ["design_experience", "ui"],
                    "risk": "R3",
                    "touches_existing": True,
                    "acceptance": "auto",
                    "acceptance_criteria": ACS,
                    "depends_on": ["N-0013", "N-0007"],
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
