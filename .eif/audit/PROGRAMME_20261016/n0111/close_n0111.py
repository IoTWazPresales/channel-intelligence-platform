"""N-0111: record baseline, evidence, findings, quality and verification through program.py.

usage: python close_n0111.py impl | ver      (each event is one program.py call; payload files kept beside this script)
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
NODE = "N-0111"
IMPL = "RUN-20261016-N0111-IMPL"
VER = "RUN-20261016-N0111-VER"
REL = ".eif/audit/PROGRAMME_20261016/n0111/"
PROOF = REL + "N0111_PROOF.md"
CLONE = REL + "N0111_CLONE_PROOF.md"
API = "3017 passed, 21 skipped, 0 failed"
WEB = "186 files, 869 passed, 0 failed (2 workers)"
BUILD = "c_B7WPOyCpkf-0iS-Vpdv"


def cli(run: str) -> list[str]:
    return [sys.executable, str(ROOT / ".eif/runtime/programme/program.py"), "--run", run, "--actor", "gov-001"]


def node_state(run: str) -> dict:
    r = subprocess.run(cli(run) + ["status", "--node", NODE], capture_output=True, text=True, cwd=ROOT)
    if r.returncode != 0:
        raise SystemExit(r.stderr or r.stdout)
    t = r.stdout
    return json.loads(t[t.rfind("{", 0, t.find(f'"id": "{NODE}"')):])


def emit(run: str, event: str, body: dict, *, tag: str = "", node: bool = True) -> None:
    body = dict(body)
    if node:
        body["node"] = NODE
        body["expected_revision"] = int(node_state(run)["revision"])
    path = HERE / f"cl_{event.replace('.', '_')}{tag}.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    r = subprocess.run(cli(run) + ["event", event, "--payload-file", str(path)], capture_output=True, text=True, cwd=ROOT)
    print(run, event, tag, r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()[-600:], flush=True)
    if r.returncode != 0:
        raise SystemExit(1)


def lease(run: str, tag: str) -> None:
    if node_state(run).get("lease"):
        emit(run, "node.lease.release", {}, tag=f"_{tag}_stale")
    emit(run, "node.lease.acquire", {"ttl_seconds": 3600}, tag=f"_{tag}")


def impl() -> None:
    lease(IMPL, "impl")
    emit(IMPL, "baseline.add", {
        "id": "BLN-N0111", "provenance": "implementation-observation", "tree_hash": "977985ba", "path": REL + "BASELINE.md",
        "observed_behavior": "Sell-through apply replaced every figure (a sales-only reload emptied on-hand); stock-only files refused; "
                             "week numbers without a year took a guessed year; no tenant week calendar; the stock chain compared across weeks "
                             "with no on-hand; day rows counted as weeks.",
        "latent_capabilities": [], "preservation": {}}, tag="_bln", node=False)
    emit(IMPL, "node.baseline", {"baseline_ref": "BLN-N0111"}, tag="_bln")
    emit(IMPL, "node.stage", {"to": "implement", "stage_note": "Charter and Warren's six decisions recorded. Build the five rules for customer sell-through; compare Pinnacle."}, tag="_impl")
    for path, note in (
        ("apps/api/app/services/imports/customer_sell_through_supersede.py", "N-0111 (d61e5af0): figures superseded independently, same key and cross key; partial rows keep the rest; figures named on each superseded record."),
        ("apps/api/app/services/imports/customer_sell_through_apply.py", "N-0111 (d61e5af0): upsert replaces only carried figures (figure_import_jobs); stock-only lines apply; a job with an unconfirmed year applies nothing."),
        ("apps/api/app/services/imports/parsers/customer_sell_through_grain.py", "N-0111 (d61e5af0): confirmed year, year-guess log, year suggestion from names, tenant Monday-Sunday default."),
        ("apps/api/app/services/imports/customer_sell_through.py", "N-0111 (d61e5af0): files with week numbers and no confirmed year are held (cst_year_required); stock-only files need Stock only."),
        ("apps/api/app/services/channel_intelligence/customer_stock_gap.py", "N-0111 (d61e5af0): a Monday-Sunday week with no on-hand is a no_on_hand position; the chain restarts at the next on-hand."),
        ("apps/api/alembic/versions/20261016_0041_cst_figure_supersede.py", "N-0111: figure_import_jobs, superseded.figures, nullable on-hand, new statuses. Clone proof cip_n0111 then cip."),
        ("apps/api/tests/test_cst_figure_supersede_db.py", "N-0111: DB tests on cip_test: stock-only never wipes sales, sales-only never wipes stock, cross key, whole row, re-upload, year gate."),
        ("apps/api/tests/test_cst_history_upload_rules.py", "N-0111: parser tests: tenant calendar, day grain, confirmed year, guess log, suggestion, stock-only file."),
        ("apps/web/src/app/(app)/admin/imports/CstUploadOptions.tsx", "N-0111 (d7807c8b): Sales only / Stock only / Year of the week numbers + Year confirmed on both CST uploads."),
        ("apps/web/src/app/(app)/admin/cst-steward/CstStockGapSection.tsx", "N-0111 (d7807c8b): Flag reads No on-hand reported / Chain restarts; counts name the weeks."),
        (CLONE, "N-0111 clone proof: migration round trip equal; synthetic 2-year set per source; re-run of the whole set changed nothing; cip unchanged; then 0041 applied to cip with counts unchanged."),
        (PROOF, f"N-0111 proof: rules, Pinnacle comparison, findings. Full API pytest on cip_test {API}; full web vitest {WEB}."),
    ):
        emit(IMPL, "evidence.add", {"path": path, "note": note, "provenance": "implementation-observation"}, tag="_" + Path(path).stem[:40])
    findings = (
        "N-0111: a day column headed only 'Date' is not read as the sale date by the CST template; rows stage with no period, are not applied, and the job still reads completed with a warning. Working headers: Sale Date, Sales Date, Transaction Date, Date Sold. Found in the clone proof.",
        "N-0111: one confirmed year covers every week number in a file; a file running from week 52 into week 1 must be split.",
        "N-0111: newest upload wins per figure (D-0090 order): loading an older file after a newer one replaces the newer figures for the same weeks.",
        "N-0111: stock positions on cip were not recomputed (no cip data writes in this node); the restart rule shows after Recompute on the Stock gap tab.",
        "N-0111: confirming the year of an already-uploaded job is API-only (POST /api/v1/imports/jobs/{id}/cst-confirm-year); no screen button.",
        "N-0111 Pinnacle: DSI has no year guessing and no confirm-year path (lines need dates); sales and stock are separate tables (rules hold); a same-key reload overwrites units in place with no superseded table; no cross-key supersession, so a correction with new invoice numbers adds rows; the reconciliation chain is a different model (10 percent band) and was not changed. The Pinnacle proof used the real fact upsert from resolved staging lines, not the file parser or mapping workflow.",
        "N-0111: Compuspeed LTD (1152) and SYNTECH DISTRIBUTION (PTY) LTD (4145) remain merged into OPEN_CHANNEL on cip; Warren ruled they are not to be merged; undoing them needs its own go-ahead (cip data write).",
        "N-0111: UNABLE_TO_RENDER the upload options and the gap tab (sign-in); component tests cover both.",
        "N-0111: no Python linter in the API venv; Python changes not linted. Web tsc exit 0, next lint 0 errors on changed files.",
    )
    for i, note in enumerate(findings, 1):
        emit(IMPL, "finding.defer", {"note": note, "code": "DOES_NOT_FIT"}, tag=f"_{i}")
    emit(IMPL, "node.stage", {"to": "validate", "stage_note": f"Built (d61e5af0, d7807c8b, 5de2186f). Clone proof PASS; 0041 on cip; API and web restarted (web build {BUILD})."}, tag="_val")
    for dim, state, path, summary in (
        ("testing", "pass", PROOF, f"Full API pytest on cip_test {API}; full web vitest {WEB}; new DB tests for per-figure supersede and the year gate; parser tests; web tsc exit 0."),
        ("observability", "pass", "apps/api/app/services/imports/customer_sell_through_supersede.py", "Supersede logs rows, partial rows and figures per load; apply summary carries superseded_partial_rows and superseded_figures; held files record cst_year_required with the suggested year."),
        ("data_integrity", "pass", CLONE, "Clone: re-running the whole 2-year set changed no total for Amazon, Takealot or Pinnacle; replaced figures kept with the superseding load; nothing hard-deleted; cip counts unchanged by 0041."),
        ("backup_recovery", "pass", "apps/api/alembic/versions/20261016_0041_cst_figure_supersede.py", "Downgrade removes only the derived N-0111 positions and the new columns; proved on the clone with N-0111 positions present; positions rebuild with Recompute."),
        ("migration_safety", "pass", CLONE, "0041 additive: clone upgrade, downgrade, upgrade with every count equal; cip fact rows 3197, units 12394, on-hand 30832, superseded 390, positions 701, staging 46718 unchanged."),
        ("ux", "pass", "apps/web/src/app/(app)/admin/imports/CstUploadOptions.tsx", "Upload: Sales-only and Stock-only exclude each other; year pre-filled from names, used only when Year confirmed is ticked. Gap tab names weeks with no on-hand."),
        ("a11y", "pass", "apps/web/src/app/(app)/admin/imports/CstUploadOptions.test.tsx", "Every checkbox and the year field have a label and an accessible description; states are text, not colour. No axe run."),
        ("content", "pass", "apps/api/app/services/imports/customer_sell_through.py", "Messages name what is missing and what to tick: Stock only, Sales only, Year of the week numbers / Year confirmed."),
    ):
        emit(IMPL, "node.quality", {"dim": dim, "state": state, "evidence": {"path": path, "summary": summary[:200]}, "rationale": summary}, tag="_" + dim)
    emit(IMPL, "node.quality", {"dim": "rendered", "state": "pending", "evidence": None,
                                "rationale": "UNABLE_TO_RENDER: the admin screens need sign-in and the agent may not sign in. Component tests cover the upload options and the gap tab labels."}, tag="_rendered")
    emit(IMPL, "node.stage_note", {"stage_note": f"N-0111 built. API {API}; web {WEB}. Verification is a different run."}, tag="_impl")
    emit(IMPL, "node.lease.release", {}, tag="_impl")


def ver() -> None:
    lease(VER, "ver")
    emit(VER, "node.verification", {"kind": "behavioral", "state": "pass", "evidence": "apps/api/tests/test_cst_figure_supersede_db.py"}, tag="_b")
    emit(VER, "node.verification", {"kind": "referent", "state": "pass", "evidence": PROOF, "path": "apps/api/app/services/imports/customer_sell_through_supersede.py"}, tag="_r")
    emit(VER, "node.stage", {"to": "verify", "stage_note": f"Self-verification run {VER}."}, tag="_ver")
    emit(VER, "node.stage_note", {"stage_note": (
        f"VERIFIED_WITH_LIMITATIONS. Self-verified under {VER}, different from {IMPL}; same session, same model, not independent. N-0099 does the second look. "
        "Built for customer sell-through: per-figure supersession (stock-only never wipes sales, sales-only never wipes stock), stock-only files, "
        "confirmed year for week numbers (held until confirmed), Monday-Sunday tenant default, no_on_hand weeks and chain restart. "
        f"Clone proof cip_n0111: re-run of the whole 2-year set changed nothing for Amazon, Takealot and Pinnacle; 0041 on cip, counts unchanged. "
        f"Full API pytest on cip_test {API}; full web vitest {WEB}. Commits d61e5af0, d7807c8b, 5de2186f. Web build {BUILD}. "
        "Limits: not rendered (sign-in); Pinnacle proof via fact upsert, not the DSI parser; cip stock positions not recomputed; 'Date' header not read as sale date; "
        "Pinnacle differences listed in the proof. Operator acceptance pending.")}, tag="_ver")
    emit(VER, "node.lease.release", {}, tag="_ver")


if __name__ == "__main__":
    {"impl": impl, "ver": ver}[sys.argv[1]]()
