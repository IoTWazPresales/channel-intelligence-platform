# N-0065 product-line row security: performance discovery

Lenses: performance-engineer (primary), database-specialist. Read-only measurement on `cip` (PG 18.3), 2026-10-07: READ ONLY transactions, `statement_timeout` 60 s, no DDL, writes or code edits. Scripts and raw output: `.eif/audit/PROGRAMME_20261007/n0065_*`.

## 1. As built (FACT: migration `20261006_0024`, `pg_proc`, `pg_class`)
- `cip_product_id_visible(pid)` is `sql STABLE SECURITY DEFINER SET search_path`, not LEAKPROOF, owned by `postgres`. It probes `dim_product` by pk on every call. SECURITY DEFINER and the SET clause block inlining, so it runs as a separate function call **for every scanned row in every mode**, unset and `*` included. The setting is checked only after the probe.
- 45 tables have ENABLE plus FORCE RLS. Role `cip` is not superuser, has no BYPASSRLS and owns most tables. FORCE applies the policies to the owner too.
- Cost per row, measured over 200k real ids (`n0065_p3.py`): **as built 9.5-15 µs**; inlined `EXISTS` 0.25-2.5 µs; short-circuit plus hashed allowed-set 0.15-1.3 µs.
- The planner assumes RLS keeps one third of rows (it estimated 64k; 88k passed). Across several RLS'd scans this compounds into 1-row estimates and nested loops.

## 2. Measurements (unset / `*` / NB; NB = 6,848 of 18,177 products)
"Stmt ms" is EXPLAIN ANALYZE of the path's heaviest statement. "Calls" is how many times the RLS function ran in it.

| Path | Endpoint ms | Stmt ms | Calls | Where time goes |
|---|---|---|---|---|
| lineup/net-requirement | 53.8k / 58.8k / 18.3k | >60k / >60k / 17.0k | 440k | Estimate of 1 row gives 1.19M nested index loops. With `enable_nestloop=off`: 2.1k / 3.7k |
| channel-ops/cover-distribution | 5.6k / 8.8k / 4.1k | 2.4k / 4.2k / 3.7k | 194k | Seq scan of `weeks_of_cover_observation`; ~80% RLS |
| channel-ops/summary | 6.6k / 5.6k / 4.4k | 3.6k / 3.6k / 3.4k | 194k | Same scan |
| brief/signals | 5.0k / 5.7k / 2.4k | 3.5k / 5.2k / 2.9k | 194k | Same scan |
| shipping/commercial-summary | 7.5k / 8.6k / 9.4k | ~1.0k | 124k | Evidence and inbound scans; mostly RLS |
| supply/overview | 2.1k / 2.1k / 1.5k | ~0.67k | 76k | 5 inbound scans; ~95% RLS |
| sellout/commercial-lines | 3.9k / 4.4k / 2.1k | 2.4k / 1.9k / 1.5k | 16-36k | Nested loop from `dim_product`; plan shape plus RLS |
| shipping/summary, dashboard | 2.2k, 1.0k / 1.8k, 0.8k / 2.5k, 0.5k | 0.25-0.7k | 30.5k | Nearly all RLS |
| shipping/lines | 15.4k / 10.1k / 12.1k | 0.8-1.3k | 2.5k | Not RLS-bound: 54k wide rows fetched and built into ORM objects |
| plan-vs-executed (58 stmts) | 16.8k / 14.9k / 16.1k | 0.4-0.7k | **0** | View bypasses RLS (3b) |
| cpor/settlement/book | 0.6k / 1.3k / 0.5k | 9-20 | 658 | Fast; sync session, gate unset (3c) |

As built, RLS costs **8-15 µs per scanned row in every mode**, workers included. That is 70-95% of the scan-heavy statements, 0.3-3 s each. The 120-240 s timeouts N-0071 reported came from correlated plans multiplying this per-row cost. The worst remaining case, net-requirement, is a misestimated plan sitting at the 60 s timeout.

## 3. Correctness findings (D-0056)
- **a. Pooled backend fails closed.** Once a backend has run `set_config(..., true)`, the setting reads back as `''` after the transaction, not NULL. `''` means "no lines", so a later unset user of that pooled connection sees **zero product rows**. The sync engine pools connections (`pool_size=5`); async uses NullPool. The in-flight `after_begin` listener now scopes sync sessions, so pooled backends will hold `''` for in-process unset work. Its docstring says the scope "can never reach another request through the pool". The value cannot, but the deny-all `''` can.
- **b. View bypasses RLS.** `shipment_evidence_current` is owned by superuser `postgres`, with no `security_invoker`. An NB user sees **6,554 rows of other lines' products** through it.
- **c. Sync routes unscoped.** `cpor_cases` routes use sync `SessionLocal`, which got no GUC before the in-flight listener. Re-check after it lands.

## 4. Fixes, ranked

| # | Fix | Gain | Migration | Access-rule risk |
|---|---|---|---|---|
| 1 | Policy predicate without SECURITY DEFINER or SET, so it inlines: `product_id IS NULL OR cs IS NULL OR cs='*' OR product_id IN (SELECT id FROM dim_product WHERE product_line = ANY(string_to_array(cs,',')))`, where `cs` = `current_setting('cip.product_lines',true)`. The allowed set becomes one hashed subplan per statement. Same for edit. | 10-40x on the RLS share. Cover and brief ~3 s to ~0.2 s. Workers pay ~0 | yes | Low, same semantics (NULL open, `*` all, list only, `''` none, NULL product visible). The inner `dim_product` read runs under its own policy, which is the same rule. Needs a parity test on 45 tables |
| 2 | "No lines" becomes a sentinel (e.g. `'!'`); SQL treats `''` as unset | Fixes 3a | yes, plus app | Medium. Every non-admin path must write the sentinel |
| 3 | `ALTER VIEW shipment_evidence_current SET (security_invoker=true)` | Closes 3b; adds ~1 s unless fix 1 lands first | yes | Closes a hole. Ship with fix 1 |
| 4 | net-requirement: compute the latest-snapshot subquery once (MATERIALIZED CTE) | 57 s to ~2-4 s | no (code) | None |
| 5 | Short-circuit only | Unset and `*` 5-20x; NB unchanged | yes | Low but partial |
| 6 | LEAKPROOF, or an index on `product_line` | Negligible | yes | Not recommended |

Not measured: write paths (`_editable` policies). Verification: self-measurement, not independent.
