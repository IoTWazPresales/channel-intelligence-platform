# E2 verification — VERIFIED_WITH_LIMITATIONS

Review run `RUN-20261026-N0116-E2-VER-ASTRA`; implementation run `RUN-20261026-N0116-E2-CODEX` (supported lease/stage events 2775/2776 inspected). Separate reviewing agent GPT-6-Astra; implementation root GPT-6.1-Sol (actual invocation provenance supplied by orchestrator, not independently measured runtime model attestation). Completed 26 October 2026.

Bounded scope: nine-line string cell typing change in `apps/api/app/services/report_export.py`, new `test_report_xlsx_literal_safety.py`, and canonical authenticated report export callers. No product/ledger/memory edits, production connection, services, migrations or identity changes by reviewer.

**Verdict: VERIFIED_WITH_LIMITATIONS for bounded E2. No unresolved blocking defect found in the final change.** This is neither N-0116 acceptance nor original-scope/R3/runtime-attestation completion. Applied SR-001 application-security and GOV-008 verification contracts; retained CR-008 correctness discipline. Reused earlier mandatory onboarding and refreshed CURRENT, work item, HEAD and relevant governance provenance.

## Canonical path and security boundary

Compared the nine added product lines with HEAD `40c111f4da21a7597dcf982f4b9fe6ca3e322ede` on `feat/ns-2-brief-nav-collapse`. The user-controlled report title and entity labels cross into XLSX through `report_exports.py::_export_from_result`, which is shared by ad-hoc `/reports/export` and saved `/reports/saved/{id}/export`. Saved legacy and model definitions follow their existing query paths before this same serializer. No duplicate exporter or query selection change was introduced.

The credible injection precondition is control of report titles or an exported text label. The former workbook builder allowed openpyxl to classify leading `=` strings as formula cells; error-looking text such as `#N/A` became an error cell. Root's retained `failed-before.txt` shows four failures, including an actual authenticated export. That pre-change regression log was inspected, not re-executed by this reviewer.

Final `report_export.py:62–69` marks every string-valued cell in both worksheets as type `s` immediately before saving. Installed primary source `openpyxl/cell/cell.py::_bind_value` confirms the initial formula/error inference; `openpyxl/cell/_writer.py` confirms type `s` emits `inlineStr` text, whereas formula XML requires type `f`. The pass covers title, header, scalar, data, and invariant cells and does not mutate integer, float, boolean or missing values. `_cell`, workbook layout/style, existing amounts and PDF implementation remain unchanged. Reports do not intentionally construct formulas in this writer.

## Independently executed evidence

```powershell
apps/api/.venv/Scripts/python.exe apps/api/scripts/db_on.py pytest tests/test_report_xlsx_literal_safety.py tests/test_report_export.py tests/test_dashboard_v2_export.py
```

**30 passed in 31.05s, exit0**, `astra_focused.txt`. Fourteen new cases comprise eight label variants, five scalar-type checks and one real authenticated HTTP workflow. Related tests cover existing workbook/vintage/PDF/fixed-window export contracts and delivery helpers. No broad suite was repeated.

The new label matrix round-trips formula-like, error-like, tab-prefixed and ordinary strings through title, header, row and scalar positions, both normal and data_only readers. It asserts negative/fractional/integer cells remain numeric, boolean stays boolean, missing stays missing, no formula cell exists, worksheet XML has no formula tag and no externalLinks package parts exist. The authenticated fixture exercises ad-hoc, saved legacy and explicitly non-v1-equivalent model report exports, with the same malicious title/customer name, and retains the expected 913 total. Real bearer authentication and SQL run on cip_test; fixture writes/savepoints are under outer rollback. This is API/SQL integration, not browser smoke.

Independent `astra_xlsx_probe.py` adds 12 adversarial cases: WEBSERVICE text, external-workbook reference text, DDE-shaped text, more Excel error literals, CR/LF/space prefixes, XML markup metacharacters, Unicode and multiline text. It verifies literal type, numeric/boolean types and styles, parses every XML/rels document for formula/external-reference elements and external relationships, and compares the prior exporter for the normalization edge below. **12 completed, exit0**; `astra_xlsx_probe_final.txt`. The probe only builds/reads bytes; it does not open Excel, follow URLs or connect to a database.

## Nonblocking finding and limitations

- **MINOR existing serialization limitation:** a leading carriage return (`\r=1+1`) round-trips as line feed (`\n=1+1`). The first extra probe stopped on its exact-text assertion (`astra_xlsx_probe_initial.txt`); a discriminating comparison with the HEAD exporter reproduced identical normalization, with both versions retaining string type. The final probe preserves this observation and verifies no formula/external relationship. E2 therefore preserves literal semantics but does not establish byte-for-byte preservation of every arbitrary text input. No E2 repair is required for this pre-existing behavior; do not claim universal exact text fidelity.
- No spreadsheet desktop application or browser was launched. Evidence proves the serialized workbook contract and openpyxl round trips, not every spreadsheet application's behavior. Other exporter families/CSV, saved sort/grain/date fidelity, schedules and recipient policy remain outside this unit.
- Root's full-suite/lint/typecheck results remain separate implementation evidence; this reviewer independently executed only the approved focused command and pure probe.
- Runtime capabilities and model-identity enforcement remain UNVERIFIED. Invocation model separation is recorded, not promoted into overall R3 completion or an ENFORCED guard claim. Original scope and operator acceptance remain open.
- Reviewer wrote only its audit artifacts. No product, ledger, memory, service, production, migration, role/grant, release or remote changes. Root owns ledger/memory and prefix-preservation closeout. Previously observed missing engineering-rules.mdc remains an onboarding limitation.

## Source provenance

Six material source/test paths are pinned in `astra_source_sha256.json`, observed against HEAD 40c111f4. Rechecked unchanged at finalization in `astra_source_match_closeout.json`.

| Changed path | SHA-256 |
|---|---|
| apps/api/app/services/report_export.py | 5b47d4dad07f8816a1ada89f42960060982a5e6da3e19f6cfb150ef99577d2c1 |
| apps/api/tests/test_report_xlsx_literal_safety.py | 52554c289f564f90e19c6b8cdd923063548f18573d9644decf6c015de4d6fd0b |

