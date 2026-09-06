"""Finish N-0018 baseline preservation + stage implement after LATENT_UNPRESERVED."""
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


def node_rev() -> int:
    r = subprocess.run(
        [sys.executable, str(PROG), "status", "--node", NODE],
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
    prog(["status", "--node", NODE])
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
