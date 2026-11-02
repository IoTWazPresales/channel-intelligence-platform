"""Mutation harness for batch 2: break ONE fix at a time, run the tests written for it, restore the file.

Run from the repo root:  python .eif/audit/REVIEW_20261102/batch2/mutate.py
Each entry: (label, file, old text, new text, pytest selector). The file is restored in a finally block, and the
restored text is compared with the original so a failed restore cannot go unnoticed. cip_test only (via run_on_cip_test.py).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
RUNNER = ROOT / ".eif" / "audit" / "REVIEW_20261102" / "batch1" / "run_on_cip_test.py"
BOOK = "tests/test_batch2_book_minors.py"

MUTATIONS = [
    ("older-report guard ignores the operating unit", "apps/api/app/services/imports/shipment_open_book.py",
     'key = (str(r["report_type"]), "" if r["report_type"] == REPORT_ACZA_BOM else str(r["operating_unit"]))',
     'key = (str(r["report_type"]), "")', (BOOK, "lagging or one_current or same_unit")),
    ("partial shipment closes silently", "apps/api/app/services/imports/shipment_open_book.py",
     'and round(item["shipped_quantity"], 4) < round(item["quantity"], 4)', "and False", (BOOK, "partial or full_shipment")),
    ("orphan quantity not checked", "apps/api/app/services/imports/shipment_shipped_fact_identity_twin_merge.py",
     "return round(float(a or 0), 4) == round(float(b or 0), 4)", "return True", (BOOK, "another_quantity")),
    ("two orphans may share one fact", "apps/api/app/services/imports/shipment_shipped_fact_identity_twin_merge.py",
     'claimed.add(pick["id"])', "pass", (BOOK, "two_orphans")),
    ("no audit event at load time", "apps/api/app/services/imports/shipment_shipped_fact_identity_twin_merge.py",
     "if (audit if audit is not None else own_plan) and", "if False and", (BOOK, "another_quantity or audit_event")),
    ("pointer refresh scans the whole table", "apps/api/app/services/imports/shipment_shipped_fact_identity_twin_merge.py",
     'job_scope = "AND k.import_job_id = :job " if written_by_job is not None else ""', 'job_scope = ""', (BOOK, "pointers")),
    ("reclassify is table-wide", "apps/api/app/services/imports/shipment_open_book.py",
     'raise ValueError("reclassify needs a scope: import_job_id and/or loaded_on_or_before (never table-wide)")', "return '', {}", (BOOK, "reclassify")),
    ("remembered sheets skip the dialog with a new sheet", "apps/api/app/services/imports/shipment_field_mapping.py",
     'return present, not changes["new"], changes', "return present, True, changes", (BOOK, "new_sheet or renamed")),
    ("widget accepts another tenant's or a missing saved report", "apps/api/app/api/v1/endpoints/dashboards.py",
     "    if report_id is None or (current is not None and int(report_id) == int(current)):\n        return",
     "    return", ("tests/test_batch2_api_minors.py", "another_tenants")),
    ("per-week report without dates is stored", "apps/api/app/api/v1/endpoints/saved_reports.py",
     "if checked.needs_date_range:", "if False:", ("tests/test_batch2_api_minors.py", "per_week")),
    ("port code XXX accepted", "apps/api/app/api/v1/endpoints/shipping_water.py",
     'if not re.fullmatch(r"[A-Z]{2}[A-Z0-9]{3}", code):', 'if not re.fullmatch(r"[A-Z0-9]{3,16}", code):', ("tests/test_batch2_api_minors.py", "locode")),
    ("raw NaN body is a 500", "apps/api/app/main.py",
     "@app.exception_handler(RequestValidationError)", "# handler removed", ("tests/test_batch2_api_minors.py", "nan_body")),
    ("cleanup script: the dry run can write", "apps/api/scripts/ops/remove_leaked_test_shipment_facts.py",
     'db.execute(text("SET TRANSACTION READ ONLY"))', "pass", ("tests/test_batch2_aud_pari_cleanup.py", "dry_run")),
    ("cleanup script: apply ignores the expected count", "apps/api/scripts/ops/remove_leaked_test_shipment_facts.py",
     "if len(rows) != expect_count:", "if False:", ("tests/test_batch2_aud_pari_cleanup.py", "wrong_database")),
    ("cleanup script: apply ignores the database name", "apps/api/scripts/ops/remove_leaked_test_shipment_facts.py",
     "if current != expect_db:", "if False:", ("tests/test_batch2_aud_pari_cleanup.py", "wrong_database")),
]


def main() -> int:
    only = sys.argv[1:]
    results = []
    for label, rel, old, new, selector in MUTATIONS:
        if only and not any(o in label for o in only):
            continue
        path = ROOT / rel
        original = path.read_bytes()
        text = original.decode("utf-8")
        if "\r\n" in text:  # the working copy may be CRLF (autocrlf): match the file's own line endings
            old, new = old.replace("\n", "\r\n"), new.replace("\n", "\r\n")
        if old not in text:
            results.append((label, "MUTATION TEXT NOT FOUND"))
            continue
        try:
            path.write_bytes(text.replace(old, new, 1).encode("utf-8"))
            proc = subprocess.run([sys.executable, str(RUNNER), "-m", "pytest", "-q", "-p", "no:cacheprovider", selector[0], "-k", selector[1]],
                                  cwd=ROOT, capture_output=True, text=True)
            tail = [ln for ln in proc.stdout.strip().splitlines() if ln.strip()][-1:]
            results.append((label, f"exit {proc.returncode}: {tail[0] if tail else proc.stderr[-200:]}"))
        finally:
            path.write_bytes(original)
            assert path.read_bytes() == original, f"RESTORE FAILED for {rel}"
    for label, outcome in results:
        print(f"{label:60s} -> {outcome}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
