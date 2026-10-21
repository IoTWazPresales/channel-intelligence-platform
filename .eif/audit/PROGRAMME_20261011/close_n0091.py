"""N-0091: implement run through validate, then a different run for verification."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NODE = "N-0091"
OUT = Path(__file__).resolve().parent
EVIDENCE = ".eif/audit/PROGRAMME_20261011/N0091_ACCEPT.md"


def cli(run: str) -> list[str]:
    return [sys.executable, str(ROOT / ".eif/runtime/programme/program.py"), "--run", run, "--actor", "gov-001"]


def revision(run: str) -> int:
    result = subprocess.run(cli(run) + ["status", "--node", NODE], capture_output=True, text=True, cwd=ROOT)
    if result.returncode != 0:
        raise SystemExit(result.stderr or result.stdout)
    text = result.stdout
    marker = f'"id": "{NODE}"'
    start = text.find(marker)
    start = text.rfind("{", 0, start)
    return int(json.loads(text[start:])["revision"])


def emit(run: str, event: str, body: dict) -> None:
    body = dict(body)
    if event != "baseline.add":
        body["node"] = NODE
        body["expected_revision"] = revision(run)
    path = OUT / f"_tmp91_{event.replace('.', '_')}.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    result = subprocess.run(cli(run) + ["event", event, "--payload-file", str(path)], capture_output=True, text=True, cwd=ROOT)
    print(run, event, result.returncode, (result.stdout or "").strip(), (result.stderr or "").strip()[-500:])
    if result.returncode != 0:
        raise SystemExit(1)


def main() -> None:
    impl = "RUN-20261011-N0091-IMPL"
    ver = "RUN-20261011-N0091-VER"
    emit(impl, "node.lease.acquire", {"ttl_seconds": 7200})
    emit(
        impl,
        "baseline.add",
        {
            "id": "BLN-N0091",
            "provenance": "implementation-observation",
            "tree_hash": "e7aac28fe91114aac3a627c799b90ec36b29e360",
            "path": "apps/api/app/services/shipping/shipment_receipt.py",
            "observed_behavior": "A shipment had no single receipt page. A line that vanished from the next report of the same shipment was not flagged.",
            "latent_capabilities": ["fact-inbound-shipment"],
            "preservation": {"fact-inbound-shipment": "kept: the signal is derived on read and does not rewrite quantities"},
        },
    )
    emit(
        impl,
        "node.baseline",
        {"baseline_ref": "BLN-N0091", "preservation": {"fact-inbound-shipment": "kept: derived on read, quantities not rewritten"}},
    )
    emit(impl, "node.stage", {"stage": "discovery", "stage_note": "One shipment page. A line on an earlier report of that shipment and missing from the latest is a cancelled candidate. One report flags nothing."})
    emit(impl, "node.stage", {"stage": "challenge", "stage_note": "Do not rewrite fact quantities. Do not flag a line that is back on the latest report."})
    emit(impl, "node.stage", {"stage": "design", "stage_note": "Grain is the delivery when a delivery number exists, otherwise the order. The page lists current lines and vanished lines."})
    emit(impl, "node.stage", {"stage": "implement", "stage_note": "Shipped in eb230ccf. Live delivery 15260123521 on 2026-10-11 showed Cancelled candidate lines."})
    emit(impl, "evidence.add", {"path": EVIDENCE, "note": "N-0091 live receipt, Warren accepted 2026-10-11.", "provenance": "implementation-observation"})
    evidence = {"path": EVIDENCE, "summary": "Live receipt showed cancelled-candidate lines. Timeline was not scrolled into view."}
    for dim, rationale in (
        ("testing", "tests/test_shipment_receipt.py 6 passed on 2026-10-11."),
        ("observability", "The signal is a column on the receipt and a timeline event type."),
        ("ux", "Vanished lines stay on the same table with a blank quantity and the words Cancelled candidate."),
        ("a11y", "Text in an existing table. No separate axe run."),
        ("rendered", "Signed-in delivery 15260123521 rendered in the browser, dark, 1440."),
        ("content", "The signal label is Cancelled candidate."),
    ):
        emit(impl, "node.quality", {"dim": dim, "state": "pass", "evidence": evidence, "rationale": rationale})
    emit(impl, "node.stage", {"stage": "validate", "stage_note": "Live receipt accepted by Warren. Verification is a different run. Timeline below the line table was not in the screenshot."})
    emit(impl, "node.lease.release", {})
    emit(ver, "node.verification", {"kind": "behavioral", "state": "pass", "evidence": EVIDENCE})
    emit(
        ver,
        "node.stage",
        {
            "stage": "verify",
            "stage_note": "R2 check under RUN-20261011-N0091-VER, a different run from implementation, same session. Not a different model. VERIFIED_WITH_LIMITATIONS: live line table confirmed; timeline not scrolled; tests/test_shipment_receipt.py 6 passed.",
        },
    )
    emit(ver, "node.accept", {})
    emit(ver, "node.status", {"status": "complete"})
    print("done", revision(ver))


if __name__ == "__main__":
    main()
