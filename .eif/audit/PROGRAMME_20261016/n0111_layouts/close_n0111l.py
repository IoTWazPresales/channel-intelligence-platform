"""N-0111 layouts: record evidence, findings and quality under the build run, then re-record
VERIFIED_WITH_LIMITATIONS under a different verification run. No accept, no complete.

usage: python close_n0111l.py impl "<api result>" "<web result>" "<commits>"
       python close_n0111l.py ver  "<api result>" "<web result>" "<commits>"      (each event is one program.py call)
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
NODE = "N-0111"
IMPL = "RUN-20261016-N0111-LAYOUTS"
VER = "RUN-20261016-N0111-VER4"
REL = ".eif/audit/PROGRAMME_20261016/n0111_layouts/"
PROOF = REL + "N0111L_PROOF.md"
CLONE = REL + "N0111L_CLONE_PROOF.md"
MIGRATION = REL + "source_migration_cip.md"
DSI = REL + "probe_dsi_cip.txt"
API = sys.argv[2] if len(sys.argv) > 2 else "?"
WEB = sys.argv[3] if len(sys.argv) > 3 else "?"
COMMITS = sys.argv[4] if len(sys.argv) > 4 else "?"


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
    "N-0111 layouts (premise): customer sell-through had NO column-mapping step. The parser matched headers by template aliases and the "
    "batch dialog never asked; the mapping steps that exist are DSI, shipments, Product Master and historical lineup. Built by reuse, not a "
    "second system: the shared CanonicalColumnMappingPanel for the step, the job's field_mapping (header -> standard column, which the "
    "parser already gave priority over aliases) for the result. The only new storage is the saved layout. Also removed: the gate that "
    "called a file 'unmappable' when its headers did not look like sell-through, which would have blocked every first upload of a new layout.",
    "N-0111 layouts (migration, for Warren): the brief hides 'hist' and 'RAW' sources as build/test, but cst_hist_v2_* and cst_raw_* hold "
    "the real loaded files (15-26 Oct 2026, real customers, real fact rows, replay_of_job_id). Their applied jobs gave the 7 layouts; "
    "every one of the 26 sources is hidden. The layouts are named 'Imported layout - <first file>'; rename them under the customer in the "
    "upload window. Amazon (299) has no layout (its only source, cst_p4_amazon, has only validated jobs): the first Amazon upload opens "
    "the mapping step. A layout keeps the stored mapping exactly, including targets the parser ignores ('name' on Computer Mania). "
    "Computer Mania keeps structure mtd_delta and Makro pivoted because those jobs loaded that way. " + MIGRATION,
    "N-0111 layouts (Pinnacle / distributor path, listed, NOT built): (1) the distributor is not picked first - it is detected and "
    "confirmed per file (dsi_file_distributor) after upload; (2) the layout memory is ONE pool on the single source 'Distributor inventory "
    "feed' (id 12, column_mapping_memory.by_header_norm, 29 headers) shared by every distributor, so it is remembered by header, not per "
    "distributor, and one header meaning two things for two distributors would collide; (3) the wizard still shows 'Data provider / feed' "
    "with that one source; (4) layouts are not named, listed, renamed or removable. " + DSI,
    "N-0111 layouts (reporting list): the picker lists customers with Reports expected on (customer_report_config.reports_expected). "
    "advance_cst_report_slots also requires is_key_account, so Amazon (299) is ticked but not a key account and gets no late/missing "
    "slots; and the slot job still opens slots for a merged-away customer that stays ticked (the picker never lists those). Not changed.",
    "N-0111 layouts (matching): a layout matches by its header set with period-named columns (49-2025, 027.2026, week 14, Jan 2026) and "
    "unit stubs (ZAR, EA) left out. A file with one extra real column (Takealot week 39 has Supplier Stock) is another layout: the mapping "
    "step opens once, started from the closest saved layout. A layout removed in the upload window is hidden, not deleted; bringing one back "
    "is PATCH is_hidden=false (no button yet). Two layouts in one upload that map one header two ways are refused (upload separately).",
    "N-0111 layouts (API): POST /imports/jobs for customer sell-through now answers 409 and names the new upload; POST /imports/cst/batch-jobs "
    "takes customer_id (and layouts), no source_id. Jobs hang on one hidden internal source 'cst_customer_upload' and carry the customer in "
    "staged_metadata. The former source path stays in create_cst_batch_job_sync for scripts and tests. The load itself is unchanged: batch "
    "creates a validate job, steward resolves, apply loads.",
    "N-0111 layouts: not rendered (sign-in): the upload window and the mapping step are covered by component tests (customer list by name "
    "only, saved layouts rename, match needs no mapping, new layout blocks until the product column is mapped, error keeps the window open) "
    "and by a page test for the step. No browser session, no axe run.",
]


def impl() -> None:
    ensure_lease(IMPL, "impl")
    for path, note in (
        ("apps/api/app/models/customer_sellthrough_layout.py", "N-0111 layouts: the saved column layout (one per customer and header set)."),
        ("apps/api/alembic/versions/20261016_0043_cst_customer_layouts.py", "N-0111 layouts: layout table and source_definition.is_hidden; clone proof."),
        ("apps/api/app/services/imports/cst_layouts.py", "N-0111 layouts: reporting customers, header sniffing and fingerprint, match, save, customer upload."),
        ("apps/api/app/services/imports/cst_layout_migration.py", "N-0111 layouts: sources with applied jobs become layouts; all sources hidden."),
        ("apps/api/scripts/ops/migrate_cst_sources_to_layouts.py", "N-0111 layouts: dry run by default, --apply needs --expect-db."),
        ("apps/api/app/services/imports/cst_batch.py", "N-0111 layouts: batch job takes a customer, a mapping and a structure."),
        ("apps/api/app/api/v1/endpoints/imports.py", "N-0111 layouts: reporting-customers, layouts, propose and batch-jobs by customer; hidden sources not listed."),
        ("apps/api/tests/test_cst_layouts.py", "N-0111 layouts: fingerprint, header sniffing, mapping checks (pure)."),
        ("apps/api/tests/test_cst_layouts_db.py", "N-0111 layouts: unknown layout -> mapping -> saved -> automatic match -> identical load -> re-upload changes nothing; migration; cip_test."),
        ("apps/api/tests/test_cst_layouts_api.py", "N-0111 layouts: endpoint contract."),
        ("apps/web/src/app/(app)/admin/imports/CstBulkUploadDialog.tsx", "N-0111 layouts: customer picker, layout match, mapping step (shared panel)."),
        ("apps/web/src/app/(app)/admin/imports/CstBulkUploadDialog.test.tsx", "N-0111 layouts: dialog tests."),
        (CLONE, "N-0111 layouts: clone proof of 20261016_0043 and of the source migration."),
        (MIGRATION, "N-0111 layouts: before / after table of the 26 sources on cip."),
        (DSI, "N-0111 layouts: read-only look at the distributor path."),
        (PROOF, f"N-0111 layouts proof. Full API pytest on cip_test {API}; full web vitest {WEB}."),
    ):
        emit(IMPL, "evidence.add", {"path": path, "note": note, "provenance": "implementation-observation"},
             tag="_" + Path(path).stem[:40])
    for i, note in enumerate(FINDINGS, 1):
        emit(IMPL, "finding.defer", {"note": note, "code": "DOES_NOT_FIT"}, tag=f"_{i}")
    for dim, path, rationale in (
        ("testing", PROOF, f"Full API pytest on cip_test {API}; full web vitest {WEB}; new pure, DB, API and component tests for customer layouts."),
        ("data_integrity", CLONE, "20261016_0043 and the source migration proved on a clone of cip: facts, jobs and sources unchanged; second run changes nothing; downgrade with layouts present keeps every fact, job and source."),
        ("migration_safety", CLONE, "0043 additive (one table, one defaulted column): clone upgrade, downgrade, upgrade with every count equal; applied to cip as the migration role and to cip_test."),
        ("ux", "apps/web/src/app/(app)/admin/imports/CstBulkUploadDialog.test.tsx", "Upload window: customer by name, saved layouts with rename / remove, per-file layout chip, mapping step with required-column gate, error keeps the window open."),
        ("a11y", "apps/web/src/app/(app)/admin/imports/CstBulkUploadDialog.test.tsx", "Customer select, layout name and rename fields have labels; states are text, not colour; the shared mapping panel is reused. No axe run."),
    ):
        emit(IMPL, "node.quality", {"dim": dim, "state": "pass", "evidence": {"path": path, "summary": rationale[:200]}, "rationale": rationale},
             tag="_" + dim)
    emit(IMPL, "node.stage_note", {"stage_note": f"Layouts built ({COMMITS}): upload picks a reporting customer; layout is the only per-customer configuration "
                                                 "(first unknown layout -> mapping step -> saved; later files match by headers); 26 sources hidden, 7 layouts "
                                                 "migrated from applied jobs. Verification is a different run."},
         tag="_impl")
    emit(IMPL, "node.lease.release", {}, tag="_impl")


def ver() -> None:
    ensure_lease(VER, "ver")
    emit(VER, "node.verification", {"kind": "behavioral", "state": "pass", "evidence": "apps/api/tests/test_cst_layouts_db.py"}, tag="_b")
    emit(VER, "node.verification", {"kind": "referent", "state": "pass", "evidence": PROOF,
                                    "path": "apps/api/app/services/imports/cst_layouts.py"}, tag="_r")
    emit(VER, "node.stage_note", {"stage_note": (
        f"VERIFIED_WITH_LIMITATIONS (customer layouts). Self-verified under {VER}, different from build run {IMPL}; same session, same model, "
        "not independent. N-0099 does the second look. Per Warren (2026-10-16): a sell-through upload picks a reporting customer, not a source; "
        "every upload loads into the one sell-through table; the only per-customer configuration is the column layout (first unknown layout "
        "opens the mapping step and is saved; later files match by headers; several layouts per customer); build/test sources never shown. "
        "cip: 20261016_0043 applied after a clone proof; 7 layouts saved from applied jobs, all 26 sources hidden, nothing deleted, re-run "
        "changes nothing. cip_test proof: unknown-layout file -> mapping -> saved -> a second file with the same headers matched by itself and "
        "loaded identically -> re-upload changed nothing. "
        f"Full API pytest on cip_test {API}; full web vitest {WEB}. Commits {COMMITS}. "
        "Limits: not rendered (sign-in); the mapping step is new for sell-through (reuse of the shared panel); Pinnacle gaps listed, not built; "
        "hist/RAW sources kept as layouts because their applied jobs are real; Amazon has no layout yet. Operator acceptance pending.")}, tag="_ver")
    emit(VER, "node.lease.release", {}, tag="_ver")


if __name__ == "__main__":
    {"impl": impl, "ver": ver}[sys.argv[1]]()
