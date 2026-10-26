# E2 — common XLSX literal safety

Implementation run `RUN-20261026-N0116-E2-CODEX`, base `40c111f4`.
N-0116 bounded frontier correction; original scope and acceptance remain open.

## Canonical path

| Trigger | Route | Task | Writer | Commit model |
|---|---|---|---|---|
| Ad-hoc report download | POST /reports/export | N/A | report_export.build_xlsx_bytes | In-memory workbook |
| Saved legacy/model/governed report download | GET /reports/saved/{id}/export | N/A | Same writer via applicable query engine | In-memory workbook |

No fact/import writer or competing steward action applies. Search of app callers
finds the common report_exports endpoint as this writer's production caller.
Other workbook exporters are outside this bounded finding, not declared safe by
this unit.

## Reproduction and correction

Regressions were written before production edits. `failed-before.txt` records
four failures / ten passes: formula-looking cover titles and labels inferred as
formula cells, #N/A inferred as an error cell, and the actual authenticated HTTP
export path doing the same. Numeric/boolean/missing checks already passed.

The existing writer now explicitly marks every string-valued cell as a string
before serialization. This covers cover titles, headers, labels and scalar
strings while preserving actual numbers, booleans and missing values. There is
no duplicate exporter, escaping prefix added to user text, new library, query
change or commercial amount change.

## Validation

- Root focused suite: 39 passed, including E1 regressions, report helpers,
  saved fixed-window export/delivery and fourteen new XLSX checks.
- Separate Astra security/verification suite: 30 passed; extra twelve-case
  XLSX/XML probe confirms literal strings, preserved numeric/boolean types and
  no formula nodes or external relationships. Final hashes/report are in
  VERIFY_ASTRA.md and its source manifest.
- Real bearer HTTP integration uses two-tenant cip_test fixtures under one
  outer rollback. Ad-hoc, saved legacy and saved multi-measure model reports
  export untrusted fictional labels as strings, retain total913 and expose
  no formula cells. It is API integration, not browser smoke.
- Full API/web, lint, typecheck and isolated-build results are recorded in
  final-summary.json when complete. Do not relabel pending runs as passes.
- Existing openpyxl behavior normalizes leading carriage returns to linefeeds;
  the independent reviewer compared the old exporter and found the same behavior.
  E2 establishes literal typing, not byte-for-byte arbitrary-text roundtrip.

## Scope and authority

Only report_export.py and the focused test module change product/test source.
No schema change, new identity/grant, production connection, API/worker restart,
deployment, main change or acceptance. Supported lease/stage events restore
N-0116 implementation ownership; protected ledger history is never edited.

E3 preparation uses a separately labelled rolled-back audit probe of the existing
scheduler. Any result is investigation evidence, not an E2 fix or a production
cross-tenant leak claim. The next execution unit is E3 background tenant/recipient
context, then E4 saved-query fidelity. Remaining original E1–E10 requirements
and genuine business/security decisions are preserved.
