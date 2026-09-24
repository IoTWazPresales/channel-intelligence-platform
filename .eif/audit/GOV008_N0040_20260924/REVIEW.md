# GOV-008 independent review: N-0040 (D-g: sellable BU grain is every dim_product.product_line)

Reviewer: independent GOV-008 verifier, fresh context, separate run from the implementation. Lenses: verification-controller, architecture-specialist, domain-analyst, frontend-engineer, accessibility-specialist. Date: 2026-09-24.
Read: commit 73466a10 (`git show`), n0040/DISCOVERY.md, n0040/prove_n0040_inprocess.py and proof_output.txt, the old-module copies, the source, the tests, cip (read-only), and the running app in my own Chrome tab.
Not read: n0040/IMPL.md.
Independence rung: another session (fresh context) on the same model family. There is no other-model consult. R2, so this rung is enough.

## Criterion 1: hardcoded line sets enumerated and data-driven. PASS

- VERIFIED: the commit removes every set that discovery listed (H1-H9, H11):
  - `CANONICAL_SHEET_BU_CODES`, `DEFAULT_ACZA_TENANT_BU_CODES`, `CANONICAL_PRODUCT_LINES` (the Gaming/Consumer words), `PM_PRODUCT_LINES`, web `TENANT_BU_OPTIONS` and `DEFAULT_TENANT_BU_CODES`.
  - A grep of `apps/` for these names now returns 0 hits. That includes tests and scripts, so nothing references a removed constant.
- VERIFIED: one source replaces them:
  - `apps/api/app/services/catalog/product_lines.py` returns distinct trimmed non-blank `product_line` values plus the null/blank count. It has a 60 s TTL cache that is invalidated in `commit_product_master_sync`.
  - Callers: the resolver (`_bu_codes` with no codes means the sheet and folder tiers do not fire), the archive config (`tenant_bu_codes: None` means the sellable codes are used), `build_bulk_lineup_preview` (loads the codes once when none are given), `lineup_case_parser` (both calls), `lineup_case_product_line`, and the PM job-state `product_lines`.
  - Web: `useProductLines` feeds the dialog's BU options and archive path parsing.
- VERIFIED: my own greps over `apps/api/app` and `apps/web/src` (excluding tests and design-lab):
  - Quoted single codes, `NB|NR` alternations and `NB/NR` or `NB,NR` sequences. The only remaining hits are prose: a docstring at `lineup_po_competition.py:6` "(NB/NR/NV/…)", the docstring at `lineup_bulk_backfill_preview.py:641`, two `dsi_mapping_workflow.py` docstrings "(e.g. NB)", the `InboundShipmentsWorkspace.tsx:615` placeholder "e.g. NB" (H10, which discovery marked optional), and ISO country "NR" (Nauru). None of these is a membership set.
- VERIFIED: the guard test `tests/test_bu_code_literal_guard.py` passes (2 tests).
- VERIFIED live: in my signed-in tab on `/admin/imports`, a JavaScript fetch of `GET /api/v1/catalog/product-lines` with the page's own bearer (not printed) returned status 200 with 14 lines: NB=6848, NX=5173, PF=2049, NR=1910, PT=1311, LM=561, XB=183, PD=93, AI=11, NV=10, NL=8, CB=6, AX=3, AZ=1. `null_product_line_count` = 10, and label = code.

## Criterion 2: NULL product_line reported with count. PASS

- VERIFIED: `ro_sql.py` returned `null_pl=10 | blank_pl=0 | distinct_codes=14` on cip.
- The count appears in three places: the endpoint's `null_product_line_count` (10, live), line 3 of the proof output, and DISCOVERY §3 (row list, test pollution, 1 `cpor_case_line` reference).
- ASSERTED/not observed: I did not see the null count rendered in any UI surface. It exists as API data and as the `nullProductLineCount` field on the hook. The steward clean-up remains deferred, which is correct under D-g.

## Criterion 3: supersession change proven with before/after numbers; repair listed, not applied. PASS (with limitations)

- VERIFIED: the proof is reproducible. I re-ran `prove_n0040_inprocess.py` myself. It connects to cip with `conn.read_only = True` and rolls back. My output (`proof_rerun.txt`) is byte-identical to `proof_output.txt`.
- VERIFIED: the "old" code is the real old code. `old_resolver.py`, `old_period_inference.py` and `old_archive_config.py` are identical to the `73466a10^` versions (`git show … | diff -q`).
- Soundness assessment (architecture and domain lenses):
  - The model is faithful to the pre-change paths. The old folder is staged with the 6-code web/archive set, then resolved on the server with the 4-code default (H3). The new path uses the catalogue codes for both steps.
  - Final BU = manual (the steward/slice `business_unit` from `lineup_parse_options`), else the automatic resolution.
  - The inputs are each case's own persisted lines, sheet, folder and filename.
- Results over all 36 cases:
  - Automatic BU changed: 0. Final BU changed: 0. Old or new final BU differs from the persisted BU: 0.
  - Collision groups: 3 persisted = 3 old = 3 new.
  - Supersession pairs: 7 of 7 unchanged.
  - The filename-fallback token changed in 28 cases. The old values were the invalid words "Gaming" and "Consumer".
  - The effective case product_line inference changed in 3 cases: 131 (9 rows, 1 resolved: Gaming→NR, persisted NB), 141 and 143 (0 rows).
  - Of the case differences from persisted values, 131 is the only one with rows. 141/142/143 are superseded losers with 0 rows.
- VERIFIED: 0 persisted changes can follow.
  - `ensure_case_product_line_from_catalogue` returns early when `case.product_line is not None`.
  - Every persisted case has a product_line: I checked cases 131 and 141-143 directly (NB/NB/NV/PF).
  - `superseded_by_case_id` is persisted and not recomputed.
- VERIFIED: nothing was written to cip.
  - `commercial_lineup_case` has 36 rows. `max(updated_at)` is 2026-08-05 16:03, which is before this node's commit on 2026-09-24.
  - Cases 131 and 141-143 have `updated_at` of 2026-08-02.
  - The "repair" is only the listed diff: `new effective case product_line != persisted`, 4 rows. Nothing was applied.
- Limitations:
  - (a) D-g asked for a proof on a clone. The proof ran in-process against cip read-only. The script's docstring states that CREATE DATABASE is denied to role `cip`. Because nothing is written, a read-only in-process run is at least as safe as a clone. But it is not the clone ceremony that D-g literally asked for.
  - (b) Line resolution uses a synthetic token per persisted `product_id`, not a re-parse of the archive spreadsheets. It proves resolver behaviour on persisted inputs. It does not prove a full re-preview of the archive tree, where lines that never resolved could meet the new, wider sheet/folder tiers.
  - (c) Discovery reported "44 cases". cip has 36. This is a discovery miscount and does not change the conclusion.

## Criterion 4: tests green, tsc 0. PASS

- VERIFIED: pytest on the five listed files against the default cip failed with conftest refusals (21 errors, 22 passed) because two modules are write-capable. This is expected.
- VERIFIED: re-run with `DATABASE_URL`/`DATABASE_URL_SYNC` pointed at the disposable `cip_test`: **43 passed** (`_pytest_cip_test.txt`).
- VERIFIED: vitest on `BulkLineupBackfillDialog.test.tsx` and `lineupBackfillArchivePath.test.ts`: **2 files, 8 tests passed** (`_vitest.txt`).
- VERIFIED: `tsc --noEmit -p apps/web` exit 0, **0 errors** (`_tsc.txt`).

## Criterion 5: UI dialog lists catalogue lines, with neutral copy. PASS (with limitations)

- VERIFIED (rendered, own tab): on Admin > Data & Stewardship (`/admin/imports`), "Bulk historical lineup backfill" opens a dialog labelled by its h2 (`aria-labelledby` resolves to "Bulk historical lineup backfill").
  - The copy reads "Select your Product Lineup root once — all product-line folders are included."
  - The dialog text contains no `NB/NR` code string.
  - The dialog fired `GET /api/v1/catalog/product-lines` → 200 (Resource Timing).
  - "Select archive folder" and "Add individual files" are enabled once codes load. "Run preview" is disabled with nothing staged.
  - Screenshot: dark theme, dialog centred, and the copy is legible.
- UNABLE (rendered): the per-row **BU override select** only exists after files are staged and "Run preview" runs. The preview POST persists a session import job (`persisted: true` in the response contract), and staging needs the OS folder picker. Both break the no-upload/no-write rule, so I did not render the select live.
- Compensating evidence:
  - VERIFIED source: `BulkLineupBackfillDialog.tsx:648-653` builds the options from `buOptionCodes(productLineCodes, buValue)`, where `productLineCodes` comes from `useProductLines`.
  - VERIFIED test: the dialog vitest asserts the options equal `['', 'NB', 'PT', 'LM']` from the mocked endpoint, and that a `PT\2026\Q1` folder is recognised.
  - VERIFIED live: the endpoint returns PT and LM.
- The dialog was closed with Close. I clicked no write controls, and my tab was closed at the end.
- The 390x844 viewport was not attempted. Resize is documented as non-working here, and my tabs were repeatedly detached or closed by the shared tab group.

## Findings (advisory; none blocks acceptance)

1. **Wider sheet/filename token matching (domain).** With 14 codes, a leading tab token or filename token such as `PD`, `AI`, `PT` or `LM` now claims a line.
   - Observed: cases 134/135 have sheet "PD Lineup 13 Feb 25" in a PF folder, and the filename fallback now yields PD.
   - The product tier wins today (63/63 resolved), and the `bu_label_product_mismatch` flag remains. This is only a risk for under-resolved future imports.
   - Case 131 shows the same effect: the filename says NR, the steward chose NB.
   - Suggest: a steward-visible flag when the filename or sheet tier is the deciding tier.
2. **The guard is narrow.** Its regex only catches 3 or more quoted two-letter upper-case codes in a row. It misses 2-code sets, regex alternations (`NB|NR`), lower-case codes, SQL `IN (...)` lists and codes built from strings. My manual greps found none of these today.
3. **Endpoint failure mode (frontend).** "Select archive folder" is disabled only while `isPending`. If the endpoint errors, it becomes enabled with an empty code set, so folder BU segments are silently not recognised. "Add individual files" is never gated.
4. **A11y (pre-existing, not introduced).** The per-row native BU `<select>` (a TextField select without a label) has no accessible name. It is announced only by its value.
5. **Residual prose** (not sets): `lineup_po_competition.py:6` "(NB/NR/NV/…)" and the `InboundShipmentsWorkspace.tsx:615` placeholder "e.g. NB". Optional neutralisation.
6. **Test ergonomics.** `test_catalog_product_lines.py` and `test_lineup_business_unit_resolution.py` need `cip_test`. Running them bare against cip gives conftest errors, not a red build signal.

## Overall verdict: VERIFIED_WITH_LIMITATIONS

All five criteria pass on observed evidence. The limitations:
- the proof ran in-process and read-only, not on a clone;
- it modelled resolution on persisted inputs and did not re-preview the archive tree;
- the per-row BU select was not rendered live, because that needs an upload plus a persisted preview; it is covered by source, vitest and the live endpoint;
- the 390 px viewport was not checked.
