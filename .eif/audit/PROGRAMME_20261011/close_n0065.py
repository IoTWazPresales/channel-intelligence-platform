"""Re-check N-0065 behavior on cip and close it. One programme command per subprocess."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PROGRAM = str(ROOT / ".eif/runtime/programme/program.py")
OUT = Path(__file__).resolve().parent
RUN = "RUN-20261011-N0065-VER3"
NODE = "N-0065"


def cli() -> list[str]:
    return [sys.executable, PROGRAM, "--run", RUN, "--actor", "gov-001"]


def load() -> dict:
    result = subprocess.run(cli() + ["status", "--node", NODE], capture_output=True, text=True, cwd=ROOT)
    if result.returncode != 0:
        raise SystemExit(result.stderr or result.stdout)
    text = result.stdout
    marker = f'"id": "{NODE}"'
    start = text.rfind("{", 0, text.find(marker))
    return json.loads(text[start:])


def emit(event: str, body: dict) -> None:
    body = dict(body)
    body["node"] = NODE
    body["expected_revision"] = int(load()["revision"])
    path = OUT / f"_tmp65_{event.replace('.', '_')}.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    result = subprocess.run(
        cli() + ["event", event, "--payload-file", str(path)],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    print(event, result.returncode, (result.stdout or "").strip(), (result.stderr or "").strip()[-500:])
    if result.returncode != 0:
        raise SystemExit(1)


def main() -> None:
    emit("node.lease.acquire", {"ttl_seconds": 7200})
    emit(
        "evidence.add",
        {
            "path": ".eif/audit/PROGRAMME_20261011/N0065_SCOPE_PROBE.md",
            "note": "N-0065 read-only cip scope probe 2026-10-11. Other product lines: 0.",
            "provenance": "implementation-observation",
        },
    )
    emit(
        "node.verification",
        {
            "kind": "behavioral",
            "state": "pass",
            "evidence": ".eif/audit/PROGRAMME_20261011/N0065_SCOPE_PROBE.md",
        },
    )
    emit(
        "node.verification",
        {
            "kind": "referent",
            "state": "pass",
            "evidence": ".eif/audit/PROGRAMME_20261011/N0065_SCOPE_PROBE.md",
            "path": "apps/api/alembic/versions/20261009_0027_current_pick_index_order_no_product_steward.py",
        },
    )
    emit(
        "node.stage",
        {
            "stage": "verify",
            "stage_note": "2026-10-11 read-only cip probe. Planner with no lines: 0 current rows. Planner on one line: 0 rows from other product lines. The one product-less row inherits that line. Same session as the probe, not a different model. VERIFIED_WITH_LIMITATIONS.",
        },
    )
    emit("node.status", {"status": "complete"})
    emit("node.lease.release", {})
    done = load()
    print("status", done.get("status"), "stage", done.get("stage"), "rev", done.get("revision"))
    print("behavioral", (done.get("verification") or {}).get("behavioral"))


if __name__ == "__main__":
    main()
