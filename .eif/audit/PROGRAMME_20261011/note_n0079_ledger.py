"""Record the N-0079 clone proof and close the migrate blocker. Do not mark complete."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PROGRAM = str(ROOT / ".eif/runtime/programme/program.py")
OUT = Path(__file__).resolve().parent
LOG = OUT / "note_n0079_ledger_log.txt"
RUN = "RUN-20261012-N0079-LEDGER"
NODE = "N-0079"


def cli() -> list[str]:
    return [sys.executable, PROGRAM, "--run", RUN, "--actor", "gov-001"]


def load() -> dict:
    result = subprocess.run(cli() + ["status", "--node", NODE], capture_output=True, text=True, cwd=ROOT)
    if result.returncode != 0:
        raise SystemExit(result.stderr or result.stdout)
    text = result.stdout
    start = text.rfind("{", 0, text.find(f'"id": "{NODE}"'))
    return json.loads(text[start:])


def emit(event: str, body: dict) -> None:
    body = dict(body)
    body["node"] = NODE
    body["expected_revision"] = int(load()["revision"])
    path = OUT / f"_tmp_{NODE}_{event.replace('.', '_')}.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    result = subprocess.run(cli() + ["event", event, "--payload-file", str(path)], capture_output=True, text=True, cwd=ROOT)
    line = f"{event} {result.returncode} {(result.stdout or '').strip()} {(result.stderr or '').strip()[-400:]}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    if result.returncode != 0:
        raise SystemExit(1)


def main() -> None:
    LOG.write_text("", encoding="utf-8")
    emit("node.lease.acquire", {"ttl_seconds": 7200})
    emit(
        "node.blocker.close",
        {
            "id": "BL-N0079-MIGRATE",
            "note": "Clone load passed, then cip is on 20261012_0033. Historical consume rows written 435, second load wrote 0.",
        },
    )
    if load().get("lease") is None:
        emit("node.lease.acquire", {"ttl_seconds": 7200})
    emit(
        "evidence.add",
        {
            "path": ".eif/audit/PROGRAMME_20261011/N0079_LEDGER.md",
            "note": "N-0079 clone proof then cip load. Counts only.",
            "provenance": "implementation-observation",
        },
    )
    emit(
        "node.stage_note",
        {
            "note": (
                "2026-10-12 clone cip_n0079 from template cip. Historical load wrote 435, skipped 4 with no result, "
                "second load wrote 0. Owner update and delete raised append-only and the row count stayed 435. "
                "cip is on 20261012_0033 with the same counts. Budgets shows product line by quarter and a row click "
                "drills to historical_import consume rows. Not complete: no pending column, no cap column, and the "
                "rest of D-0059 (campaign view switch, unplanned and unknown-quarter buckets, an admin cap control) "
                "is still open. Caps flag and do not block."
            )
        },
    )
    if load().get("lease") is not None:
        emit("node.lease.release", {})
    done = load()
    print(f"status {done.get('status')} rev {done.get('revision')} lease {done.get('lease') is not None}", flush=True)


if __name__ == "__main__":
    main()
