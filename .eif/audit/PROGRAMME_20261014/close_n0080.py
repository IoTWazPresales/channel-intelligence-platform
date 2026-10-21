"""N-0080: implement run through validate, then a different run for verification. No accept, no complete."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NODE = "N-0080"
OUT = Path(__file__).resolve().parent
PROOF = ".eif/audit/PROGRAMME_20261014/N0080_CLONE_PROOF.md"
DEF = "apps/api/app/services/profit_definition.py"
CPOR = "apps/api/app/services/cpor/case_margin.py"
PANEL = "apps/web/src/features/promotions-funding/CaseMarginPanel.tsx"
TESTS = "apps/api/tests/test_profit_definition.py"
DBTEST = "apps/api/tests/test_cpor_case_margin_db.py"
VTEST = "apps/web/src/features/promotions-funding/CaseMarginPanel.test.tsx"


def cli(run: str) -> list[str]:
    return [sys.executable, str(ROOT / ".eif/runtime/programme/program.py"), "--run", run, "--actor", "gov-001"]


def revision(run: str) -> int:
    result = subprocess.run(cli(run) + ["status", "--node", NODE], capture_output=True, text=True, cwd=ROOT)
    if result.returncode != 0:
        raise SystemExit(result.stderr or result.stdout)
    text = result.stdout
    start = text.rfind("{", 0, text.find(f'"id": "{NODE}"'))
    return int(json.loads(text[start:])["revision"])


def emit(run: str, event: str, body: dict, *, node_scoped: bool = True, tag: str = "") -> None:
    body = dict(body)
    if node_scoped:
        body["node"] = NODE
        body["expected_revision"] = revision(run)
    path = OUT / f"_n0080_{event.replace('.', '_')}{tag}.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    result = subprocess.run(cli(run) + ["event", event, "--payload-file", str(path)], capture_output=True, text=True, cwd=ROOT)
    print(run, event, result.returncode, (result.stdout or "").strip(), (result.stderr or "").strip()[-500:])
    if result.returncode != 0:
        raise SystemExit(1)


def main() -> None:
    impl = "RUN-20261014-N0080-IMPL"
    ver = "RUN-20261014-N0080-VER"
    emit(impl, "node.lease.acquire", {"ttl_seconds": 7200})
    emit(
        impl,
        "baseline.add",
        {
            "id": "BLN-N0080",
            "provenance": "implementation-observation",
            "tree_hash": "5bce9b1c",
            "path": "apps/api/app/services/commercial_planner/lineup_pricing.py",
            "observed_behavior": (
                "Lineup profit was DAP minus PM controlled cost. Planner GP was distributor net minus controlled "
                "cost, and distributor net took the distributor margin off twice. CPOR showed no company margin. "
                "No landed cost was stored anywhere."
            ),
            "latent_capabilities": ["lineup-price-chain", "planner-reserves", "cpor-support-waterfall"],
            "preservation": {
                "lineup-price-chain": "kept: SRP to DAP chain and stored lineup profit numbers unchanged",
                "planner-reserves": "kept: reserve pool and split math unchanged",
                "cpor-support-waterfall": "kept: case lines are not written; margin is a read",
            },
        },
        node_scoped=False,
    )
    emit(
        impl,
        "node.baseline",
        {
            "baseline_ref": "BLN-N0080",
            "preservation": {
                "lineup-price-chain": "kept: SRP to DAP chain and stored lineup profit numbers unchanged",
                "planner-reserves": "kept: reserve pool and split math unchanged",
                "cpor-support-waterfall": "kept: case lines are not written; margin is a read",
            },
        },
    )
    emit(impl, "node.stage", {"stage": "discovery", "stage_note": "Spec 9 item 3. Two profit formulas found (lineup chain, planner calculator). CPOR had none. No landed cost data."}, tag="_1")
    emit(impl, "node.stage", {"stage": "challenge", "stage_note": "Warren D-0052: headline margin is PM controlled cost; DAP and landed cost beside it, never folded in. Planner GP used distributor net, which double-deducts the distributor margin."}, tag="_2")
    emit(impl, "node.stage", {"stage": "design", "stage_note": "One pure function (profit_definition.compute_profit). Lineup, planner and CPOR read it. Landed cost is an optional SKU field in the controlled cost currency."}, tag="_3")
    emit(impl, "node.stage", {"stage": "implement", "stage_note": "Product commit 9fda9893. 20261014_0036 on cip after clone proof."}, tag="_4")
    emit(
        impl,
        "decision.add",
        {
            "scope": NODE,
            "origin": "implementation",
            "status": "proposed",
            "statement": (
                "Planner line margin now starts from OEM sell-in (the DAP) minus PM controlled cost, less reserves. "
                "Before, it started from distributor net, which took the distributor margin off a second time. "
                "Plan totals rise by sell-in x distributor margin x units. Stored plan lines keep their old figure "
                "until the line is recalculated; nothing was rewritten. Reversible: one line in calculator.py."
            ),
        },
        node_scoped=False,
        tag="_1",
    )
    emit(
        impl,
        "decision.add",
        {
            "scope": NODE,
            "origin": "implementation",
            "status": "proposed",
            "statement": (
                "CPOR case margin derives DAP from the line SRP, VAT and dealer margin with the customer rebate and "
                "distributor margin from trade terms, divided by the case ROE (USD). A missing term is used as 0 and "
                "flagged on the line; a SKU cost not in USD gives no margin and is flagged, never converted."
            ),
        },
        node_scoped=False,
        tag="_2",
    )
    for path, note in (
        (DEF, "N-0080 one profit definition: margin vs PM controlled cost; DAP and landed cost beside it."),
        (CPOR, "N-0080 CPOR case margin read (GET /api/v1/cpor/cases/{id}/margin). Case 223 on cip: 1837.33 USD over 5 of 9 lines."),
        (PROOF, "N-0080 clone proof of 20261014_0036 on cip_n0080, then applied to cip. sku_rows 31 and cost sum 17602.0 unchanged."),
        (PANEL, "N-0080 Margin vs PM controlled cost panel on the plan workspace."),
    ):
        emit(impl, "evidence.add", {"path": path, "note": note, "provenance": "implementation-observation"}, tag="_" + Path(path).stem)
    tests = "pytest 131 passed on touched areas (cip_test, incl. 3 DB tests); vitest 131 passed on touched files; web tsc exit 0; next lint 0 errors on changed files."
    dims = (
        ("testing", "pass", TESTS, tests),
        ("observability", "pass", CPOR, "Read-only path. Every missing figure is a named flag on the line (no cost, no term, cost not USD, no ROE), shown in words on the panel. No new job or write to log."),
        ("ux", "pass", PANEL, "Headline names its basis. Per line: units, DAP, PM controlled cost, support, margin, margin total, landed cost (Not recorded when empty), notes in words. Lineup columns and planner waterfall renamed to the same words."),
        ("a11y", "pass", PANEL, "Semantic table with column and row headers and an aria-label; landed cost input is labelled with helper text. Component tests query by role. No axe run."),
        ("content", "pass", DEF, "Labels: Margin vs PM controlled cost; DAP, price to distributor; PM controlled cost; Landed cost (not in margin). Old Internal GP and Profit total labels replaced."),
    )
    for dim, state, path, rationale in dims:
        emit(impl, "node.quality", {"dim": dim, "state": state, "evidence": {"path": path, "summary": rationale[:200]}, "rationale": rationale}, tag="_" + dim)
    emit(
        impl,
        "node.quality",
        {
            "dim": "rendered",
            "rationale": "UNABLE_TO_RENDER in the browser: /promotions?plan=223 on 127.0.0.1:3000 opened the sign-in form and no account password may be entered by the agent. Web build b2QCbedv2c--6me-VJRcg is live; /api/v1/cpor/cases/223/margin answers 401 without a session. Component tests cover the panel.",
        },
        tag="_rendered",
    )
    emit(impl, "node.stage", {"stage": "validate", "stage_note": "Built and tested. Rendered check blocked by sign-in. Verification is a different run."}, tag="_5")
    emit(impl, "node.lease.release", {})
    emit(ver, "node.lease.acquire", {"ttl_seconds": 3600}, tag="_ver")
    emit(ver, "node.verification", {"kind": "behavioral", "state": "pass", "evidence": TESTS}, tag="_b")
    emit(ver, "node.verification", {"kind": "referent", "state": "pass", "evidence": DBTEST, "path": CPOR}, tag="_r")
    emit(
        ver,
        "node.stage",
        {
            "stage": "verify",
            "stage_note": (
                "VERIFIED_WITH_LIMITATIONS. Self-verified under RUN-20261014-N0080-VER, different from implementation run "
                "RUN-20261014-N0080-IMPL; same session, same model, not independent. N-0099 does the second look. "
                "Limits: margin panel not rendered in the browser (sign-in); stored planner lines keep the old GP until "
                "recalculated; CPOR lines without customer rebate or distributor margin terms use 0 (flagged); no SKU has a "
                "landed cost yet; ruff not installed; full API suite has 19 failures and 10 errors in files this node does not "
                "touch. Operator acceptance pending."
            ),
        },
        tag="_6",
    )
    emit(ver, "finding.defer", {"note": "N-0080: planner lines stored before 9fda9893 keep the old GP (distributor-net base) until recalculated. No bulk recompute was run.", "code": "DOES_NOT_FIT"}, tag="_1")
    emit(ver, "finding.defer", {"note": "N-0080: full API suite on cip_test: 19 failed, 10 errors outside N-0080 files (platform_audit mock await, promo_plan_builder FakeSession.begin_nested, open-channel copy, seed data, settle-clone test leaves settings on a dropped clone DB).", "code": "DOES_NOT_FIT"}, tag="_2")
    emit(ver, "node.lease.release", {}, tag="_ver")
    print("done", revision(ver))


if __name__ == "__main__":
    main()
