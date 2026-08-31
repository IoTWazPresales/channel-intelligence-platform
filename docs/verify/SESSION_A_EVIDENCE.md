# VERIFY Session A — automated evidence only

**Date:** 2026-08-30  
**Branch:** `docs/verify-debt-runbook` @ `0f0f611`  
**Session scope:** Units **6f**, **7**, **15B** — automated checks per `docs/VERIFY_DEBT_RUNBOOK.md`  
**Database:** No database connections. `ALLOW_TESTS_ON_DEV_DB` unset. No writes to `cip` or `cip_test`.  
**Compute-from-history:** Not executed (writes; deferred to Session F).

**Status:** Evidence capture only. **No unit is PASS, closed, or verified.** Only Opus CONSULT may issue `VERDICT: PASS`.

---

## Unit 6f — D-040 distributor attribution

### Command

```text
cd apps/api
.\.venv\Scripts\activate.ps1
# ALLOW_TESTS_ON_DEV_DB unset
pytest tests/test_lineup_distributor_attribution.py -v
```

### Exit status

`0`

### Printed output (verbatim)

```text
============================= test session starts =============================
platform win32 -- Python 3.12.8, pytest-8.4.2, pluggy-1.6.0 -- C:\Users\warren_eliason\channel-intelligence-platform\apps\api\.venv\Scripts\python.exe
cachedir: .pytest_cache
CIP_AUTH_MODE pin='stub' (conftest setdefault stub; not a fix)
rootdir: C:\Users\warren_eliason\channel-intelligence-platform\apps\api
configfile: pytest.ini
plugins: anyio-4.13.0
collecting ... collected 10 items

tests/test_lineup_distributor_attribution.py::test_sole_exact_offers_accept_when_null_dist PASSED [ 10%]
tests/test_lineup_distributor_attribution.py::test_sole_exact_confirms_matching_proposed PASSED [ 20%]
tests/test_lineup_distributor_attribution.py::test_multi_dist_leaves_proposed_when_present PASSED [ 30%]
tests/test_lineup_distributor_attribution.py::test_absent_proposed_sets_conflict_keeps_semantics PASSED [ 40%]
tests/test_lineup_distributor_attribution.py::test_no_ships_noop PASSED  [ 50%]
tests/test_lineup_distributor_attribution.py::test_sole_dap_helper_unique_within_tol PASSED [ 60%]
tests/test_lineup_distributor_attribution.py::test_sole_dap_helper_ambiguous_when_two_within_tol PASSED [ 70%]
tests/test_lineup_distributor_attribution.py::test_phase2_dap_confirms_when_multi_exact_qty PASSED [ 80%]
tests/test_lineup_distributor_attribution.py::test_phase2_dap_conflict_when_proposed_differs PASSED [ 90%]
tests/test_lineup_distributor_attribution.py::test_phase2_dap_offer_when_null_dist PASSED [100%]

============================= 10 passed in 3.21s ==============================
```

### Summary line

`============================= 10 passed in 3.21s ==============================`

### Contract coverage

| Contract | Covered by this run? | Notes |
|----------|---------------------|-------|
| **D-040** Phase-1 confirmer exact-qty transitions (`token_proposed` → `shipment_confirmed` / `conflict`; no auto-clear) | **Partial** | `_evaluate_token_group` logic only; mocked `SimpleNamespace` lines, no DB |
| **D-040** Accept ship-corroborated steward action | **No** | HTTP/UI `accept-ship` endpoint not exercised |
| **D-040** Soft-clear distributor | **No** | `soft_clear` service path not in this test file |
| **D-040** Steward override / review list | **No** | API + `DistributorAttributionReviewSection` not exercised |
| **D-041** Phase-2 DAP price confirmer | **Partial** | Three `test_phase2_dap_*` tests cover helper/evaluate only |
| **D-038** dual-write on stamp | **No** | Stamp path not in this file |
| Migration `20260807_0010` | **No** | Schema assumed; no DB |

### Still outstanding before Opus can rule

- **Browser:** `/admin/po-management` → Proposed filter → Accept on case **#1016** (or substitute row); soft-clear; conflict row FK retained.
- **Data (read-only `cip`):** `steward_audit_event` rows for `lineup_distributor_attribution_*`; line status distribution.
- **Optional write on `cip_test`:** End-to-end Accept/confirm if read-only insufficient for Opus.

---

## Unit 7 — BACKLOG-068 Shipping lineup-quarter strip

### Command

```text
cd apps/api
.\.venv\Scripts\activate.ps1
# ALLOW_TESTS_ON_DEV_DB unset
pytest tests/test_inbound_lineup_quarter.py -v
```

### Exit status

`0`

### Printed output (verbatim)

```text
============================= test session starts =============================
platform win32 -- Python 3.12.8, pytest-8.4.2, pluggy-1.6.0 -- C:\Users\warren_eliason\channel-intelligence-platform\apps\api\.venv\Scripts\python.exe
cachedir: .pytest_cache
CIP_AUTH_MODE pin='stub' (conftest setdefault stub; not a fix)
rootdir: C:\Users\warren_eliason\channel-intelligence-platform\apps\api
configfile: pytest.ini
plugins: anyio-4.13.0
collecting ... collected 12 items

tests/test_inbound_lineup_quarter.py::test_lifecycle_bucket_taxonomy PASSED [  8%]
tests/test_inbound_lineup_quarter.py::test_awaiting_pod_days_shipped_without_pod PASSED [ 16%]
tests/test_inbound_lineup_quarter.py::test_awaiting_pod_days_null_when_landed PASSED [ 25%]
tests/test_inbound_lineup_quarter.py::test_slip_computation PASSED       [ 33%]
tests/test_inbound_lineup_quarter.py::test_slipped_out_and_in PASSED     [ 41%]
tests/test_inbound_lineup_quarter.py::test_resolve_plan_quarter_no_po PASSED [ 50%]
tests/test_inbound_lineup_quarter.py::test_resolve_plan_quarter_unattributed_po PASSED [ 58%]
tests/test_inbound_lineup_quarter.py::test_resolve_plan_quarter_line_match PASSED [ 66%]
tests/test_inbound_lineup_quarter.py::test_resolve_plan_quarter_single_case_fallback PASSED [ 75%]
tests/test_inbound_lineup_quarter.py::test_resolve_plan_quarter_multi_case_ambiguous PASSED [ 83%]
tests/test_inbound_lineup_quarter.py::test_enrich_fact_lineup_fields PASSED [ 91%]
tests/test_inbound_lineup_quarter.py::test_accumulate_landed_this_quarter_vs_plan_landed PASSED [100%]

============================= 12 passed in 2.21s ==============================
```

### Summary line

`============================= 12 passed in 2.21s ==============================`

### Contract coverage

| Contract | Covered by this run? | Notes |
|----------|---------------------|-------|
| **BACKLOG-068** `landed_this_quarter_units` vs `shipped_not_landed_units` separation | **Partial** | `test_accumulate_landed_this_quarter_vs_plan_landed` — pure Python accumulator |
| **BACKLOG-068** PvE fill rate untouched | **No** | No PvE / fill-rate test in this file |
| **SH-01** lifecycle buckets | **Partial** | `test_lifecycle_bucket_taxonomy` only |
| **SH-02** commercial cohorts on fact `pod_date` | **No** | `shipping_commercial_kpis.py` not exercised |
| API `GET /shipping/lineup-quarter-summary` | **No** | Async read model + DB not hit |
| UI `ShippingLineupQuarterSummary` labels | **No** | Browser not run |

### Still outstanding before Opus can rule

- **Browser:** `/shipping` strip labels (“Shipped (awaiting POD)”, “Landed this quarter”, “Landed (plan quarter)”) vs `COMMERCIAL_SEMANTICS.md`.
- **Browser:** `/plan-vs-executed` fill % unchanged (shipped-basis regression).
- **Data (read-only `cip`):** API spot-check one plan quarter; optional fact-row sanity query.

---

## Unit 15B — B1 forecast compute-from-history

### Command 1 — pytest

```text
cd apps/api
.\.venv\Scripts\activate.ps1
# ALLOW_TESTS_ON_DEV_DB unset
pytest tests/test_demand_forecast_compute.py -v
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
collecting ... collected 3 items

tests/test_demand_forecast_compute.py::test_resolve_forecast_tenant_id_never_none PASSED [ 33%]
tests/test_demand_forecast_compute.py::test_velocity_inserts_default_tenant_not_none PASSED [ 66%]
tests/test_demand_forecast_compute.py::test_compute_from_history_passes_tenant_and_skip_overrides PASSED [100%]

============================== 3 passed in 1.68s ==============================
```

### Summary line (pytest)

`============================== 3 passed in 1.68s ==============================`

### Command 2 — vitest

```text
cd repo root
$env:ESLINT_USE_FLAT_CONFIG="false"
pnpm --filter @cip/web exec vitest run "src/app/(app)/forecasts/page.test.tsx" --reporter=verbose
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

 ✓ src/app/(app)/forecasts/page.test.tsx > ForecastsPage 15B > shows Compute from history as the primary CTA and posts confirm 382ms

 Test Files  1 passed (1)
      Tests  1 passed (1)
   Start at  18:46:32
   Duration  28.00s (transform 361ms, setup 3.06s, collect 13.52s, tests 383ms, environment 6.16s, prepare 1.22s)
```

### Summary lines (vitest)

```text
 Test Files  1 passed (1)
      Tests  1 passed (1)
```

### Contract coverage

| Contract | Covered by this run? | Notes |
|----------|---------------------|-------|
| **B1-07** forecast never merged into actuals | **Partial** | `test_compute_from_history_passes_tenant_and_skip_overrides` asserts `never_merges_actuals` flag on orchestrator return; mocked session, no real tables |
| **B1-04** Compute-from-history primary CTA | **Partial** | Vitest mocks `apiPost`; confirms CTA label + POST shape with `confirm: true` |
| **B1-04** paste/add remain overrides only | **Partial** | Vitest asserts Add override + Paste override buttons exist; does not exercise override flows |
| `tenant_id` never NULL on inserts | **Partial** | Mocked `pg_insert` kwargs in `test_velocity_inserts_default_tenant_not_none` |
| Velocity + analogue provenance JSON on real rows | **No** | No DB; no `provenance_json` assertion on persisted rows |
| **B1-01** rollup / grid display after compute | **No** | Grid mocked in vitest |
| Live `POST /forecasts/compute-from-history` | **No** | Explicitly excluded this session (writes) |

### Still outstanding before Opus can rule

- **Browser on `cip_test`:** `/forecasts` Compute from history end-to-end (with both sync URLs overridden).
- **Data on `cip_test`:** `SELECT count(*) FROM fact_demand_forecast WHERE tenant_id IS NULL` = 0; method + `provenance_json` on new rows; confirm sell-out/CST tables untouched.

---

## Session A aggregate

| Unit | Automated result | Failures |
|------|------------------|----------|
| **6f** | 10/10 pytest passed | None |
| **7** | 12/12 pytest passed | None |
| **15B** | 3/3 pytest + 1/1 vitest passed | None |

**All Session A automated commands exited 0.** This is necessary but not sufficient for VERIFY debt clearance.
