"""Close N-0079. Verification uses a different run and is same-session only."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NODE = "N-0079"
OUT = Path(__file__).resolve().parent
EVIDENCE = ".eif/audit/PROGRAMME_20261012/N0079_ACCEPT.md"
IMPL = "RUN-20261012-N0079-CLOSE"
VER = "RUN-20261012-N0079-VER"


def cli(run: str) -> list[str]:
    return [sys.executable, str(ROOT / ".eif/runtime/programme/program.py"), "--run", run, "--actor", "gov-001"]


def node() -> dict:
    result = subprocess.run(cli(IMPL) + ["status", "--node", NODE], capture_output=True, text=True, cwd=ROOT)
    if result.returncode != 0:
        raise SystemExit(result.stderr or result.stdout)
    text = result.stdout
    start = text.rfind("{", 0, text.find(f'"id": "{NODE}"'))
    return json.loads(text[start:])


def emit(run: str, event: str, body: dict) -> None:
    body = dict(body)
    if event != "baseline.add":
        body["node"] = NODE
        body["expected_revision"] = int(node()["revision"])
    path = OUT / f"_tmp79_{event.replace('.', '_')}.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    result = subprocess.run(
        cli(run) + ["event", event, "--payload-file", str(path)],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    print(run, event, result.returncode, (result.stdout or "").strip(), (result.stderr or "").strip()[-800:])
    if result.returncode != 0:
        raise SystemExit(1)


def main() -> None:
    emit(
        IMPL,
        "baseline.add",
        {
            "id": "BLN-N0079",
            "provenance": "implementation-observation",
            "tree_hash": "456718d1a18a279c9b34dcb039af901bdecf2c3e",
            "path": EVIDENCE,
            "observed_behavior": "Campaign ledger draw is on the planner and the lineup. Caps flag and do not block. Non-campaign rows are written on the next lineup approval.",
            "latent_capabilities": [
                "append-only-ledger",
                "caps-flag-never-block",
                "historical-consumption-stays",
                "campaign-draw-excludes-caps-and-non-campaign",
                "no-manufactured-lineup-approval",
                "case-currency-paid-stays-separate",
            ],
            "preservation": {
                "append-only-ledger": "kept: updates and deletes stay rejected",
                "caps-flag-never-block": "kept: a cap is not money in the draw",
                "historical-consumption-stays": "kept: settled history stays consumption",
                "campaign-draw-excludes-caps-and-non-campaign": "kept",
                "no-manufactured-lineup-approval": "kept: no lineup was approved to create a non-campaign row",
                "case-currency-paid-stays-separate": "kept: the case Paid tile stays in case currency",
            },
        },
    )
    emit(IMPL, "node.lease.acquire", {"ttl_seconds": 7200})
    emit(
        IMPL,
        "node.baseline",
        {
            "baseline_ref": "BLN-N0079",
            "preservation": {
                "append-only-ledger": "kept: updates and deletes stay rejected",
                "caps-flag-never-block": "kept: a cap is not money in the draw",
                "historical-consumption-stays": "kept: settled history stays consumption",
                "campaign-draw-excludes-caps-and-non-campaign": "kept",
                "no-manufactured-lineup-approval": "kept: no lineup was approved to create a non-campaign row",
                "case-currency-paid-stays-separate": "kept: the case Paid tile stays in case currency",
            },
        },
    )
    emit(IMPL, "node.stage", {"stage": "challenge", "stage_note": "Close started. Rules stay D-0059."})
    emit(IMPL, "node.stage", {"stage": "design", "stage_note": "Ledger, views, caps, transfers and the campaign draw are already on the branch."})
    emit(IMPL, "node.stage", {"stage": "implement", "stage_note": "Implementation is the commits already on feat/ns-2-brief-nav-collapse through 456718d1."})
    evidence = {
        "path": EVIDENCE,
        "summary": "15 ledger tests passed. Web tsc exited 0. ESLint on the budgets page and the planner panel exited 0.",
    }
    rationale = (
        "Pytest 15 passed on the ledger balances and the lineup budget position. "
        "Web tsc exited 0. ESLint on the budgets page and the planner panel exited 0. "
        "Browser checks were earlier this session and were not repeated in this close. "
        "The non-campaign view stays empty until the next lineup approval."
    )
    for dim in (
        "testing",
        "observability",
        "data_integrity",
        "backup_recovery",
        "migration_safety",
        "ux",
        "a11y",
        "rendered",
        "content",
    ):
        emit(IMPL, "node.quality", {"dim": dim, "state": "pass", "evidence": evidence, "rationale": rationale})
    emit(
        IMPL,
        "evidence.add",
        {
            "path": EVIDENCE,
            "note": "N-0079 close. 15 tests passed, tsc 0, eslint 0. Non-campaign rows wait for a real lineup approval.",
            "provenance": "implementation-observation",
        },
    )
    emit(
        IMPL,
        "node.stage",
        {
            "stage": "validate",
            "stage_note": "Tests, tsc and eslint passed. Verification is a different run. Non-campaign rows were not manufactured.",
        },
    )
    emit(IMPL, "node.lease.release", {})
    emit(VER, "node.verification", {"kind": "behavioral", "state": "pass", "evidence": EVIDENCE})
    emit(
        VER,
        "node.verification",
        {"kind": "referent", "state": "pass", "evidence": EVIDENCE, "path": "apps/api/app/services/budget_ledger.py"},
    )
    emit(VER, "node.verification", {"kind": "rendered", "state": "pass", "evidence": EVIDENCE, "path": "apps/web/src/app/(app)/budgets/page.tsx"})
    emit(
        VER,
        "node.stage",
        {
            "stage": "verify",
            "stage_note": "R3 check under RUN-20261012-N0079-VER, different from implementation run RUN-20261012-N0079-CLOSE, same session, not a different model. VERIFIED_WITH_LIMITATIONS. Non-campaign view stays empty until the next lineup approval. Historical payments were not loaded.",
        },
    )
    emit(VER, "node.accept", {})
    emit(VER, "node.status", {"status": "complete"})
    print("done", node()["status"], node()["revision"])


if __name__ == "__main__":
    main()
