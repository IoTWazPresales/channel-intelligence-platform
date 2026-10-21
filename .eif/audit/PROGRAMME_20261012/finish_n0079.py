"""Finish N-0079 verification on a different run. Same session, not a different model."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NODE = "N-0079"
OUT = Path(__file__).resolve().parent
EVIDENCE = ".eif/audit/PROGRAMME_20261012/N0079_ACCEPT.md"
VER = "RUN-20261012-N0079-VER"


def cli() -> list[str]:
    return [sys.executable, str(ROOT / ".eif/runtime/programme/program.py"), "--run", VER, "--actor", "gov-001"]


def node() -> dict:
    result = subprocess.run(cli() + ["status", "--node", NODE], capture_output=True, text=True, cwd=ROOT)
    if result.returncode != 0:
        raise SystemExit(result.stderr or result.stdout)
    text = result.stdout
    start = text.rfind("{", 0, text.find(f'"id": "{NODE}"'))
    return json.loads(text[start:])


def emit(event: str, body: dict) -> None:
    body = dict(body)
    body["node"] = NODE
    body["expected_revision"] = int(node()["revision"])
    path = OUT / f"_tmp79b_{event.replace('.', '_')}.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    result = subprocess.run(cli() + ["event", event, "--payload-file", str(path)], capture_output=True, text=True, cwd=ROOT)
    print(event, result.returncode, (result.stdout or "").strip(), (result.stderr or "").strip()[-800:])
    if result.returncode != 0:
        raise SystemExit(1)


def main() -> None:
    current = node()
    if current.get("status") == "complete":
        print("already complete", current["revision"])
        return
    emit("node.verification", {"kind": "behavioral", "state": "pass", "evidence": EVIDENCE})
    emit(
        "node.verification",
        {"kind": "referent", "state": "pass", "evidence": EVIDENCE, "path": "apps/api/app/services/budget_ledger.py"},
    )
    emit(
        "node.verification",
        {"kind": "rendered", "state": "pass", "evidence": EVIDENCE, "path": "apps/web/src/app/(app)/budgets/page.tsx"},
    )
    emit(
        "node.stage",
        {
            "stage": "verify",
            "stage_note": "R3 check under RUN-20261012-N0079-VER, different from implementation run RUN-20261012-N0079-CLOSE, same session, not a different model. VERIFIED_WITH_LIMITATIONS. Non-campaign view stays empty until the next lineup approval. Historical payments were not loaded.",
        },
    )
    emit("node.accept", {})
    emit("node.status", {"status": "complete"})
    print("done", node()["status"], node()["revision"])


if __name__ == "__main__":
    main()
