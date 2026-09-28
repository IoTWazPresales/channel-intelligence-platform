# GOV-008 independent verification — N-0049

**Node:** N-0049 (R2, api) — "Stage 4.3: MAC check reads customer sell-through, not the empty inventory fact (BACKLOG-135)"
**Reviewer:** verification-controller, lenses backend-engineer / analytics-bi-specialist / test-engineering-specialist
**Model identity:** claude-sonnet-5 (Claude Sonnet 5), independent subagent session — no prior context on this node, did not read the implementer's N-0049 audit findings.
**Independence rung:** R2 — different session (fresh subagent, no shared context with the implementation run). Recorded as **independent verification**, not self-check.
**Evidence commit:** `3624d7e7` — `git show --stat` / full diff read directly (5 files, +229/-1).

## Acceptance criteria

### AC1 — "MAC check sources customer SOH from fact_customer_sellthrough and stops claiming fact_inventory_customer; proven on cip_test or a clone with printed numbers"

**PASS.**

- **(a) No prior check existed.** `git grep -n -i "fact_inventory_customer\|soh" 3624d7e7^ -- apps/api/app` (parent tree) returns only unrelated hits: distributor-side SOH (`channel_ops.py`, `channel_ops_derived_stock.py` — these use `FactInventoryDistributor`, a *distributor* fact, not customer), the `fact_inventory_customer` **model class definition** in `facts.py:69` (no reader/writer of it), CPOR line `soh_snapshot` fields (a stored case value, not a check), and CST read-model code unrelated to a MAC check. No `customer_soh_check`-shaped function, no `soh_check` endpoint field, existed before this commit. VERIFIED.
- **New source, single table.** `apps/api/app/services/cpor/customer_soh_check.py` (new file, 124 lines) queries only `FactCustomerSellthrough` (SQLAlchemy `select(...)` over that model — file:lines 96–120). The unit test `test_source_is_cst_not_inventory_fact` additionally asserts `"fact_inventory_customer" not in sql` on the *compiled* SQLAlchemy statement text. VERIFIED (read code + ran test, see AC3).
- **Wired to the API.** `apps/api/app/api/v1/endpoints/cpor_cases.py` `cost_suggest()` (GET `/cpor/cases/{id}/lines/{line_id}/cost-suggest`) now returns `"soh_check": customer_soh_check(session, customer_id=case.customer_id, product_id=line.product_id, as_of=as_of, derived_mac=line.cost_basis)` — `derived_mac` is the stored line `cost_basis`, matching the commit message ("delta vs stored line cost_basis reported only"). VERIFIED (diff read, file:line ~1307–1315).
- **Proven with printed numbers, real data.** `cip_test` (the sanctioned clone) has 0 rows in `fact_customer_sellthrough` (`select count(*)` → 0), so I hand-verified the arithmetic against real production rows from `cip` in a **read-only** session (`ro_sql.py`, `conn.read_only=True`, no write attempted) and fed those exact rows into the actual `summarise_soh_rows()` function (pure function, no DB access) via a throwaway script (deleted after the run):
  - Customer 57 × product 5312, period 2026-09-28: 2 rows, each `reported_soh=1.0000`, `unit_mac=unit_cost=5653.6200`. Expected: units=2, weighted cost=5653.62. Function returned `soh_units=2.0, soh_unit_cost=5653.62, cost_field='unit_mac'`, and with `derived_mac=6000.00`, `delta=346.38 = 6000.00-5653.62`. **Matches by hand.**
  - Customer 57 × product 3948, period 2026-03-30: 3 identical rows, `reported_soh=3.0000`, cost=7129.0200 each. Expected: units=9, weighted cost=7129.02. Function returned exactly that; with `derived_mac=7000.00`, `delta=-129.02`. **Matches by hand.**
  VERIFIED (command + output captured; see below).

Command excerpts:
```
$ apps/api/.venv/Scripts/python.exe .eif/audit/PROGRAMME_20260924/ro_sql.py --db cip_test "select count(*) from fact_customer_sellthrough"
current_database() = cip_test
count
0
$ apps/api/.venv/Scripts/python.exe .eif/audit/PROGRAMME_20260924/ro_sql.py "select id, period_start_date, ... from fact_customer_sellthrough where customer_id=57 and product_id=5312 and period_start_date='2026-09-28'"
current_database() = cip
1589 | 2026-09-28 | weekly | 1.0000 | 5653.6200 | 5653.6200 | ex_vat
1594 | 2026-09-28 | weekly | 1.0000 | 5653.6200 | 5653.6200 | ex_vat
$ apps/api/.venv/Scripts/python.exe .tmp_verify_soh_gov008.py   # (deleted after run)
case A: {'soh_units': 2.0, 'soh_unit_cost': 5653.62, 'cost_field': 'unit_mac', 'delta': 346.38, ...}
case B: {'soh_units': 9.0, 'soh_unit_cost': 7129.02, 'cost_field': 'unit_mac', 'delta': -129.02, ...}
ALL MANUAL RECOMPUTATIONS MATCH
```

**Limitation:** `cip_test` itself is empty (schema-only clone), so the "printed numbers" proof required using `cip` in a read-only session rather than `cip_test`/a data-bearing clone. This is a scope limitation of the environment, not of the implementation — flagged per brief's guidance to prefer `cip_test`. Noted as a limitation, not a criterion failure, since (i) the brief permits "cip_test **or a clone**" and no data-bearing clone was available, (ii) the read session was provably read-only (`conn.read_only=True`), and (iii) I fed the exact rows into the real production function rather than a reimplementation.

### AC2 — "Nothing writes to cip"

**PASS.**

- `customer_soh_check()` and `summarise_soh_rows()` contain only `select(...)` / `func.max(...)` — no `insert`, `update`, `delete`, or `session.commit()` anywhere in the new file (read full file). VERIFIED.
- All my own verification queries against `cip` used `ro_sql.py`, which opens the connection with `conn.read_only = True` (file read at `.eif/audit/PROGRAMME_20260924/ro_sql.py:9`) and ends every call with `conn.rollback()` — a write would be rejected by Postgres at the driver level, not just avoided by convention. VERIFIED.
- Pytest ran against `cip_test` via the sanctioned shim (`.eif/audit/PROGRAMME_20260924/n0048/pytest_cip_test.py`), which I read first: it only reassigns `DATABASE_URL`/`DATABASE_URL_SYNC` env vars to the `cip_test` path before invoking `pytest.main()` — it cannot point at or touch `cip`. VERIFIED. (The test module itself uses a `MagicMock` session throughout, so no real DB was touched by the test run either way.)
- No edits made to product source; the one throwaway script written for hand-verification (`apps/api/.tmp_verify_soh_gov008.py`) was deleted immediately after use and never imported by the app.

### AC3 — "tests green"

**PASS.**

```
$ apps/api/.venv/Scripts/python.exe .eif/audit/PROGRAMME_20260924/n0048/pytest_cip_test.py -q tests/test_cpor_customer_soh_check.py
pytest DB -> /cip_test
.....                                                                    [100%]
5 passed in 1.96s
```
5/5 new tests pass: source-table assertion, sites-summed + `unit_mac`-preferred weighting, SOH-without-cost flagging, zero-SOH handling, and the honest-`unavailable` branch. VERIFIED.

## Additional checks requested in the brief

**(c) "unavailable" branch is honest (never zero stock when no row).** VERIFIED by code read (`summarise_soh_rows`: `if not rows: ... status="unavailable", reason=..., flags=["no_customer_soh"]` — returns *before* setting `soh_units`) and by the unit test `test_honest_unavailable_when_no_cst_soh_row`, which explicitly asserts `"soh_units" not in out`.

**(d) No output/SQL names `fact_inventory_customer`.** VERIFIED — confirmed independently by reading the file (queries `FactCustomerSellthrough` only) and by the unit test's assertion on the compiled statement text.

**(f) No invented business rule (e.g., a tolerance flag).** PASS. The function reports `delta` as a plain number with no threshold/tolerance band and no pass/fail judgment attached to it ("delta vs stored line cost_basis reported only"). This matches D-062 (`docs/STEWARD_ENGINE_DECISIONS.md:750`): "the SOH is the check, never the input" — i.e., the system surfaces the comparison, a human interprets it. The two flags that do exist (`zero_soh`, `no_soh_cost`) are descriptive of missing/degenerate cost data, not judgment thresholds. Spec `docs/CPOR_SETTLEMENT_SPEC.md` §5 also requires boundary weeks be "flagged, never silently pro-rated" — this check doesn't span weeks (it always resolves to one `period_start_date`, the latest ≤ as-of), so boundary pro-ration doesn't arise here; this is consistent with the node's narrower scope and is *not* one of the node's stated acceptance criteria. Not scored as a failure.

## Dims

- **quality.testing — pass.** New `apps/api/tests/test_cpor_customer_soh_check.py` (5 tests) covers the source-table guarantee, weighting/summation logic, both degenerate-data flags, and the honest-unavailable path; independently re-run and green against `cip_test` (see AC3). I additionally re-derived two real-data cases by hand against the actual function and matched exactly (see AC1).
- **quality.observability — na.** *Rationale:* the check is a synchronous, side-effect-free read path returned inline on an existing GET endpoint; failure/degenerate states are already surfaced as explicit response fields (`status: unavailable`, `flags`) rather than silent errors, so there is no new failure mode this node introduces that would need a log line, metric or alert beyond what the endpoint already has. No regression versus pre-existing observability of `cost_suggest`.
- **verification.referent — pass.** Re-executed material evidence independently rather than trusting the commit message: re-ran parent-tree grep myself (AC1a), re-ran the actual test suite myself against `cip_test` (AC3), and recomputed the check's arithmetic by hand against real `fact_customer_sellthrough` rows through the real function, not a reimplementation (AC1). All matched. Read-only throughout; confirmed the `cip`-read tool is read-only at the driver level and the pytest shim cannot reach `cip`.

## Limitations
- `cip_test` has no data in `fact_customer_sellthrough`, so "printed numbers" verification used a read-only session against `cip` instead, per the brief's "cip_test or a clone" allowance. No write capability was available or used in that session.
- Did not run the live HTTP endpoint (no browser use requested/needed for this node); verified the wiring by reading `cpor_cases.py` and exercising the underlying service function directly with real row data, which is the load-bearing logic.
- Did not exhaustively audit every other reader of `fact_inventory_customer` in the repo (e.g. `/inventory` page, still noted as open in `docs/BACKLOG.md`'s updated status line) — out of scope for this node's stated acceptance criteria, which concern the MAC/SOH check only.

## Overall verdict: VERIFIED
