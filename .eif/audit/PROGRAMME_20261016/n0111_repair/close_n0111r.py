"""N-0111 repair: record evidence, findings and quality under the repair run, then re-record
VERIFIED_WITH_LIMITATIONS under a different verification run. No accept, no complete.

usage: python close_n0111r.py impl | ver      (each event is one program.py call; payload files kept beside this script)
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
NODE = "N-0111"
IMPL = "RUN-20261016-N0111-REPAIR"
VER = "RUN-20261016-N0111-VER2"
REL = ".eif/audit/PROGRAMME_20261016/n0111_repair/"
PROOF = REL + "N0111R_PROOF.md"
CLONE = REL + "N0111R_CLONE_PROOF.md"
TRACE = REL + "N0111_UNMERGE_TRACE.md"
RECOMPUTE = REL + "recompute_stock_gap_output.txt"
COMMITS = sys.argv[2] if len(sys.argv) > 2 else ""
API = (HERE / "api_result.txt").read_text(encoding="utf-8").strip() if (HERE / "api_result.txt").exists() else "?"
WEB = (HERE / "web_result.txt").read_text(encoding="utf-8").strip() if (HERE / "web_result.txt").exists() else "?"


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


def ensure_lease(run: str, tag: str) -> None:
    lease = node_state(run).get("lease")
    if lease and lease.get("run") == run:
        return
    if lease:
        emit(run, "node.lease.release", {}, tag=f"_{tag}_stale")
    emit(run, "node.lease.acquire", {"ttl_seconds": 3600}, tag=f"_{tag}")


FINDINGS = [
    ("DOES_NOT_FIT", "N-0111 repair item 5 (Warren to decide) (D-0111) not done: the 2026-08-08 OPEN_CHANNEL absorb of Compuspeed LTD (1152) and "
     "SYNTECH DISTRIBUTION (PTY) LTD (4145) recorded only the loser ids. Traceable: 31/31 OPEN_CHANNEL sell-out facts (26 Compuspeed, "
     "544 u; 5 Syntech, 26 u) via job 96 staging tokens, 16 lineup lines (steward audit). Not traceable: shipments (5451 facts, 31.8k "
     "evidence lines), CPOR case 174, 76 lineup lines, reconciliation 12, velocity 2, returns 4. No un-merge made. " + TRACE),
    ("DOES_NOT_FIT", "N-0111 repair: after the cip stock-position recompute (D-0105 chain rule), 4158 positions: no_on_hand 3457, "
     "chain_restart 298, first_report 387, compared 16 (Game only; was 314 compared, 243 flagged). Computer Mania alone has 2426 "
     "no-on-hand weeks over 56 products. Comparisons now need on-hand in consecutive weeks. " + RECOMPUTE),
    ("DOES_NOT_FIT", "N-0111 repair: distributor lines of one load with the same invoice, product, date and customer replace each "
     "other (the later line wins); the earlier figures are now kept as superseded and the load report names them. Summing them "
     "like customer sell-through D-0091 is a Warren decision."),
    ("DOES_NOT_FIT", "N-0111 repair: the week 52 -> 1 year roll reads row-level week labels (a Week column). A wide file with one "
     "column per week (W51, W52, W1 headers) still takes one year for every column; month labels (Dec -> Jan) do not roll."),
    ("DOES_NOT_FIT", "N-0111 repair: re-running an older distributor load after a newer one replaces the newer figures again and "
     "keeps them (superseded trail grows: clone 6 -> 10 sell-out, 1 -> 2 returns); totals end where the last load leaves them."),
    ("DOES_NOT_FIT", "N-0111 repair: customer sell-through has no upload-time column-mapping screen; a date column with another "
     "header needs the source's field mapping or template alias. The distributor mapping step lets the uploader pick any column as "
     "Date (transaction_date)."),
]


def impl(skip_evidence: bool = False) -> None:
    ensure_lease(IMPL, "impl")
    for path, note in () if skip_evidence else (
        ("apps/api/app/services/imports/parsers/customer_sell_through_flat.py",
         "N-0111 repair: 'Date' is a built-in sale-date alias (D-0107); skipped rows by reason."),
        ("apps/api/app/services/imports/parsers/customer_sell_through_grain.py",
         "N-0111 repair: roll_bare_week_years - week 52/53 -> 1 rolls the confirmed year (D-0109)."),
        ("apps/api/app/services/imports/dsi_line_supersede.py",
         "N-0111 repair: same-invoice distributor reloads keep replaced figures (D-0110)."),
        ("apps/api/alembic/versions/20261016_0042_dsi_line_superseded.py",
         "N-0111 repair: fact_distributor_line_superseded, append-only; clone proof cip_n0111r then cip."),
        ("apps/api/app/services/imports/import_load_report.py",
         "N-0111 repair: rows read / loaded / not loaded by reason; 'Completed with rows not loaded (N)' (D-0108)."),
        ("apps/web/src/app/(app)/admin/imports/ImportJobLoadReport.tsx",
         "N-0111 repair: Import Center load report panel and Status column display status."),
        ("apps/api/tests/test_import_load_report.py", "N-0111 repair: load report unit and cip_test DB tests (CST and DSI)."),
        ("apps/api/tests/test_dsi_line_supersede_db.py", "N-0111 repair: DSI same-invoice supersede DB tests on cip_test."),
        ("apps/api/tests/test_cst_history_upload_rules.py", "N-0111 repair: Date header and week 52 -> 1 roll tests."),
        (CLONE, "N-0111 repair clone proof cip_n0111r: 0042 round trip, CST Date / roll / dropped rows, Pinnacle load-reload-correct."),
        (TRACE, "N-0111 repair item 5: Compuspeed/Syntech un-merge traceability on cip (read-only); not traceable exactly."),
        (RECOMPUTE, "N-0111 repair item 6: cip stock positions recomputed once; cause table."),
        (PROOF, f"N-0111 repair proof. Full API pytest on cip_test {API}; full web vitest {WEB}."),
    ):
        emit(IMPL, "evidence.add", {"path": path, "note": note, "provenance": "implementation-observation"},
             tag="_" + Path(path).stem[:40])
    for i, (code, note) in enumerate(FINDINGS, 1):
        emit(IMPL, "finding.defer", {"note": note, "code": code}, tag=f"_{i}")
    for dim, path, rationale in (
        ("testing", PROOF, f"Full API pytest on cip_test {API}; full web vitest {WEB}; new DB tests for DSI supersede and the load report; parser tests for Date and the year roll; web tsc exit 0."),
        ("data_integrity", CLONE, "Clone: Pinnacle reload kept 4+1 superseded records, correction 2 more, new invoice added; re-applying the correction changed nothing; CST re-run of three files changed nothing; cip counts unchanged by 0042."),
        ("migration_safety", CLONE, "0042 additive: clone upgrade, downgrade, upgrade with every count equal; cip sell-out 35582, units 178195.85, returns 3176, inventory 47411, DSI staging 183463, CST facts 3197 unchanged."),
        ("observability", "apps/api/app/services/imports/import_load_report.py", "Each CST and DSI job reports rows read, loaded, not loaded and partly loaded with the reason per category; DSI apply summary carries superseded_lines."),
        ("ux", "apps/web/src/app/(app)/admin/imports/ImportJobLoadReport.tsx", "Status column reads 'Completed with rows not loaded (N)'; the job panel lists each reason with its rows."),
        ("content", "apps/api/app/services/imports/import_load_report.py", "Reason labels name what is missing and where to fix it (steward, Sales-only, Stock-only, Year confirmed)."),
    ):
        emit(IMPL, "node.quality", {"dim": dim, "state": "pass", "evidence": {"path": path, "summary": rationale[:200]}, "rationale": rationale},
             tag="_" + dim)
    emit(IMPL, "node.stage_note", {"stage_note": f"Repair built ({COMMITS}): Date header, rows-not-loaded report, week 52 -> 1 roll, "
                                                  "same-invoice distributor supersede (0042 on cip), stock positions recomputed on cip. "
                                                  "Item 5 (un-merge) stopped for Warren: not traceable. Verification is a different run."},
         tag="_impl")
    emit(IMPL, "node.lease.release", {}, tag="_impl")


def ver() -> None:
    ensure_lease(VER, "ver")
    emit(VER, "node.verification", {"kind": "behavioral", "state": "pass", "evidence": "apps/api/tests/test_import_load_report.py"}, tag="_b")
    emit(VER, "node.verification", {"kind": "referent", "state": "pass", "evidence": CLONE,
                                    "path": "apps/api/app/services/imports/dsi_line_supersede.py"}, tag="_r")
    emit(VER, "node.stage_note", {"stage_note": (
        f"VERIFIED_WITH_LIMITATIONS (repair). Self-verified under {VER}, different from repair run {IMPL}; same session, same model, "
        "not independent. N-0099 does the second look. Repair per Warren D-0107..D-0111: 'Date' is a sale-date column (CST alias; DSI "
        "already mapped it); every CST and DSI load reports rows read / loaded / not loaded by reason and shows 'Completed with rows not "
        "loaded (N)'; bare week numbers roll the confirmed year at week 52/53 -> 1; distributor reloads of the same invoice keep the "
        "replaced figures (20261016_0042, clone cip_n0111r then cip, counts unchanged). Clone: CST Date file day grain, W51-W2 2024 -> "
        "2024-W51, 2024-W52, 2025-W1, 2025-W2; dropped-rows file 'Completed with rows not loaded (2)'; Pinnacle load / reload / correct "
        "superseded 0 -> 5 -> 7, re-apply changed nothing. cip stock positions recomputed: 4158 (no_on_hand 3457, chain_restart 298, "
        "first_report 387, compared 16, all no prior on-hand). "
        f"Full API pytest on cip_test {API}; full web vitest {WEB}. Commits {COMMITS}. "
        "Limits: item 5 un-merge NOT done (rows not traceable exactly; Warren to choose); not rendered (sign-in); Pinnacle proof via "
        "fact upsert, not the DSI parser; wide week-column files and month labels do not roll; repeated same-key lines in one "
        "distributor load are not summed. Operator acceptance pending.")}, tag="_ver")
    emit(VER, "node.lease.release", {}, tag="_ver")


if __name__ == "__main__":
    {"impl": impl, "impl-rest": lambda: impl(True), "ver": ver}[sys.argv[1]]()
