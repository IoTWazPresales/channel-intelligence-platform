"""N-0111 repair 2: record evidence, findings and quality under the repair run, then re-record
VERIFIED_WITH_LIMITATIONS under a different verification run. No accept, no complete.

usage: python close_n0111r2.py impl | ver <commits>    (each event is one program.py call)
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
NODE = "N-0111"
IMPL = "RUN-20261016-N0111-REPAIR2"
VER = "RUN-20261016-N0111-VER3"
REL = ".eif/audit/PROGRAMME_20261016/n0111_repair2/"
PROOF = REL + "N0111R2_PROOF.md"
RECOMPUTE = REL + "recompute_stock_gap_output.txt"
PROBE = REL + "probe_restarts_cip.txt"
COUNT = REL + "probe_unmerge_raw_cip.txt"
API = "3041 passed, 21 skipped, 0 failed"
WEB = "187 files, 872 passed, 0 failed (2 workers)"
COMMITS = sys.argv[2] if len(sys.argv) > 2 else "0aeffcbc, 045fd68a"


def cli(run: str) -> list[str]:
    return [sys.executable, str(ROOT / ".eif/runtime/programme/program.py"), "--run", run, "--actor", "gov-001"]


def node_state(run: str) -> dict:
    r = subprocess.run(cli(run) + ["status", "--node", NODE], capture_output=True, text=True, cwd=ROOT)
    if r.returncode != 0:
        raise SystemExit(r.stderr or r.stdout)
    t = r.stdout
    return json.loads(t[t.rfind("{", 0, t.find(f'"id": "{NODE}"')):])


def emit(run: str, event: str, body: dict, *, tag: str = "") -> None:
    body = dict(body)
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
    ("DOES_NOT_FIT", "N-0111 repair 2 (D-0114): Compuspeed (1152) / Syntech (4145) un-merge PARKED by Warren; no partial un-merge. "
     "Read-only count on cip of OPEN_CHANNEL rows whose raw text names them: fact_inbound_shipment 214 of 5499, shipment_evidence_line "
     "1414 of 31975, shipment_evidence_observation 576 of 16093, shipment_evidence_current 198 of 5662, commercial_lineup_line 52 of 92 "
     "(text hits, not proof of owner). BACKLOG-212, trigger: before distributor-level reporting is shown to users. " + COUNT),
    ("DOES_NOT_FIT", "N-0111 repair 2 (D-0112): the bridge compares only when sales are reported for EVERY whole week between two on-hand "
     "reports; one uncovered week makes the later report 'Unreported weeks' (stored chain_restart, no migration). That partial-coverage "
     "reading is mine, not stated by Warren. On cip nothing new is compared: 289 of 298 report points after a gap have no sales row of "
     "any kind between the reports, 9 have some. " + PROBE),
    ("DOES_NOT_FIT", "N-0111 repair 2 (D-0113): summed repeated distributor lines keep the later line's unit price and currency; no price "
     "is recomputed from the totals. Proof is through the real apply function on cip_test with staging lines built directly, not the "
     "file parser, and no cip load was made."),
]


def impl() -> None:
    ensure_lease(IMPL, "impl")
    for path, note in (
        ("apps/api/app/services/channel_intelligence/customer_stock_gap.py",
         "N-0111 repair 2: stock chain bridges weeks with no on-hand when sales are reported (D-0112); unreported weeks start a fresh chain."),
        ("apps/api/tests/test_customer_stock_gap.py", "N-0111 repair 2: bridge, delivery, unreported-weeks and coverage tests."),
        ("apps/api/tests/test_customer_stock_gap_cause_db.py", "N-0111 repair 2: bridged chain and stock-only row on cip_test."),
        ("apps/api/app/services/imports/dsi_line_supersede.py",
         "N-0111 repair 2: RepeatedLines - differing repeated distributor lines summed, identical counted once (D-0113)."),
        ("apps/api/app/services/imports/distributor_sales_inventory.py", "N-0111 repair 2: apply writes one row per repeated key."),
        ("apps/api/app/services/imports/import_load_report.py", "N-0111 repair 2: repeated lines loaded; identical copies counted once."),
        ("apps/api/tests/test_dsi_line_supersede_db.py", "N-0111 repair 2: Pinnacle repeated-line tests on cip_test."),
        (RECOMPUTE, "N-0111 repair 2: cip stock positions recomputed once; status table before and after."),
        (PROBE, "N-0111 repair 2: read-only probe of the remaining 298 unreported-weeks points."),
        (COUNT, "N-0111 repair 2: read-only count of OPEN_CHANNEL rows naming Compuspeed or Syntech."),
        (PROOF, f"N-0111 repair 2 proof. Full API pytest on cip_test {API}; full web vitest {WEB}."),
    ):
        emit(IMPL, "evidence.add", {"path": path, "note": note, "provenance": "implementation-observation"},
             tag="_" + Path(path).stem[:40])
    for i, (code, note) in enumerate(FINDINGS, 1):
        emit(IMPL, "finding.defer", {"note": note, "code": code}, tag=f"_{i}")
    for dim, path, rationale in (
        ("testing", PROOF, f"Full API pytest on cip_test {API}; full web vitest {WEB}; new pure and DB tests for the stock chain bridge and for Pinnacle repeated lines; web build and restart done."),
        ("data_integrity", RECOMPUTE, "cip stock positions recomputed once (derived table): compared 16, flagged 16, no on-hand 36, unreported weeks 298, first report 387; no fact table written. Pinnacle repeated lines: re-apply changes nothing, reload keeps the replaced total."),
    ):
        emit(IMPL, "node.quality", {"dim": dim, "state": "pass", "evidence": {"path": path, "summary": rationale[:200]}, "rationale": rationale},
             tag="_" + dim)
    emit(IMPL, "node.stage_note", {"stage_note": f"Repair 2 built ({COMMITS}): stock chain bridge (D-0112), repeated Pinnacle lines D-0091 (D-0113), "
                                                  "un-merge parked with BACKLOG-212 (D-0114), cip positions recomputed once. Verification is a different run."},
         tag="_impl")
    emit(IMPL, "node.lease.release", {}, tag="_impl")


def ver() -> None:
    ensure_lease(VER, "ver")
    emit(VER, "node.verification", {"kind": "behavioral", "state": "pass", "evidence": "apps/api/tests/test_customer_stock_gap.py"}, tag="_b")
    emit(VER, "node.verification", {"kind": "referent", "state": "pass", "evidence": PROOF,
                                    "path": "apps/api/app/services/channel_intelligence/customer_stock_gap.py"}, tag="_r")
    emit(VER, "node.stage_note", {"stage_note": (
        f"VERIFIED_WITH_LIMITATIONS (repair 2). Self-verified under {VER}, different from repair run {IMPL}; same session, same model, "
        "not independent. N-0099 does the second look. Per Warren D-0112..D-0114: the stock chain bridges weeks with no on-hand when sales "
        "are reported for every week in between (last on-hand + matched deliveries - all sales); the chain starts fresh only when sales are "
        "also missing (Unreported weeks, a data gap; stored chain_restart). Repeated Pinnacle lines in one file follow D-0091: differing "
        "lines summed, identical lines counted once and flagged duplicate. Un-merge parked (BACKLOG-212; read-only count recorded). "
        "cip positions recomputed once: compared 16 (was 16), flagged 16 (16), no on-hand reported 36 (3457), unreported weeks 298 (298), "
        "first report 387 (387): no gap in the real data has sales for every missing week, so nothing new is compared. "
        f"Full API pytest on cip_test {API}; full web vitest {WEB}. Commits {COMMITS}. "
        "Limits: partial-coverage reading is mine; not rendered (sign-in); Pinnacle proof via the apply function, not the file parser; "
        "summed lines keep the later price; wide week-column files and month labels do not roll. Operator acceptance pending.")}, tag="_ver")
    emit(VER, "node.lease.release", {}, tag="_ver")


if __name__ == "__main__":
    {"impl": impl, "ver": ver}[sys.argv[1]]()
