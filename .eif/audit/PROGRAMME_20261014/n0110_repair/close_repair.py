"""N-0110 repair: record evidence, decisions and findings under the repair run, then re-record
VERIFIED_WITH_LIMITATIONS under a different verification run. No accept, no complete.

usage: python close_repair.py impl | ver
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
NODE = "N-0110"
IMPL = "RUN-20261014-N0110-REPAIR"
VER = "RUN-20261015-N0110-VER2"
REL = ".eif/audit/PROGRAMME_20261014/n0110_repair/"

SUPERSEDE = "apps/api/app/services/imports/customer_sell_through_supersede.py"
MIG = "apps/api/alembic/versions/20261015_0038_cst_superseded_rows.py"
CAUSE = "apps/api/app/services/channel_intelligence/customer_stock_gap_cause.py"
PANEL = "apps/web/src/app/(app)/admin/cst-steward/CstStockGapSection.tsx"
REUP_TEST = "apps/api/tests/test_cst_reupload_supersede_db.py"
CAUSE_TEST = "apps/api/tests/test_customer_stock_gap_cause_db.py"
REUP_PROOF = REL + "N0110_REUPLOAD_PROOF.md"
COUNTS = REL + "N0110_CAUSE_COUNTS.md"

CAUSES = (
    "243 flagged of 314 compared (701 positions, threshold 1 unit), unchanged. First cause: "
    "(a) old overwrite 8 (by site 8, by sale day 0); (b) unmatched shipment 0; (c) no POD 0; "
    "(d) no prior on-hand 29; (e) 206, split: repeated report 108, unreported weeks 58, unexplained 40 "
    "(Computer Mania 28, Evetech 7, Takealot 5)."
)
OVERWRITE = (
    "Rows on cip holding 2+ source rows of the load that wrote them: 2+ sale days 0; 2+ sites 366 "
    "(6840 source units more than stored); same-site repeats 99 (817)."
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
    path = HERE / f"_repair_{event.replace('.', '_')}{tag}.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    result = subprocess.run(cli(run) + ["event", event, "--payload-file", str(path)], capture_output=True, text=True, cwd=ROOT)
    print(run, event, tag, result.returncode, (result.stdout or "").strip(), (result.stderr or "").strip()[-600:], flush=True)
    if result.returncode != 0:
        raise SystemExit(1)


def impl() -> None:
    for path, note in (
        (SUPERSEDE, "N-0110 repair (d31433fe): a re-upload of byte-identical files supersedes the rows its earlier load wrote under other keys; rows move verbatim to fact_customer_sellthrough_superseded."),
        (MIG, "N-0110 repair: 20261015_0038 adds fact_customer_sellthrough_superseded (product-line RLS, no update/delete policy). Clone round trip clean; applied to cip; fact rows 1823, units 6159, on-hand 28812 unchanged."),
        (REUP_PROOF, "N-0110 repair clone proof (cip_n0110p, dropped): Dispo WK1 re-upload customer 15 688 -> 1574 (+886, same week and product now one row per site; old load stored 151 of 1118 source units); second re-upload no change. Computer Mania wk40: total 2299 unchanged, 56 rows moved 2026-09-28 -> 2025-09-29; second re-upload no change."),
        (COUNTS, "N-0110 repair cause counts on cip (read-only): " + CAUSES + " " + OVERWRITE),
        (CAUSE, "N-0110 repair (be0a1d5d): cause per compared position, first match of overwrite, unmatched_shipment, no_pod, no_prior_on_hand, repeated_report, unreported_weeks, unexplained. " + CAUSES),
        (PANEL, "N-0110 repair: Stock gap tab shows Why it differs right after Gap; Flag reads Data gap or Stock difference; only a stock difference keeps the warning highlight; counts line splits data gaps from stock differences."),
    ):
        emit(IMPL, "evidence.add", {"path": path, "note": note, "provenance": "implementation-observation"}, tag="_" + Path(path).stem)

    decisions = (
        "Re-upload idempotence (N-0110 repair): after a sell-through load applies, an older stored row is superseded only when "
        "the load that last wrote it read files byte-identical (sha256 of the stored file) to files in this load, this load "
        "restates the same customer and product, and this load did not write that key. Superseded rows move verbatim "
        "(row_json) into fact_customer_sellthrough_superseded with the superseding load and reason; staging rows stay. "
        "Same file name alone is not enough (a customer can resend 'ASUS WEEK 31.xlsx' each year). A load whose old file "
        "is gone, or with a failed chunk, supersedes nothing. Reversible: drop the step; the moved rows can be copied back.",
        "Gap causes beyond the four named (N-0110 repair). Question: should a gap that CIP can trace to a report repeating the "
        "previous report's figures, or to weeks with no report in the window, be shown as a data gap rather than a stock "
        "difference? Options: (1) yes, as two more causes ahead of unexplained (built); (2) no, leave them unexplained (206 of "
        "243 flagged would read as stock differences); (3) treat a repeated report as a load error and refuse it at upload. "
        "Evidence: Computer Mania 2025-12-29, 2026-03-30, 2026-06-29 and 2026-09-28 store identical figures from different "
        "files (108 flagged); 58 short gaps have windows with unreported weeks. Assumptions: identical figures in two reports "
        "are not real; missing weekly reports hide sales. Sign rule: unmatched and no-POD shipments explain only over gaps, "
        "unreported weeks only short gaps. Impact: unexplained 206 -> 40. Reversible: classifier only, no number changes. "
        "Resolving experiment: ask Computer Mania whether those four reports were refreshed.",
    )
    for i, statement in enumerate(decisions, 1):
        emit(IMPL, "decision.add", {"scope": NODE, "origin": "implementation", "status": "proposed", "statement": statement}, node_scoped=False, tag=f"_{i}")

    findings = (
        "N-0110 repair: earlier finding (re-upload of an old file counts units twice) is fixed in d31433fe for byte-identical files. A different file covering the same week still loads beside the old rows.",
        "N-0110 repair: 366 stored rows on cip still hold several sites as one row (customers 15, 12, 11; 6840 source units more than stored) until their files are re-uploaded. Files are gone for jobs 903, 911, 912, 913, 917, 918.",
        "N-0110 repair: 99 stored rows hold same-site, same-period repeats (817 source units more than stored). Current code still keeps the last row for a repeated key; not changed.",
        "N-0110 repair: 75 stored rows sit on week 40 dated 2026-09-28 by loads made 2026-08-11 (customers 18 and 57). A re-upload moves them to 2025-09-29; no bulk correction was run.",
        "N-0110 repair: no Python linter (ruff) is installed in apps/api/.venv; API changes were not linted.",
    )
    for i, note in enumerate(findings, 1):
        emit(IMPL, "finding.defer", {"note": note, "code": "DOES_NOT_FIT"}, tag=f"_{i}")

    tests = (
        "pytest 217 passed on CST, sell-through, stock gap, period grain and tenant profile tests (cip_test), incl. new "
        "re-upload supersede DB tests (3) and gap-cause DB tests (2); vitest 13 passed in cst-steward; web tsc exit 0; "
        "next lint clean on changed files. No Python linter available."
    )
    for dim, path, rationale in (
        ("testing", REUP_TEST, tests),
        ("data_integrity", SUPERSEDE, "Re-upload of the same file is idempotent: clone proof second re-upload changed nothing; superseded rows are kept verbatim with the superseding load; staging rows untouched; no number in a stock position is changed by the cause classifier."),
        ("migration_safety", REUP_PROOF, "20261015_0038 additive: clone upgrade, downgrade, upgrade clean; cip_test upgraded; applied to cip with fact rows 1823, units 6159, on-hand 28812, staging 43472 unchanged."),
        ("ux", PANEL, "Stock gap tab: Why it differs beside Gap; Flag reads Data gap or Stock difference; counts line says how many highlighted rows are data gaps and how many have none found."),
        ("a11y", PANEL, "The data-gap state is text (Flag column and Why it differs), not colour only; data-gap gap cells are italic on a neutral tint, stock differences keep bold on warning. No axe run."),
        ("content", CAUSE, "Cause labels start with Data gap: or Stock difference:. A data-gap row's What it can mean starts Not read as the customer's stock until this is fixed."),
    ):
        emit(IMPL, "node.quality", {"dim": dim, "state": "pass", "evidence": {"path": path, "summary": rationale[:200]}, "rationale": rationale}, tag="_" + dim)
    emit(
        IMPL,
        "node.quality",
        {
            "dim": "rendered",
            "rationale": "Not rendered this session: the earlier attempt redirected /admin/cst-steward?tab=stock-gap to sign-in and the agent may not enter a password. Web build WYUCq5dcTsmOhEkcqKEYX is live after restart. Component tests cover the cause column.",
        },
        tag="_rendered",
    )
    emit(
        IMPL,
        "node.stage_note",
        {"stage_note": "Repair built: re-upload supersede (d31433fe, 20261015_0038 on cip) and gap causes (be0a1d5d). " + CAUSES + " Verification is a different run."},
        tag="_impl",
    )
    emit(IMPL, "node.lease.release", {})


def ver() -> None:
    emit(VER, "node.lease.acquire", {"ttl_seconds": 3600}, tag="_ver")
    emit(VER, "node.verification", {"kind": "behavioral", "state": "pass", "evidence": REUP_TEST}, tag="_b")
    emit(VER, "node.verification", {"kind": "referent", "state": "pass", "evidence": COUNTS, "path": CAUSE}, tag="_r")
    emit(
        VER,
        "node.stage_note",
        {
            "stage_note": (
                "VERIFIED_WITH_LIMITATIONS (repair). Self-verified under " + VER + ", different from repair run " + IMPL + "; "
                "same session, same model, not independent. N-0099 does the second look. Re-upload of the same file is "
                "idempotent (clone proof: second re-upload no change; Dispo WK1 +886 was one row per site restored). " + CAUSES + " "
                "Limits: Stock gap tab not rendered (sign-in); 366 site-collapsed rows on cip stay until their files are "
                "re-uploaded; a different file for the same week still adds rows; two added causes await Warren; shipment loads "
                "do not recompute positions; highlight 1 unit (D-0086 accepted). Operator acceptance pending."
            )
        },
        tag="_ver",
    )
    emit(VER, "node.lease.release", {}, tag="_ver")


if __name__ == "__main__":
    {"impl": impl, "ver": ver}[sys.argv[1]]()
