"""N-0083: record baseline, evidence, decision, findings, quality and verification through program.py.

usage: python close_n0083.py impl | ver     (each event is one bare program.py call; payload files are kept beside this script)
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
NODE = "N-0083"
IMPL = "RUN-20261015-N0083-IMPL"
VER = "RUN-20261015-N0083-VER"
REL = ".eif/audit/PROGRAMME_20261015/n0083/"
PROOF = REL + "N0083_PROOF.md"
BASELINE = REL + "BASELINE.md"
COMMIT = "5104f59c"

MIGRATION = "apps/api/alembic/versions/20261015_0039_fx_rate_grants_and_provenance.py"
SERVICE = "apps/api/app/services/cpor/fx_rate.py"
DB_TEST = "apps/api/tests/test_fx_case_rate_db.py"
UNIT_TEST = "apps/api/tests/test_cpor_fx_rate.py"
WEB = "apps/web/src/features/promotions-funding/PlanWorkspace.tsx"


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
    path = HERE / f"_ev_{event.replace('.', '_')}{tag}.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    result = subprocess.run(cli(run) + ["event", event, "--payload-file", str(path)], capture_output=True, text=True, cwd=ROOT)
    print(run, event, tag, result.returncode, (result.stdout or "").strip(), (result.stderr or "").strip()[-600:], flush=True)
    if result.returncode != 0:
        raise SystemExit(1)


def last_decision_id() -> str:
    text = (ROOT / ".eif/program/PROGRAM.yaml").read_text(encoding="utf-8")
    return max(re.findall(r"\bid: (D-\d{4})\b", text))


def impl() -> None:
    emit(IMPL, "node.lease.acquire", {"ttl_seconds": 3600}, tag="_impl")
    emit(
        IMPL,
        "baseline.add",
        {
            "id": "BLN-N0083",
            "provenance": "implementation-observation",
            "tree_hash": "51bdc160",
            "path": BASELINE,
            "observed_behavior": (
                "fx_daily_rate is owned by postgres and cip has no privilege on it, so the poller stored nothing (0 rows on cip). "
                "Create booked today's fetched rate whatever the case dates were; approval never read the table; a booked draft's ROE could be overwritten by PATCH "
                "with no reason; the brief counted cases with no rate as FX blocked."
            ),
            "latent_capabilities": [],
            "preservation": {},
        },
        tag="_bln",
    )
    emit(IMPL, "node.baseline", {"baseline_ref": "BLN-N0083"}, tag="_bln")
    emit(IMPL, "node.stage", {"to": "implement", "stage_note": "Baseline recorded. Grant migration, case-date rate rule, override audit, FX blocked definition, approve dialog."}, tag="_impl")
    for path, note in (
        (MIGRATION, f"N-0083 ({COMMIT}): grants SELECT, INSERT, UPDATE on fx_daily_rate and sequence USAGE to cip; adds fx_booked_source, fx_booked_rate_date, fx_override_reason to cpor_case. Clone proof then cip."),
        (SERVICE, f"N-0083 ({COMMIT}): rate_for_case_date (stored first, fetch only when none stored), book_on_approve fixes the rate at first approval, manual override needs a reason, reapproval keeps the rate, persisted flag on a fetched rate."),
        (DB_TEST, "N-0083: 13 DB tests on cip_test: app role privileges, fetch stores and updates, failed fetch stores nothing, poller stores, case-date and weekend lookup, no stale substitute, create/approve/override/never-revisited."),
        (PROOF, "N-0083 proof: clone cip_n0083 reproduced the denial and the fix with a clean round trip; cip applied; the poller stored USDZAR 16.47 for 2026-10-14 on cip."),
    ):
        emit(IMPL, "evidence.add", {"path": path, "note": note, "provenance": "implementation-observation"}, tag="_" + Path(path).stem)
    emit(
        IMPL,
        "decision.add",
        {
            "scope": NODE,
            "origin": "implementation",
            "status": "proposed",
            "statement": (
                "How N-0083 reads Warren's settled FX rules where they leave a choice (N-0083). Built: (1) 'the case's own date' is the window start, or today when the window "
                "has not started; (2) a stored rate for a past date may be up to 4 days older than the date (weekend, bank holiday), otherwise one ECB fetch for the date is stored; "
                "(3) a manual rate that differs from the stored rate needs a reason, at approval and when a booked draft is edited; (4) create books the stored rate provisionally and "
                "approval books it again and fixes it; a rate chosen at create or carried from an import is kept, not replaced; (5) reapproval keeps the fixed rate and refuses a new one; "
                "(6) 'FX blocked' counts cases with a rate and no mode, and cases with no rate are counted apart. Options: (a) as built; (b) case date = approval date; "
                "(c) no reason required for an override. Evidence: cip has 311 cases, 308 with a rate, 2 open cases with a rate and no mode, 0 with no rate; fx_daily_rate was empty. "
                "Assumption: window start is the date Warren means. Impact: (b) would book every late approval at the approval-day rate. Reversible: yes, provenance columns record the basis. "
                "Resolving experiment: Warren names one approved case and the date its rate should come from."
            ),
        },
        node_scoped=False,
    )
    did = last_decision_id()
    print("decision", did, flush=True)
    emit(IMPL, "node.blocker.open", {"id": "BL-N0083-CASEDATE", "type": "decision", "ref": did,
                                     "note": "Warren: confirm the case date is the window start, the reason rule, and the 4-day stored-rate gap."}, tag="_dec")
    for code, note in (
        ("DOES_NOT_FIT", "N-0083: the approve dialog and the plan's rate-basis line were not rendered in a browser (sign-in). ux, a11y and rendered stay pending."),
        ("DOES_NOT_FIT", "N-0083: cases already booked on cip have no booked source or rate date (shown as carried over with the case); nothing was backfilled."),
        ("DOES_NOT_FIT", "N-0083: pre-existing failures outside FX: test_promo_plan_builder (4, FakeSession lacks begin_nested, from budget_ledger.used_usd), test_rbac_n0038_cpor_roles (2, approval-link route), test_cpor_settle_confirm_clone (database cip_ns4_settle_clone gone; also breaks later modules in one run), PaymentEvidenceOverlay.test.tsx (1)."),
    ):
        emit(IMPL, "finding.defer", {"note": note, "code": code}, tag="_" + str(abs(hash(note)) % 1000))
    emit(IMPL, "node.stage", {"to": "validate", "stage_note": "Built and applied. Tests on cip_test, clone proof, cip apply, restart done."}, tag="_val")
    for dim, state, path, summary in (
        ("testing", "pass", DB_TEST, "pytest on cip_test: FX unit and endpoint tests 36, FX DB tests 13, brief 3; wider cpor set 210 passed. vitest promotions-funding 27 passed (1 unrelated failure). tsc exit 0. next lint clean on changed files."),
        ("observability", "pass", SERVICE, "A fetched rate the table refuses logs an error and returns persisted false; approval writes an fx_booked event; a PATCH override writes fx_override."),
        ("data_integrity", "pass", DB_TEST, "Proposed and booked stay in separate columns; a booked rate is fixed at first approval; an override carries a reason; no stale rate is substituted."),
        ("migration_safety", "pass", PROOF, "Clone cip_n0083: denial reproduced, upgrade, downgrade, upgrade identical; cases 311 and booked 308 unchanged; then cip."),
        ("backup_recovery", "pass", PROOF, "Additive migration; downgrade proven on the clone; no row rewritten."),
        ("content", "pass", WEB, "Dialog and basis wording reviewed in source and asserted in vitest; not rendered."),
    ):
        emit(IMPL, "node.quality", {"dim": dim, "state": state, "evidence": {"path": path, "summary": summary[:200]}, "rationale": summary}, tag="_" + dim)
    emit(IMPL, "node.stage_note", {"stage_note": f"N-0083 built ({COMMIT}), migration 0039 on cip, poller stored a rate on cip. Verification is a different run."}, tag="_impl")
    emit(IMPL, "node.lease.release", {}, tag="_impl")


def ver() -> None:
    emit(VER, "node.lease.acquire", {"ttl_seconds": 3600}, tag="_ver")
    emit(VER, "node.verification", {"kind": "behavioral", "state": "pass", "evidence": DB_TEST}, tag="_b")
    emit(VER, "node.verification", {"kind": "referent", "state": "pass", "evidence": PROOF, "path": SERVICE}, tag="_r")
    emit(
        VER,
        "node.stage_note",
        {
            "stage_note": (
                f"VERIFIED_WITH_LIMITATIONS. Self-verified under {VER}, different from build run {IMPL}; same session, same model, not independent. N-0099 does the second look. "
                "Poller wrote USDZAR 16.47 (2026-10-14) to fx_daily_rate on cip after migration 0039. A case rate is the stored rate for its date or an override with a reason, fixed at first approval. "
                "Limits: approve dialog and basis line not rendered (sign-in; ux, a11y, rendered pending); existing booked cases have no source recorded; unrelated test failures listed in the deferred findings. "
                "Warren to confirm the case date (window start), the reason rule and the 4-day gap (decision blocker). Operator acceptance pending."
            )
        },
        tag="_ver",
    )
    emit(VER, "node.lease.release", {}, tag="_ver")


if __name__ == "__main__":
    {"impl": impl, "ver": ver}[sys.argv[1]]()
