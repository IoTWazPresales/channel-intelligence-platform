"""Attach BLN-0001 and record preservation, then stage implement."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PROG = REPO / ".eif/runtime/programme/program.py"
RUN = "NS7_EXEC_20260906"
NODE = "N-0017"


def prog(args: list[str]) -> str:
    r = subprocess.run([sys.executable, str(PROG), *args], cwd=REPO, capture_output=True, text=True)
    out = (r.stdout or r.stderr).strip()
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
        raise SystemExit("no revision")
    return int(m.group(1))


def main() -> None:
    sys.path.insert(0, str(PROG.parent))
    from eif_program.store import ProgramStore

    state = ProgramStore(REPO).load()
    node = state["nodes"][NODE]
    pres = dict(node.get("preservation") or {})
    pres.update(
        {
            "plan_vs_executed_workspace": "PlanVsExecutedView relocated below lab Execution strip; not deleted",
            "plan_vs_executed_route": "/plan-vs-executed page retained",
            "stock_cover_lens": "CoverLensView unchanged",
            "stock_movement_lens": "MovementLensView unchanged",
            "stock_inbound_lens": "/stock?lens=inbound still Supply InboundShipmentsWorkspace",
            "customer_account_sell_out_gap": "brief signal unchanged; not this Execution lens",
            "pipeline_fill_pct": "stock regime strip unchanged; not this Execution lens",
            "response_container_badge": "spine response badge unchanged until a later Administration/Overview node",
        }
    )
    rev = node_rev()
    prog(
        [
            "--run",
            RUN,
            "--actor",
            "gov-001",
            "event",
            "node.patch",
            "--payload",
            json.dumps({"node": NODE, "expected_revision": rev, "preservation": pres}),
        ]
    )
    rev = node_rev()
    prog(
        [
            "--run",
            RUN,
            "--actor",
            "gov-001",
            "event",
            "node.stage",
            "--payload",
            json.dumps({"node": NODE, "expected_revision": rev, "to": "implement"}),
        ]
    )


if __name__ == "__main__":
    main()
