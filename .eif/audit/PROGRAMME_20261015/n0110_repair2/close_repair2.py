"""N-0110 repair 2: record evidence, decisions and findings under the repair run, then re-record
VERIFIED_WITH_LIMITATIONS under a different verification run. No accept, no complete.

usage: python close_repair2.py impl | ver
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
NODE = "N-0110"
IMPL = "RUN-20261015-N0110-REPAIR2"
VER = "RUN-20261015-N0110-VER3"
REL = ".eif/audit/PROGRAMME_20261015/n0110_repair2/"

SUPERSEDE = "apps/api/app/services/imports/customer_sell_through_supersede.py"
APPLY = "apps/api/app/services/imports/customer_sell_through_apply.py"
GRAIN = "apps/api/app/services/imports/parsers/customer_sell_through_grain.py"
SUP_TEST = "apps/api/tests/test_cst_reupload_supersede_db.py"
YEAR_TEST = "apps/api/tests/test_cst_week_year_received.py"
PROOF = REL + "N0110_REPAIR2_PROOF.md"
CAUSE = "apps/api/app/services/channel_intelligence/customer_stock_gap_cause.py"

RECOVERED = (
    "Units recovered on cip: Makro Dispo (15) +5434 (site-merged rows restored per site; 315 older rows, 595 u, superseded "
    "by newer loads for the same customer, product and period), Takealot (20) +712 (week split over months summed), "
    "Game (57) +57 (differing repeats summed), Computer Mania (18) +32 (repeated article rows summed). Week 40 rows dated "
    "2026-09-28 from 2026-08-11 loads moved to 2025-09-29: 75 rows, 529 u (18: 56/510, 57: 19/19). Clone run 2 identical; "
    "cip after equals clone after."
)
CAUSES = (
    "243 flagged of 314 compared (701 positions, 1 unit). First cause: overwrite 0 (was 8), unmatched shipment 0, no POD 0, "
    "no prior on-hand 37 (was 29), repeated report 108, unreported weeks 58, unexplained 40 (Computer Mania 28, Evetech 7, "
    "Takealot 5)."
)
LEFT = (
    "Loads with no stored file, not restated: jobs 903 (cust 15, 43 under-counted rows), 911 (57, 13), 912 (12, 24), "
    "913 (11, 11), 917 (18, none), 918 (299, 1)."
)


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
    path = HERE / f"_r2_{event.replace('.', '_')}{tag}.json"
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
    emit(IMPL, "node.blocker.close", {"id": "BL-N0110-CAUSES", "note": "Warren accepted D-0089 on 2026-10-15."})
    for path, note in (
        (SUPERSEDE, "N-0110 repair 2 (92340adb, D-0090): a newer load supersedes an older load's rows for the same customer and product whose period overlaps a period it wrote and lies in its span for that customer, whatever site or day grain; rows move verbatim to fact_customer_sellthrough_superseded. Replaces the byte-identical rule (D-0088)."),
        (APPLY, "N-0110 repair 2 (92340adb, D-0091): source rows of one key that differ are summed; a row identical in every source column counts once and its copies get apply_status 'duplicate'. On-hand/in transit/on order repeated with one value is kept once, different values summed (proposed, D-0092)."),
        (GRAIN, "N-0110 repair 2 (5e6bc4fd): a week or month with no year resolves to the latest one started by the receive day (staged_metadata.received_on, else job created date), never a period not yet started."),
        (PROOF, "N-0110 repair 2 proof: " + RECOVERED + " " + CAUSES + " " + LEFT),
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
                "On-hand when differing repeated rows of one key are summed (N-0110, D-0091 names units only). Question: how "
                "do on-hand, in transit and on order combine? Options: (1) a value every line repeats is one snapshot and kept "
                "once, different values are summed (built); (2) always sum; (3) keep the last line's. Evidence on cip: 73 "
                "repeated rows carry on-hand; 69 repeat one value (Takealot: a week split over two months, each line 336), 4 "
                "differ (Computer Mania, two article rows per product: on-hand +168). Assumption: equal values on split lines "
                "are the same stock. Impact: option 2 would double Takealot on-hand. Reversible: re-apply the loads. "
                "Resolving experiment: ask Computer Mania whether its two article rows hold separate stock."
            ),
        },
        node_scoped=False,
    )
    did = last_decision_id()
    print("on-hand decision", did, flush=True)
    emit(IMPL, "node.blocker.open", {"id": "BL-N0110-ONHAND", "type": "decision", "ref": did,
                                     "note": "Warren: accept or change how on-hand combines when differing repeated rows are summed. Built as option 1."})
    for code, note in (
        ("DOES_NOT_FIT", "N-0110 repair 2: " + LEFT + " Their site-merged and repeated rows stay under-counted until the files are uploaded again."),
        ("DOES_NOT_FIT", "N-0110 repair 2: loads 955, 956 (Takealot) and 967 (Dispo WK26) stored no on-hand and were replayed marked sales-only; the on-hand rule refuses them otherwise."),
    ):
        emit(IMPL, "finding.defer", {"note": note, "code": code}, tag="_" + str(abs(hash(note)) % 1000))
    for dim, path, rationale in (
        ("testing", SUP_TEST, "pytest 248 passed on CST, sell-through, stock gap, tenant profile and lineup period tests (cip_test), incl. 4 supersede/repeat DB tests and 3 week-year tests. No Python linter available."),
        ("data_integrity", PROOF, "Clone: second replay superseded 0 and changed no total; cip after equals clone after. Superseded rows kept verbatim with the superseding load; staging kept; nothing hard-deleted. " + RECOVERED),
    ):
        emit(IMPL, "node.quality", {"dim": dim, "state": "pass", "evidence": {"path": path, "summary": rationale[:200]}, "rationale": rationale}, tag="_" + dim)
    emit(IMPL, "node.stage_note", {"stage_note": "Repair 2 built (92340adb, 5e6bc4fd) and applied to cip by replay. " + RECOVERED + " " + CAUSES + " Verification is a different run."}, tag="_impl")
    emit(IMPL, "node.lease.release", {}, tag="_impl")


def ver() -> None:
    emit(VER, "node.lease.acquire", {"ttl_seconds": 3600}, tag="_ver")
    emit(VER, "node.verification", {"kind": "behavioral", "state": "pass", "evidence": SUP_TEST}, tag="_b")
    emit(VER, "node.verification", {"kind": "referent", "state": "pass", "evidence": PROOF, "path": SUPERSEDE}, tag="_r")
    emit(
        VER,
        "node.stage_note",
        {
            "stage_note": (
                "VERIFIED_WITH_LIMITATIONS (repair 2). Self-verified under " + VER + ", different from repair run " + IMPL + "; "
                "same session, same model, not independent. N-0099 does the second look. " + RECOVERED + " " + CAUSES + " "
                "Limits: " + LEFT + " On-hand combining for summed repeats awaits Warren (decision blocker). Stock gap tab not "
                "rendered (sign-in). Shipment loads do not recompute positions. Operator acceptance pending."
            )
        },
        tag="_ver",
    )
    emit(VER, "node.lease.release", {}, tag="_ver")


if __name__ == "__main__":
    {"impl": impl, "ver": ver}[sys.argv[1]]()
