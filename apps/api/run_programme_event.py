"""One-shot programme event runner — avoids PowerShell JSON mangling on --payload."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / ".eif" / "runtime" / "programme"
sys.path.insert(0, str(RUNTIME))

from eif_program.store import ProgramStore  # noqa: E402
from eif_program.views import write_views  # noqa: E402


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: run_programme_event.py <event-type> <payload.json> [run-id]", file=sys.stderr)
        return 2
    event_type = sys.argv[1]
    payload = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    run = sys.argv[3] if len(sys.argv) > 3 else "NS2_RESUME_AFTER_RUNTIME_REPAIR_20260901"
    st = ProgramStore(ROOT, run=run)
    state = st.append(event_type, payload, actor="agent")
    write_views(st.project, state)
    print("rev", state["programme"]["snapshot_revision"])
    if "node" in payload and payload["node"] in state["nodes"]:
        print("node_rev", state["nodes"][payload["node"]]["revision"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
