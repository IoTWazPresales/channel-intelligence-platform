"""N-0096: record baseline, evidence, findings, quality and verification through program.py.

usage: python close_n0096.py impl | finish | ver | n0110     (each event is one program.py call; payload files kept beside this script)
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
NODE = "N-0096"
IMPL = "RUN-20261015-N0096-IMPL"
VER = "RUN-20261015-N0096-VER"
REL = ".eif/audit/PROGRAMME_20261015/n0096/"
PROOF = REL + "N0096_PROOF.md"
RLS_PROOF = REL + "N0096_RLS_CLONE_PROOF.md"
BASELINE = REL + "BASELINE.md"

API_COUNTS = "2977 passed, 21 skipped, 0 failed"
WEB_DONE = (HERE / "web_counts.txt").exists()
WEB_COUNTS = (
    open(HERE / "web_counts.txt", encoding="utf-8").read().strip()
    if WEB_DONE
    else "NOT COMPLETE (run 1: 852 passed, 8 failed, all 8 stale tests since fixed; the 3 fixed files re-ran 47 passed; "
    "the final full run was stopped by memory pressure and has not been repeated)"
)


def cli(run: str) -> list[str]:
    return [sys.executable, str(ROOT / ".eif/runtime/programme/program.py"), "--run", run, "--actor", "gov-001"]


def revision(run: str, node: str) -> int:
    result = subprocess.run(cli(run) + ["status", "--node", node], capture_output=True, text=True, cwd=ROOT)
    if result.returncode != 0:
        raise SystemExit(result.stderr or result.stdout)
    text = result.stdout
    start = text.rfind("{", 0, text.find(f'"id": "{node}"'))
    return int(json.loads(text[start:])["revision"])


def emit(run: str, event: str, body: dict, *, node: str = NODE, tag: str = "") -> None:
    body = dict(body)
    body["node"] = node
    body["expected_revision"] = revision(run, node)
    path = HERE / f"_cl_{node}_{event.replace('.', '_')}{tag}.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    result = subprocess.run(cli(run) + ["event", event, "--payload-file", str(path)], capture_output=True, text=True, cwd=ROOT)
    print(run, node, event, tag, result.returncode, (result.stdout or "").strip(), (result.stderr or "").strip()[-600:], flush=True)
    if result.returncode != 0:
        raise SystemExit(1)


def impl() -> None:
    emit(IMPL, "node.lease.acquire", {"ttl_seconds": 3600}, tag="_impl")
    emit(
        IMPL,
        "baseline.add",
        {
            "id": "BLN-N0096",
            "provenance": "implementation-observation",
            "tree_hash": "ebf6f9ea",
            "path": BASELINE,
            "observed_behavior": (
                "Full API pytest on cip_test: 20 failed and 34 errors. Two clone-dependent fixtures rewrote os.environ for a "
                "database that no longer exists and never restored it, so every later DB test failed. Eight web vitest tests failed on copy changes."
            ),
            "latent_capabilities": [],
            "preservation": {},
        },
        tag="_bln",
    )
    emit(IMPL, "node.baseline", {"baseline_ref": "BLN-N0096"}, tag="_bln")
    emit(IMPL, "node.stage", {"to": "implement", "stage_note": "Baseline recorded. Fixing failures by class: stale test, product bug, or missing named database."}, tag="_impl")
    for path, note in (
        ("apps/api/app/services/cpor/fx_rate.py", "N-0096 (4c25474e): the FX date is the approval date, always (D-0093); a stored rate up to 4 days older is accepted when the fetch fails; case_rate_date no longer reads the window start."),
        ("apps/api/alembic/versions/20261015_0040_stock_tables_rls_inline.py", "N-0096 (c3dba532): customer_stock_position and fact_customer_sellthrough_superseded move to the inline product-line policies. Clone proof, then cip and cip_test."),
        (RLS_PROOF, "N-0096 clone proof (cip_n0096, dropped): policies and row counts printed before and after; upgrade, downgrade, upgrade identical; 701 positions and 390 superseded rows unchanged."),
        ("apps/api/tests/test_cpor_settle_confirm_clone.py", "N-0096: the settle test runs on cip_test and seeds and deletes its own cases; no longer rewrites os.environ."),
        ("apps/api/tests/test_lineup_distributor_as_customer_remediation.py", "N-0096 (BACKLOG-144): four tests seed their own distributor, case and lines in a rolled-back transaction."),
        ("apps/api/tests/test_product_line_rls_parity_n0065_db.py", "N-0096: needs 0027 applied, not to be the head; counts 42 protected tables; append-only tables checked for SELECT+INSERT policies; no exemption."),
        ("apps/api/tests/test_cst_takealot_week_shape.py", "N-0096 Part B: pins that a one-week Takealot file with a month-end split lands in its one week."),
        ("apps/api/tests/test_rbac_n0038_cpor_roles.py", "N-0096: approval-link routes in the matrix; the one public approval route allowed by name, not by loosening the rule."),
        (PROOF, f"N-0096 proof: full API pytest on cip_test {API_COUNTS}; web vitest {WEB_COUNTS}; web tsc exit 0; eslint 0 errors on the three changed files."),
    ):
        emit(IMPL, "evidence.add", {"path": path, "note": note, "provenance": "implementation-observation"}, tag="_" + Path(path).stem[:40])
    findings = (
        "N-0096: BACKLOG-099 (live API in GitHub Actions) DEFERRED by Warren 2026-10-15. Trigger: before a second developer pushes or before main promotion. Recorded in docs/BACKLOG.md. .github was not touched.",
        "N-0096: BACKLOG-121 (non-split sheets: preview row_count from parser #1 vs apply parser #2) is product work, not test seeding, and no test refers to it. Limitation: the acceptance wording 'non-split-sheet tests' is not met by a test change; the bulk-backfill integration tests are marked integration and skip when the cip_bulk_smoke clone is absent.",
        "N-0096: 21 tests skip on cip_test with a logged reason each (live cip data, ALLOW_TESTS_ON_DEV_DB, remote Supabase, the cip_bulk_smoke clone, migration 0048 fixtures, session-mode e2e). Skips are not failures but they are not run.",
        "N-0096: no Python linter (ruff) is installed in apps/api/.venv. The acceptance criteria call for tsc and eslint only, so none was installed; API changes were not linted.",
        "N-0096: cip holds eight 'RelAmazon ...' customers (C-REL-A/B-*, ids 5195 to 5259) that look like test fixtures from a run against cip. Not touched. Needs a decision before the Amazon history upload picks a customer.",
        "N-0096: the full web vitest run takes about 27 minutes on this machine with the stack running (setup 2017 s of 1604 s wall); not investigated.",
    )
    for i, note in enumerate(findings, 1):
        emit(IMPL, "finding.defer", {"note": note, "code": "DOES_NOT_FIT"}, tag=f"_{i}")
    if not WEB_DONE:
        emit(
            IMPL,
            "node.stage_note",
            {"stage_note": f"N-0096 IN PROGRESS, NOT CLOSED. API full pytest on cip_test {API_COUNTS}. Web full vitest: {WEB_COUNTS}. Quality and verification not recorded until a full web run is green."},
            tag="_partial",
        )
        emit(IMPL, "node.lease.release", {}, tag="_partial")
        return
    emit(IMPL, "node.stage", {"to": "validate", "stage_note": "Fixes made and committed. Full suites run on cip_test."}, tag="_val")
    for dim, state, path, summary in (
        ("testing", "pass", PROOF, f"Full API pytest on cip_test {API_COUNTS} from a fresh run; full web vitest {WEB_COUNTS}; web tsc exit 0; eslint 0 errors on changed files."),
        ("observability", "pass", PROOF, "Every skip carries its reason in the pytest output; the integration marker is registered."),
    ):
        emit(IMPL, "node.quality", {"dim": dim, "state": state, "evidence": {"path": path, "summary": summary[:200]}, "rationale": summary}, tag="_" + dim)
    emit(IMPL, "node.stage_note", {"stage_note": f"N-0096 built. API {API_COUNTS}; web {WEB_COUNTS}. Verification is a different run."}, tag="_impl")
    emit(IMPL, "node.lease.release", {}, tag="_impl")


def finish() -> None:
    """After impl() left the node in progress: stage validate, quality, stage note. Needs web_counts.txt."""
    assert WEB_DONE, "web_counts.txt missing"
    emit(IMPL, "node.lease.acquire", {"ttl_seconds": 3600}, tag="_fin")
    emit(IMPL, "node.stage", {"to": "validate", "stage_note": "Fixes made and committed. Full API and full web suites green on cip_test."}, tag="_val")
    for dim, state, path, summary in (
        ("testing", "pass", PROOF, f"Full API pytest on cip_test {API_COUNTS} from a fresh run; full web vitest {WEB_COUNTS}; web tsc exit 0; eslint 0 errors on changed files."),
        ("observability", "pass", PROOF, "Every skip carries its reason in the pytest output; the integration marker is registered."),
    ):
        emit(IMPL, "node.quality", {"dim": dim, "state": state, "evidence": {"path": path, "summary": summary[:200]}, "rationale": summary}, tag="_" + dim)
    emit(IMPL, "node.stage_note", {"stage_note": f"N-0096 built. API {API_COUNTS}; web {WEB_COUNTS}. Verification is a different run."}, tag="_fin")
    emit(IMPL, "node.lease.release", {}, tag="_fin")


def ver() -> None:
    emit(VER, "node.lease.acquire", {"ttl_seconds": 3600}, tag="_ver")
    emit(VER, "node.verification", {"kind": "behavioral", "state": "pass", "evidence": PROOF}, tag="_b")
    emit(VER, "node.verification", {"kind": "referent", "state": "pass", "evidence": PROOF, "path": "apps/api/tests/test_cpor_settle_confirm_clone.py"}, tag="_r")
    emit(
        VER,
        "node.stage_note",
        {
            "stage_note": (
                f"VERIFIED_WITH_LIMITATIONS. Self-verified under {VER}, different from build run {IMPL}; same session, same model, not independent. N-0099 does the second look. "
                f"Full API pytest on cip_test {API_COUNTS}; full web vitest {WEB_COUNTS}; web tsc exit 0. "
                "Limits: BACKLOG-099 (live API in CI) deferred by Warren, trigger before a second developer pushes or before main promotion; "
                "BACKLOG-121 is product work and is not met by a test change; 21 tests skip with logged reasons; no Python linter installed. "
                "Operator acceptance pending."
            )
        },
        tag="_ver",
    )
    emit(VER, "node.lease.release", {}, tag="_ver")


def n0110() -> None:
    emit(IMPL, "node.lease.acquire", {"ttl_seconds": 3600}, node="N-0110", tag="_f")
    notes = (
        (
            "N-0110 Part B finding (Takealot one-week misread): the 'two months' in repair 2 are not a second period. Every Takealot file has ONE "
            "Transaction Week (the Monday) and a Transaction Month column. When the week crosses a month end, each product that sold on both sides "
            "appears twice in the same week, once per calendar month, each row holding that month's share (cip loads 1648 Jul 427 + Aug 28 = 455; "
            "1650 Dec 111 + Jan 108; 1651 Mar 70 + Apr 115; 1652 Jun 102 + Jul 184; 1649 has no split). Barcode and stock repeat on both halves "
            "(28 of 28 products in both halves carry the same stock). The parser dates every row by Transaction Week (mapping Transaction Week -> period): "
            "5 loads, 5 periods, grain week. The old 'last row wins' dropped one half; repair 2 sums the halves (Takealot 541 -> 1,253 units, which is every resolved staging unit of the 5 loads). "
            "No parser or period fix was needed; a test now pins the shape (test_cst_takealot_week_shape.py). Stored Takealot rows on cip are right "
            "for their week: 96 rows, 5 weeks, 100% of resolved units; 29 unresolved rows (30 units) in loads 1648, 1650, 1652 are product matches, not periods. "
            "Nothing was changed on cip."
        ),
        (
            "N-0110 Part B finding (history upload paths, read-only): Takealot (customer 20) -> customer sell-through; Amazon -> customer sell-through; "
            "Pinnacle -> distributor sales/inventory (it is distributor 29 with 5,704 sell-out rows, 344 periods to 2026-06-12, and 13,784 inventory rows, 75 dates "
            "to 2026-06-08; customer 295 Pinnacle has no data). WOULD BREAK: (1) customer sell-through supersedes whole rows by customer, product and period, so a "
            "sales file then a separate stock file for the same week (Amazon style) cannot both load: a stock-only file is refused (units_sold required) and a "
            "later sales-only file would replace the on-hand of the earlier one; sales and stock need one workbook (the companion soh sheet) or a measure-wise merge. "
            "(2) Amazon has two customers (26 provisional TMP-CUST 'Amazon', 299 'Amazon Commercial Services (South Africa)') and eight RelAmazon test customers; the history "
            "must land on one. (3) A file whose period is only a week number takes the year from the latest week started by the received date, so 2-year-old "
            "files without a date column land in the wrong year; Takealot is safe (Transaction Week is a date), Amazon and Pinnacle formats are unseen. "
            "(4) Amazon weeks may run Sunday to Saturday; no week calendar is set for Amazon or Pinnacle. (5) Weeks without on-hand break the expected-position chain "
            "(today 37 no-prior-on-hand and 58 unreported-weeks gaps). (6) Load order: a newer load supersedes older rows, so re-loading an old file after a newer one "
            "that covers the same week replaces it. (7) Not measured: cost of recomputing stock positions after each of ~100 loads per customer, and DSI "
            "supersession for Pinnacle. Nothing was built."
        ),
    )
    for i, note in enumerate(notes, 1):
        emit(IMPL, "finding.defer", {"note": note, "code": "DOES_NOT_FIT"}, node="N-0110", tag=f"_{i}")
    emit(IMPL, "node.lease.release", {}, node="N-0110", tag="_f")


if __name__ == "__main__":
    {"impl": impl, "finish": finish, "ver": ver, "n0110": n0110}[sys.argv[1]]()
