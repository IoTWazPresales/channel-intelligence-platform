# VERIFY Session B — automated evidence only

**Date:** 2026-08-30  
**Branch:** `docs/verify-debt-runbook` @ `d5d3046` (evidence commit pending)  
**Session scope:** Units **12**, **B4 (15C)** — automated checks per `docs/VERIFY_DEBT_RUNBOOK.md`  
**Database:** No database connections. `ALLOW_TESTS_ON_DEV_DB` unset. No writes to `cip` or `cip_test`.  
**Excluded:** Live create-case, export-apply against DB, browser smoke.

**Status:** Evidence capture only. **No unit is PASS, closed, or verified.** Only Opus CONSULT may issue `VERDICT: PASS`.

---

## Path verification (register vs tree)

All runbook paths exist at the stated locations — **no stale-path correction required.**

| Register path | Resolved path | Exists |
|---------------|---------------|--------|
| `tests/test_commercial_tenant_profile_p6_persistence.py` | `apps/api/tests/test_commercial_tenant_profile_p6_persistence.py` | Yes |
| `tests/test_lineup_export_apply.py` | `apps/api/tests/test_lineup_export_apply.py` | Yes |
| `tests/test_product_master_pipeline_retired.py` | `apps/api/tests/test_product_master_pipeline_retired.py` | Yes |
| `tests/test_promo_plan_builder.py` | `apps/api/tests/test_promo_plan_builder.py` | Yes |
| `promotions/promoPlanDraftMerge.test.ts` | `apps/web/src/app/(app)/promotions/promoPlanDraftMerge.test.ts` | Yes |

`test_lineup_export_apply.py` uses `tmp_path` + `monkeypatch` only (no PostgreSQL).

---

## Unit 12 — P6 polish (BACKLOG-026 + Settings export)

**Unit 11 dependency:** Unit 12 VERIFY requires **Unit 11 S-rows (S1–S14) still PASS** with no regression (`docs/VERIFY_DEBT_RUNBOOK.md`). Session B automated evidence does **not** grade steward S-rows; that remains Session E + Opus VERIFY.

### Command 1 — pytest (three files)

```text
cd apps/api
.\.venv\Scripts\activate.ps1
# ALLOW_TESTS_ON_DEV_DB unset
pytest tests/test_commercial_tenant_profile_p6_persistence.py tests/test_lineup_export_apply.py tests/test_product_master_pipeline_retired.py -v
```

### Exit status (pytest)

`0`

### Printed output — pytest (verbatim)

```text
============================= test session starts =============================
platform win32 -- Python 3.12.8, pytest-8.4.2, pluggy-1.6.0 -- C:\Users\warren_eliason\channel-intelligence-platform\apps\api\.venv\Scripts\python.exe
cachedir: .pytest_cache
CIP_AUTH_MODE pin='stub' (conftest setdefault stub; not a fix)
rootdir: C:\Users\warren_eliason\channel-intelligence-platform\apps\api
configfile: pytest.ini
plugins: anyio-4.13.0
collecting ... collected 15 items

tests/test_commercial_tenant_profile_p6_persistence.py::test_load_overrides_missing_file_returns_empty PASSED [  6%]
tests/test_commercial_tenant_profile_p6_persistence.py::test_save_then_load_roundtrip PASSED [ 13%]
tests/test_commercial_tenant_profile_p6_persistence.py::test_save_rejects_invalid_value PASSED [ 20%]
tests/test_commercial_tenant_profile_p6_persistence.py::test_save_drops_unknown_keys_and_empty_values PASSED [ 26%]
tests/test_commercial_tenant_profile_p6_persistence.py::test_profile_snapshot_merges_overrides_over_defaults PASSED [ 33%]
tests/test_commercial_tenant_profile_p6_persistence.py::test_tenant_id_sanitized_for_filesystem_safety PASSED [ 40%]
tests/test_commercial_tenant_profile_p6_persistence.py::test_default_tenant_profile_snapshot_backward_compatible PASSED [ 46%]
tests/test_commercial_tenant_profile_p6_persistence.py::test_lineup_export_columns_roundtrip_and_reject_unknown_field PASSED [ 53%]
tests/test_lineup_export_apply.py::test_half_year_1h PASSED              [ 60%]
tests/test_lineup_export_apply.py::test_half_year_2h PASSED              [ 66%]
tests/test_lineup_export_apply.py::test_csv_header PASSED                [ 73%]
tests/test_lineup_export_apply.py::test_xlsx_workbook_sheets PASSED      [ 80%]
tests/test_lineup_export_apply.py::test_xlsx_draft_sheet_uses_tenant_column_map PASSED [ 86%]
tests/test_product_master_pipeline_retired.py::test_process_product_master_handler_raises PASSED [ 93%]
tests/test_product_master_pipeline_retired.py::test_process_import_job_sync_refuses_product_master PASSED [100%]

============================= 15 passed in 6.62s ==============================
```

### Summary line (pytest)

`============================= 15 passed in 6.62s ==============================`

### Command 2 — pnpm test:web

```text
cd repo root
$env:ESLINT_USE_FLAT_CONFIG="false"
pnpm test:web
```

### Exit status (pnpm test:web)

`1`

### Printed output — pnpm test:web (header + summary + failures; full log ~12,022 lines)

Full console log captured locally at `apps/api/.tmp_session_b_unit12_vitest_all.txt` (not committed).

```text
> channel-intelligence-platform@ test:web C:\Users\warren_eliason\channel-intelligence-platform
> pnpm --filter @cip/web test


> @cip/web@0.0.1 test C:\Users\warren_eliason\channel-intelligence-platform\apps\web
> vitest run

node.exe : [33mThe CJS build of Vite's Node API is deprecated. See 
https://vite.dev/guide/troubleshooting.html#vite-cjs-node-api-deprecated for more details.[39m
...

 RUN  v2.1.9 C:/Users/warren_eliason/channel-intelligence-platform/apps/web

 Test Files  2 failed | 96 passed (98)
      Tests  20 failed | 525 passed (545)
   Start at  18:51:57
   Duration  188.57s (transform 26.15s, setup 214.59s, collect 1388.35s, tests 360.82s, environment 430.62s, prepare 145.31s)

C:\Users\warren_eliason\channel-intelligence-platform\apps\web:
ERR_PNPM_RECURSIVE_RUN_FIRST_FAIL @cip/web@0.0.1 test: `vitest run`
Exit status 1
ELIFECYCLE Command failed with exit code 1.
```

### Summary lines (vitest)

```text
 Test Files  2 failed | 96 passed (98)
      Tests  20 failed | 525 passed (545)
```

### Failed tests (verbatim FAIL lines from log)

```text
 FAIL  src/app/(app)/admin/customers/page.test.tsx > AdminCustomersPage phase1 behaviors > submits add location and add contact from drawer
Error: Test timed out in 5000ms.

 FAIL  src/app/(app)/admin/imports/page.test.tsx > AdminImportsPage historical_lineup Apply button post-success behavior > Apply button appears after validate succeeds and a file is present
TestingLibraryElementError: Unable to find role="button" and name `/Apply validated file/i`

 FAIL  src/app/(app)/admin/imports/page.test.tsx > AdminImportsPage historical_lineup Apply button post-success behavior > Apply button disappears and apply success Alert appears after apply succeeds

 FAIL  src/app/(app)/admin/imports/page.test.tsx > AdminImportsPage historical_lineup Apply button post-success behavior > validate success Alert shows generic message and does not show apply Alert

 FAIL  src/app/(app)/admin/imports/page.test.tsx > AdminImportsPage historical_lineup mapping review panel > mapping review panel appears and shows source columns after validate

 FAIL  src/app/(app)/admin/imports/page.test.tsx > AdminImportsPage historical_lineup mapping review panel > re-validate with corrections sends mapping_override in FormData

 FAIL  src/app/(app)/admin/imports/page.test.tsx > AdminImportsPage historical_lineup mapping review panel > apply with edits sends mapping_override in FormData

 FAIL  src/app/(app)/admin/imports/page.test.tsx > AdminImportsPage historical_lineup mapping review panel > start over clears the mapping review panel

 FAIL  src/app/(app)/admin/imports/page.test.tsx > AdminImportsPage Phase 3B — mapping review label clarity > mapping review shows "Product identity (SKU)" label not bare "SKU"

 FAIL  src/app/(app)/admin/imports/page.test.tsx > AdminImportsPage Phase 3B — mapping review label clarity > mapping review shows "Base unit (descriptor)" as a target option

 FAIL  src/app/(app)/admin/imports/page.test.tsx > AdminImportsPage Phase 3B — mapping review label clarity > regression: sku_raw stays unmapped when field_mapping has no sku_raw

 FAIL  src/app/(app)/admin/imports/page.test.tsx > AdminImportsPage Phase 3B — diagnostic summary chips > diagnostic summary chips appear with code counts after validate returns rows

 FAIL  src/app/(app)/admin/imports/page.test.tsx > AdminImportsPage Phase 3C — quality review panel > quality review panel shows apply-ready badge when no blocking errors exist

 FAIL  src/app/(app)/admin/imports/page.test.tsx > AdminImportsPage Phase 3C — quality review panel > quality review panel groups unknown customer tokens with row counts

 FAIL  src/app/(app)/admin/imports/page.test.tsx > AdminImportsPage Phase 3C — quality review panel > apply button shows inline confirmation when unresolved customers exist, then applies on confirm

 FAIL  src/app/(app)/admin/imports/page.test.tsx > AdminImportsPage Sub-pass A — loaded lineup records > loaded lineup section appears after apply and shows line data

 FAIL  src/app/(app)/admin/imports/page.test.tsx > AdminImportsPage Sub-pass A — loaded lineup records > loaded lineup section shows empty state when no lines returned

 FAIL  src/app/(app)/admin/imports/page.test.tsx > AdminImportsPage Sub-pass A — loaded lineup records > View apply job link appears in success alert with correct job id

 FAIL  src/app/(app)/admin/imports/page.test.tsx > AdminImportsPage Sub-pass A — loaded lineup records > unresolved customer token chips appear in loaded lineup section when lines have unknown_customer

 FAIL  src/app/(app)/admin/imports/page.test.tsx > AdminImportsPage Sub-pass A — loaded lineup records > unresolved customer token section is absent when all customers are resolved
```

**Note:** 19 of 20 failures are in `admin/imports/page.test.tsx` (historical_lineup / Import Centre UX). One failure is unrelated timeout in `admin/customers/page.test.tsx`. Failures may indicate **Unit 11 import-parity regression** or **stale tests** after `CanonicalColumnMappingPanel` migration — Opus must judge; Cursor does not.

### Contract coverage — Unit 12

| Contract | Covered by this run? | Notes |
|----------|---------------------|-------|
| **BACKLOG-026** PM dual pipeline retired | **Partial** | `test_product_master_pipeline_retired.py` — raises only; not Import Centre E2E |
| **P6** lineup export sheet titles in Settings | **Partial** | `test_lineup_export_columns_roundtrip` — file-based tenant profile, not `/settings` UI |
| **P6** `lineup_export_columns` / XLSX sheet names | **Partial** | `test_xlsx_draft_sheet_uses_tenant_column_map` — in-memory xlsx via `tmp_path` |
| **Unit 11 S-rows** no regression | **Not assessed** | `pnpm test:web` failures in `imports/page.test.tsx` are a **negative signal** for HL/import UX tests, not S1–S14 grading |
| Settings UI persist sheet titles | **No** | Browser `/settings` not run |
| PM Import Centre workflow smoke | **No** | Browser not run |

### Still outstanding before Opus can rule — Unit 12

- **Browser:** `/settings` — net requirement + draft lineup sheet title fields save/reload.
- **Browser:** `/admin/imports` PM job still uses Import Centre workflow (not dead generic pipeline).
- **Unit 11 dependency:** Opus S1–S14 table for shipment + PM/HL mapping must PASS independently (Session E).
- **Investigate:** 19 failing `admin/imports/page.test.tsx` cases — may block claiming “no regression from Unit 11” until explained (test drift vs product bug).

---

## Unit B4 (15C) — Promo planner

### Command 1 — pytest

```text
cd apps/api
.\.venv\Scripts\activate.ps1
# ALLOW_TESTS_ON_DEV_DB unset
pytest tests/test_promo_plan_builder.py -v
```

### Exit status (pytest)

`0`

### Printed output — pytest (verbatim)

```text
============================= test session starts =============================
platform win32 -- Python 3.12.8, pytest-8.4.2, pluggy-1.6.0 -- C:\Users\warren_eliason\channel-intelligence-platform\apps\api\.venv\Scripts\python.exe
cachedir: .pytest_cache
CIP_AUTH_MODE pin='stub' (conftest setdefault stub; not a fix)
rootdir: C:\Users\warren_eliason\channel-intelligence-platform\apps\api
configfile: pytest.ini
plugins: anyio-4.13.0
collecting ... collected 4 items

tests/test_promo_plan_builder.py::test_build_promo_plan_draft_case_not_found PASSED [ 25%]
tests/test_promo_plan_builder.py::test_derive_planned_skips_missing_srp PASSED [ 50%]
tests/test_promo_plan_builder.py::test_build_promo_plan_draft_emits_per_line_mac_and_units PASSED [ 75%]
tests/test_promo_plan_builder.py::test_create_case_from_promo_draft_carries_edits_and_skips_cover_persist PASSED [100%]

============================== 4 passed in 2.31s ==============================
```

### Summary line (pytest)

`============================== 4 passed in 2.31s ==============================`

**Note:** `test_create_case_from_promo_draft_carries_edits_and_skips_cover_persist` uses `FakeSession` — **no database write**; exercises D-053/D-054 logic in process only.

### Command 2 — vitest

```text
cd repo root
$env:ESLINT_USE_FLAT_CONFIG="false"
pnpm --filter @cip/web exec vitest run "src/app/(app)/promotions/promoPlanDraftMerge.test.ts" --reporter=verbose
```

### Exit status (vitest)

`0`

### Printed output — vitest (verbatim)

```text
node.exe : [33mThe CJS build of Vite's Node API is deprecated. See 
https://vite.dev/guide/troubleshooting.html#vite-cjs-node-api-deprecated for more details.[39m
At C:\Users\warren_eliason\AppData\Roaming\npm\pnpm.ps1:24 char:5
+     & "node$exe"  "$basedir/node_modules/pnpm/bin/pnpm.cjs" $args
+     ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : NotSpecified: ([33mThe CJS bu...e details.[39m:String) [], RemoteException
    + FullyQualifiedErrorId : NativeCommandError
 

 RUN  v2.1.9 C:/Users/warren_eliason/channel-intelligence-platform/apps/web

 ✓ src/app/(app)/promotions/promoPlanDraftMerge.test.ts > promoPlanDraftMerge > hydrates suggestions as clean working values
 ✓ src/app/(app)/promotions/promoPlanDraftMerge.test.ts > promoPlanDraftMerge > refresh does not clobber dirty MAC; other cells update
 ✓ src/app/(app)/promotions/promoPlanDraftMerge.test.ts > promoPlanDraftMerge > reset restores suggested MAC and clears dirty

 Test Files  1 passed (1)
      Tests  3 passed (3)
   Start at  18:51:57
   Duration  21.27s (transform 163ms, setup 4.51s, collect 91ms, tests 7ms, environment 9.90s, prepare 1.70s)
```

### Summary lines (vitest)

```text
 Test Files  1 passed (1)
      Tests  3 passed (3)
```

### Contract coverage — Unit B4

| Contract | Covered by this run? | Notes |
|----------|---------------------|-------|
| **D-051** per-line `build_promo_plan_draft` rows | **Partial** | `test_build_promo_plan_draft_emits_per_line_mac_and_units` — mocked session |
| **D-052** dirty-flag client-owned; refresh merges non-dirty only | **Yes** (unit) | `promoPlanDraftMerge.test.ts` refresh/reset tests |
| **D-053** create-case `lines[]`; `manual` vs `intake_weighted` | **Partial** | `test_create_case_from_promo_draft_*` — FakeSession, no HTTP/DB |
| **D-054** cover override session-only; no `commercial_customer_term` write | **Partial** | Asserted in create_case test via mock; no DB |
| **D-055** editable vs display-only split | **Partial** | `display_only_fields` in build draft test; no MAC popover UI |
| **D-056** tenant `lineup_export_columns` column-mapped export | **No** | Not in these test files |
| **BACKLOG-094** closed criteria (planner grid, dirty refresh, create-case) | **Partial** | Logic/unit only |

### Still outstanding before Opus can rule — Unit B4

- **Browser on `cip_test`:** `/promotions` — Build grid, dirty MAC/units survive Refresh, MAC popover legs, Create case.
- **Data on `cip_test`:** `cost_source` on new case lines after create; read-only tenant export column map on `cip`.
- **Export:** Draft lineup XLSX headers vs D-056 tenant profile (not run — would write/apply).

---

## Session B aggregate

| Unit | Check | Result | Failures |
|------|-------|--------|----------|
| **12** | pytest (3 files) | **Passed** | 0 / 15 |
| **12** | `pnpm test:web` | **Failed** | 20 / 545 (2 files) |
| **B4** | pytest `test_promo_plan_builder.py` | **Passed** | 0 / 4 |
| **B4** | vitest `promoPlanDraftMerge.test.ts` | **Passed** | 0 / 3 |

**No unit is PASS, closed, or verified.** Session B is input for Opus CONSULT only.

---

## Run 2026-08-31 — Unit 12 browser VERIFY gap (Settings export sheet titles)

**Collection timestamp:** 2026-08-31 (Monday), ~13:10–13:55 UTC+2  
**Branch:** `main` @ `15ab61ab99bf5db6e37691dfb43334b08aea220c`  
**Origin:** `http://127.0.0.1:3000` (cursor-ide-browser, serial)  
**Write target:** File persistence only (`tenant_profiles/default.json` on API host) — **no DB writes**  
**API:** `session_d_run_api.py cip_test` during mixed session; tenant profile file lives under `apps/api/storage/uploads/` (gitignored)  
**Evidence only — no PASS verdict.**

### Browser journey — `/settings`

1. **Edit** (MUI `browser_type` with `clear:true`, `slowly:true` — `browser_fill` does not fire React `onChange`):
   - `tenant-profile-export-net-req-sheet` → **`SESSION-B-NET-REQ`**
   - `tenant-profile-export-draft-sheet` → **`SESSION-B-DRAFT`**
2. **Save:** `data-testid="tenant-profile-save"` (ref **e178** after scroll).
3. **Reload** `/settings` — after tenant profile query completes, fields show **`SESSION-B-NET-REQ`** / **`SESSION-B-DRAFT`** (not defaults).

**Screenshots:** `docs/verify/artifacts/session-b-12-before-save-final.png` (alias of `page-2026-08-31T11-51-12-002Z.png`), `session-b-12-after-reload.png`, `session-b-12-before-save.png`

### File persistence (API cwd `apps/api`)

```text
tenant_profile_path storage\uploads\tenant_profiles\default.json
{
  "lineup_export_draft_sheet": "SESSION-B-DRAFT",
  "lineup_export_net_requirement_sheet": "SESSION-B-NET-REQ",
  ...
}
```

### Automation notes (not verdicts)

| Issue | Code | Mitigation used |
|-------|------|-----------------|
| `browser_fill` skips React state | `AUTOMATION_LIMIT` | `browser_type` + `clear` + `slowly` |
| Early reload snapshot shows defaults before query settles | `TIMING` | Wait for full snapshot (418 refs) or scroll + screenshot |
| Save button ref off-screen in large snapshot | `AUTOMATION_LIMIT` | Scroll + ref `e178` click |

### Unit 12 gap status

| Check | Captured? |
|-------|-----------|
| UI edit export sheet titles | **Yes** |
| Save tenant profile | **Yes** |
| Reload persistence in UI | **Yes** |
| `tenant_profiles/default.json` on disk | **Yes** |
