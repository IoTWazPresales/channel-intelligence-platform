# N-0049 IMPL — customer SOH (MAC) check reads CST (BACKLOG-135)

Run: implementation subagent (fresh context), 2026-09-24. Lenses: backend-engineer, analytics-bi-specialist, test-engineering-specialist.
Commit: `3624d7e7` on `feat/ns-2-brief-nav-collapse` (not pushed).

## Finding first: the named "MAC check" did not exist in code
OBSERVATION: `grep -i` over `apps/api/app` for `fact_inventory_customer` / `FactInventoryCustomer` / `mac check` / `soh check`: the inventory fact is read only by `/inventory` CRUD (`endpoints/inventory.py`), `grid_fields.py`, usage counters and `seed_demo.py`. **No CPOR/MAC code read it.** The D-062 check ("customer SOH cost checks derived MAC") was only in docs (`CPOR_SETTLEMENT_SPEC.md` §5/§9.1, D-062, BACKLOG-135). There was therefore no old code path to repoint; the "before" is what any check sourcing `fact_inventory_customer` returns: 0 rows for every pair.
DECISION taken (smallest change that meets the criteria): add the check as a read-only service on CST and expose it on the existing line cost-suggest response. The derived customer×SKU MAC master (§5) is out of scope (BACKLOG-135), so the check compares against the line's stored `cost_basis`.

## Rule (as implemented, `apps/api/app/services/cpor/customer_soh_check.py`)
For customer × product as of date D (the cost-suggest endpoint's existing `as_of` = case created date):
1. period = latest `period_start_date` <= D among `fact_customer_sellthrough` rows with `reported_soh IS NOT NULL`;
2. `soh_units` = SUM(`reported_soh`) over that period's rows (all sites — Game has up to 89 site rows per week);
3. `soh_unit_cost` = `reported_soh`-weighted average of `unit_mac` else `unit_cost` (same preference as CPOR tier-1 cost) over rows carrying a cost;
4. `delta` = stored `cost_basis` − `soh_unit_cost`; reported only, **no tolerance flag** (tolerance is Warren's);
5. flags: `zero_soh` (0 on hand → no weighted cost), `no_soh_cost` (units without any cost field); `vat_basis` passed through unconverted;
6. no CST SOH row → `status: "unavailable"`, `reason: "customer SOH unavailable — no fact_customer_sellthrough row with reported_soh on or before D"`, never zero stock.
CST column facts (read-only cip): `reported_soh` 1,420/1,823 rows, `unit_mac` 548, `unit_cost` 940; all `period_type = weekly`.

## Criteria
1. **PASS** — sources CST `reported_soh` + `unit_mac`/`unit_cost`; latest period per pair as of the check date; rule stated above and in the module docstring. Wired: `apps/api/app/api/v1/endpoints/cpor_cases.py` cost-suggest returns `soh_check`.
2. **PASS** — the check names only `fact_customer_sellthrough` (`source` field, reason text; test asserts the SQL and output never mention `fact_inventory_customer`). Docs: `docs/CPOR_SETTLEMENT_SPEC.md` §9.1 dated note; `docs/BACKLOG.md` BACKLOG-135 status → Partial. D-062 origin note left as history (it is accurate). `/inventory` page copy ("Rows are stored in fact_inventory_customer") is true for that manual CRUD page and is web (N-0034 area) — not touched.
3. **PASS** — `prove_cip_ro.py` → `prove_cip_ro.txt`, `SET TRANSACTION READ ONLY` + rollback, `current_database() = cip`. `fact_inventory_customer` 0 rows, CST 1,823. Excerpts (as_of 2026-09-24; BEFORE for every pair: `fact_inventory_customer rows=0 on_hand=0`):
   - Makro 15/15712: available, wk 2026-04-06, soh 24, cost 6194.26 (unit_mac, ex_vat)
   - Computer Mania 18/13461: available, wk 2026-06-29, soh 8, cost 28086.0 (unit_cost, ex_vat)
   - Evetech 52/16529: available, wk 2026-07-27, soh 1, cost None, flags [no_soh_cost]
   - Takealot 20/13284: soh 0, flags [zero_soh]
   - Amazon 299/11929: **unavailable** (no CST SOH row)
   - CPOR line 2971 Takealot 20/8528: soh 11, SOH cost 33516.10 (inc_vat) vs cost_basis 30811.213 → delta −2704.887; lines 2968/2964/2960 similar (−1008.818, −1593.502, −598.124).
4. **PASS** — `apps/api/tests/test_cpor_customer_soh_check.py` (5 tests: CST source + SQL shape, multi-site sum + SOH-weighted unit_mac-preferred cost + delta, units-without-cost, zero SOH, honest unavailable). Run on cip_test via n0048 shim: `pytest_cip_test.py -q tests/ -k "cpor or cost_suggestion or intake_weighted or cst_d1"` → **274 passed, 1 skipped**. ruff not installed in the venv (not run).

## Files changed
- `apps/api/app/services/cpor/customer_soh_check.py` (new)
- `apps/api/app/api/v1/endpoints/cpor_cases.py` (+import, `soh_check` in cost-suggest response)
- `apps/api/tests/test_cpor_customer_soh_check.py` (new)
- `docs/CPOR_SETTLEMENT_SPEC.md` (§9.1 note), `docs/BACKLOG.md` (BACKLOG-135 status line only; N-0034's concurrent BACKLOG hunks left unstaged)
- Evidence: `.eif/audit/PROGRAMME_20260924/n0049/prove_cip_ro.py`, `prove_cip_ro.txt`, this file.

## Questions for Warren
1. **Tolerance:** at what gap should the check FLAG (e.g. % of cost_basis or absolute R)? Today it only reports `delta`.
2. **VAT basis:** Takealot CST cost is `inc_vat`; line `cost_basis` appears ex-VAT. The four Takealot deltas are −8% to −9% (ratio ~1.088, not 1.15, so not a clean VAT gap). Should the check convert to ex-VAT before comparing, and at what rate? Not converted today (no rule stated).
3. **Evetech:** D-062 says Evetech has no SOH file, but CST holds 130 Evetech rows with `reported_soh` (no cost). Keep them in the check (units only) or exclude Evetech?
4. **Site sum:** is the customer SOH the sum across all reported sites in the latest week (implemented), or should a per-site check be kept?
5. **Comparand:** until a customer×SKU MAC master exists (§5), is line `cost_basis` the right thing to check against?

## Not done / blocked
- Nothing blocked. No web change, no DB write, no migration.
