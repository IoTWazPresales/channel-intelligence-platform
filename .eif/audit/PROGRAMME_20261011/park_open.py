"""Park the still-open invite and unbuilt nodes. One programme command per subprocess."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PROGRAM = str(ROOT / ".eif/runtime/programme/program.py")
OUT = Path(__file__).resolve().parent
RUN = "RUN-20261011-PARK"


def cli() -> list[str]:
    return [sys.executable, PROGRAM, "--run", RUN, "--actor", "gov-001"]


def load(node: str) -> dict:
    result = subprocess.run(cli() + ["status", "--node", node], capture_output=True, text=True, cwd=ROOT)
    if result.returncode != 0:
        raise SystemExit(result.stderr or result.stdout)
    text = result.stdout
    marker = f'"id": "{node}"'
    start = text.rfind("{", 0, text.find(marker))
    return json.loads(text[start:])


def emit(node: str, event: str, body: dict) -> None:
    body = dict(body)
    body["node"] = node
    body["expected_revision"] = int(load(node)["revision"])
    path = OUT / f"_tmp_park_{node}_{event.replace('.', '_')}.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    result = subprocess.run(
        cli() + ["event", event, "--payload-file", str(path)],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    print(node, event, result.returncode, (result.stdout or "").strip(), (result.stderr or "").strip()[-400:])
    if result.returncode != 0:
        raise SystemExit(1)


def main() -> None:
    emit("N-0075", "node.lease.acquire", {"ttl_seconds": 7200})
    emit(
        "N-0075",
        "node.blocker.open",
        {
            "id": "BL-N0075-SMTP",
            "type": "environment",
            "ref": "apps/api/.env",
            "note": (
                "2026-10-11: invite not sent. apps/api/.env has no CIP_MAILBOX_IMAP_USER, "
                "no CIP_MAILBOX_IMAP_PASSWORD, and CIP_SHIPPING_MAILER_SEND is off. "
                "The digest sender is intended to be warren.eliason@gmail.com via smtp.gmail.com:587. "
                "issue_invite was not called, so no set-password link was burned. "
                "15 historical email deliveries exist in report_delivery; this process cannot send."
            ),
            "release_lease": True,
        },
    )
    emit("N-0086", "node.lease.acquire", {"ttl_seconds": 7200})
    emit(
        "N-0086",
        "node.stage_note",
        {
            "note": (
                "Criterion 3 still waits on N-0075. Placeholder passwords on admin@local and viewer@local "
                "were not retired: those addresses cannot receive mail, and retiring them would lock Local Admin out. "
                "Do not call issue_invite until the Gmail app password is in apps/api/.env and send is on."
            )
        },
    )
    emit("N-0086", "node.lease.release", {})
    for node, note in (
        (
            "N-0078",
            "Not built. D-0062 is not in DECISIONS.md. Recommended checks are in .eif/audit/PROGRAMME_20261007/N0078_PROPOSAL.md. "
            "Depends on N-0076 and N-0085, which are still proposed. Quality lens is still the planned empty state.",
        ),
        (
            "N-0079",
            "Not built. D-0059 is not in DECISIONS.md. Sketch is .eif/audit/PROGRAMME_20261007/N0079_PROPOSAL.md. "
            "Do not apply a budget migration to cip before a clone proof. Role cip is not table owner. Next down_revision is 20261011_0032.",
        ),
    ):
        emit(node, "node.lease.acquire", {"ttl_seconds": 7200})
        emit(node, "node.stage_note", {"note": note})
        emit(node, "node.lease.release", {})
    print("parked", load("N-0075").get("status"), load("N-0086").get("status"))


if __name__ == "__main__":
    main()
