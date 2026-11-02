# GOV-008 independent review: N-0114, N-0115, N-0116, On the water, shipment fixes (2 November 2026)

**Result: VERIFIED_WITH_LIMITATIONS for what passed; none of the three nodes can close.** Acceptance is Warren's; this review accepts nothing.

| | |
|---|---|
| Branch / HEAD | `feat/ns-2-brief-nav-collapse` at `5f442c3c` (product source committed; only untracked ops scripts and an e2e spec outside it) |
| Run | `RUN-20261102-GOV008-OPUS`, actor `gov-008` |
| Implementation runs | N-0114 `RUN-20261023-N0114-IMPL`, N-0115 `RUN-20261023-N0115-IMPL`, N-0116 `RUN-20261024-N0116-IMPL-CODEX`. All three differ from this run. |
| Independence rung | **R2**: fresh Claude Code session on Opus 5.5 plus four fresh-context Opus subagents (query model, reports, frontend, shipping). **Same model family** as the writer (Sonnet 5.5, Claude) and as the 28 Oct E10 reviewer. N-0116's code was partly written by Codex, so for that part the model differs, but this is not attested R3 for the nodes as a whole. **R3 not reached.** |
| Scope | Implementation change scope NONE. No product file edited. Nothing written to `cip`; every cip connection was `default_transaction_read_only=on` (a test write was refused: `ReadOnlySqlTransaction`). Write probes ran on `cip_test` inside rolled-back transactions. No restart, no migration, no `--apply`, no email. |
| Not done | Live render: **UNABLE_TO_RENDER** (Claude-in-Chrome extension not connected). The writer's PNGs (fixture tenant, 10:35, before the final 11:12 commit) are secondary evidence only. No non-owner Postgres role, no concurrency test, opt-in Playwright not run. |

Labels: **VERIFIED** = this review re-executed it or read the code. **ASSERTED** = taken from a writer's report and not re-run. A finding from a subagent probe that I re-ran or re-read myself is VERIFIED; one I did not re-run is marked (sub-agent, VERIFIED by it).

Evidence folder: `.eif/audit/REVIEW_20261102/` — `data/` (my cip probe, audit events, full API log), `query/REVIEW_REPORT.txt` + probes p1–p5, `reports/gov008_final_report.txt` + probes, `web/charts.probe.test.tsx` + `probe_run_output.log`, `shipping/GOV008_REPORT.txt` + probes.

## Gates re-run (VERIFIED)

| Gate | Result |
|---|---|
| Full API pytest on `cip_test` (`apps/api/.venv`) | **3,547 passed, 24 skipped, 0 failed** in 45 min (`data/api_full_pytest_cip_test.log`) |
| Web `tsc --noEmit` | exit 0 |
| Full web vitest | **222 files, 1,205 tests passed** |
| Focused API suites by the sub-reviewers | query 89 passed; reports 47 + 77/1 skip + others passed; shipping 87 passed |
| Lint | not re-run |

All committed tests pass. The defects below are not caught by them.

## 1. Requirements per node

### N-0114 chart fixes (R2, stage verify)

| Requirement | Status | Evidence |
|---|---|---|
| Every axis title with unit | UNVERIFIED | Not probed per caller; no render. |
| Legend on multi-series, optional on single | NOT MET (comparison chart) | Probe P1b: 12 categories, 10 bars shown, **24 legend entries** (`web/probe_run_output.log`). VERIFIED. |
| Long names never cut; auto horizontal; full pie names | NOT MET for dual axis; MET for bar/combo | P3a bar and combo: 10 wrapped category ticks, sort control present. P3b dual axis over 12 long names: **0 wrapped ticks, no sort control** (jsdom also drew 1 of 12 tick labels; that count may be a jsdom artefact, the missing shared tick is not). VERIFIED. |
| Top N 5/10/15/25/all and sort value/name/period | PARTLY MET | Saved `top_n` 5 reaches the bar (P2a), saved name sort reaches hbar (P2b), keyboard filter buttons on bar/hbar (P4). Defects: table widget ignores a saved name sort (P2d, server order shown, menu says "Highest first"); saved Z–A shows menu "Name A–Z" (P2c); a bar saved without `top_n` shows 10 while the editor says "Start with top 15" (P2e); saved `top_n` 50 shows no pressed option (P2f); comparison chart default order is as listed, not highest first (P1a). VERIFIED. |
| Numbers formatted by unit | PARTLY MET | Widget CSV header says `Delivery rate (%)` over the raw ratio `0.86` (P5a). On-screen formatting not re-checked. VERIFIED. |
| Shared components used by every chart | NOT MET | Dual axis bypasses the shared category tick (P3b). Full caller inventory not completed (frontend sub-review ended without a report). |
| No new chart library | MET | `git diff 17d0d1b2~1 HEAD -- apps/web/package.json` shows no dependency change since 23 Oct. VERIFIED. |
| Rendered light/dark at 1280×800 and 390×844 | UNVERIFIED | UNABLE_TO_RENDER. Writer renders exist (ASSERTED). |
| Full API pytest, web vitest, tsc green | MET | See gates. VERIFIED. |

### N-0115 data model and query compiler (R3, stage validate)

| Requirement / unit | Status | Evidence |
|---|---|---|
| E1 governed CPOR filters before aggregation, rows = totals | MET | `query/p2_output.txt` E1.1–E1.9: bu=NB gives 40 (was 100); a nonexistent customer gives 0 and no rows; 3 grains × 6 filters rows = totals; tenant-B ids return 0. VERIFIED (sub-agent probe, files present). |
| E3 scheduled delivery tenant/recipient scope (D-0132) | MET for one recipient; see M4 | `reports/gov008_probe_e3_schedule_output.json`: tenant bound, GUCs reset after aborted SQL, cache order safe, revoked/inactive/other-tenant recipient refused. VERIFIED. |
| E6 hidden/narrowed legacy metric refuses its v2 counterpart | PARTLY MET | units, avg, min, max and the calculations are refused (`tenant_restrictions.py:87-117`). **`dsi_sellout.priced_units` (the same units column) stays queryable and listed**: 44.4% of sell-out units on cip (`query/p3_output.txt`). specs_json allowlist and injection-shaped keys: MET. Cache isolation across tenants/overlay: MET in one process. VERIFIED. |
| E7 new measures | NOT MET (shipments) | **`shipments.quantity`/`lines` count closed lines** (`semantics/models/default.yaml:303-314` filters only `when_not_null: ship_confirm_date`). On cip: 29 `closed_shipped` (2,015 units) + 47 `closed_superseded` (3,597) carry a confirm date → **+5,612 units, +76 lines** (I re-ran the count read-only). Open quantity strict-pair: MET. Distributor on-hand latest-not-summed: MET (10, not 18). Returns tenant via product: MET. Sell-in and recorded prices: UNVERIFIED (both tables empty on cip). Lineup drops 53 lines / 553 units with no product. Refused measures refuse, but as "Unknown measure", not with the pending reason. |
| E8 day / business calendar | PARTLY MET | Sell-through refuses day: MET. **Lineup and sell-in declare `floor: day` on a period-start date**, so day and week grains are allowed and put a whole period's plan into its first day/week (all 32 dated lineup cases on cip start on the 1st). **Per-week totals wrong on non-platform calendars with no window** (Sunday week row 14/wk, total 7/wk; retail 2.8 vs 3.16; `calc.window_weeks`). VERIFIED (sub-agent probes p2 D5–D7, p4 W). |
| E10 defects 1–5 (28 Oct) | FIXED | Prior year with a window, Sunday-week first bucket, 4-4-5 previous period, retail prior year (never probed before, 53-week FY23 included), open-line double count, `resolved_customer_id` grouping: all pass by value (p2 D1–D4). The old open-line double count is gone, but closed states now double count (E7 row). VERIFIED. |
| Measures with sum/count/distinct/avg/min/max for every fact family | PARTLY MET | The loader supports all of them; avg/min/max are declared only for sell-out and sell-through units and average prices. None for shipments, stock, returns, lineup or CPOR. Sales value is still a decision (D-0117/0118). |
| Shared breakdowns, attributes, specs, calendar grains | MET with the lineup caveat | `graph.derived_breakdowns`; `execute.py:134-138` uses the tenant calendar. |
| Breakdowns derived from joins/walls; walls with plain reasons; every refuse_example kept | MET | p5: 11 of 11 v1 examples verbatim, 9 walls. |
| Calculated measures (8 kinds) | MET per row; per-week total defect above | share 1.0, running total per partition correct. |
| One compiler, tenant + product-line scope, limits, explain, cache | MET in the application | `compiler.py:244-278` adds a structural tenant predicate. **No RLS policy checks tenant anywhere** (all policies are product-line only), so tenant isolation rests on the application. |
| Under 2 s per widget query on cip | MET as the table owner only | 15 queries, slowest 498 ms. Role `cip` is the owner; no non-owner, concurrency or HTTP timing. |
| Per-tenant catalog config; catalog API returns combinations | MET with mismatches | Catalog offers `day` for every sell-through measure and `period` for open shipments, which the planner refuses (24 cases); `requires: []` on prior year and running total. |
| Parity; every existing caller keeps working with a test | PARTLY VERIFIED | Full API suite green. No per-caller parity matrix re-run. |
| Non-owner RLS | UNVERIFIED | Not tested. |

### N-0116 dashboard builder (R3, stage validate)

| Requirement / unit | Status | Evidence |
|---|---|---|
| E2 XLSX literal safety | MET | `report_export.py:65-69`; `=1+1`, `+cmd`, `-2+3`, `@SUM(A1)`, tab, `=HYPERLINK` through 4 HTTP paths stay type `s`, no `<f>`; numbers stay `n` (`reports/gov008_probe_e2_xlsx_output.json`). Delivery builds no file (N/A). VERIFIED. Other XLSX exporters (CPOR, lineup, promo) and AG Grid CSV have no guard (outside E2, m). |
| E4 saved-query fidelity | MET for v2-native; NOT MET for migrated v1 (M3) | Sort asc / limit / period grain identical card → promote → XLSX → PDF → delivery, total 1,012 at every hop; ordinary dashboard dates refused or frozen on promotion; saved-v2 download routed to v2 (vitest). `units_per_week` with no dates is refused on promotion but a direct `POST /saved-reports` stores it, then export 400s. VERIFIED. |
| Saved dashboards/widgets/reports migrate without loss | Schema and idempotence MET; export parity NOT MET | 0048 adds columns only; the script writes only `definition_v2 IS NULL` rows. A migrated report with 522 groups exports 500 reordered rows (M3). Latent: 0 of 3 saved reports on cip are migrated. |
| Scheduled reports keep sending | MET on cip today; at risk (M4) | cip's only enabled schedule delivered on 2 Nov 09:00 (read-only). No delivery and no failure row on 5 Oct and 26 Oct (cause not established). |
| Tenant scoping of dashboards, widgets, reports | MET | Tenant B admin got 404 on 24 by-id reads/writes of tenant A objects; tenant A rows unchanged. A widget accepts another tenant's `saved_report_id` (stored, 200): integrity gap, not a data leak (m). dashboard, dashboard_widget, saved_report, cpor_case, report_schedule have no RLS on cip (VERIFIED, my probe). |
| Visual set, click to filter, view rows, widget tools, loading/empty | Keyboard filter on bar/hbar MET (P4); the rest UNVERIFIED | Not re-probed; no render. |
| Widget CSV export | NOT MET (fidelity) | `builder/table.ts:61` runs every non-period breakdown through `displayPartyName`: **`UX3405MA` exports as `Ux3405Ma`, `ACBU` as `Acbu`, `=SUM(A1)` as `=Sum(A1)`** (P5b). The formula guard (`guardCell`) works. VERIFIED. |
| Three editable starters | NOT MET (ASSERTED) | E10 found cover, restock, value and open cases still refuse; CURRENT.md calls them honest gaps. Not re-run here. |
| Every visual and starter rendered light/dark at both widths | UNVERIFIED | UNABLE_TO_RENDER. |

### On the water

| Item | Status | Evidence |
|---|---|---|
| At sea 14,987 units / 131 lines / 8 vessels / 3 overdue | MET | In-process `GET /shipping/on-the-water` on cip, read-only: exactly those figures; 4,013 units on overdue vessels; vessel units and lines sum to the tile (`data/cip_readonly_probe_output.json`). VERIFIED. |
| Arrived 5,512 | MET | 5,512 / 66 lines; City Deep 5,108, Port Louis 404. VERIFIED. |
| Needs a look 9 lines / 731 units | MET | Card 9 / 731; `/shipping/lines?cohort=needs_look` 9 rows / 731 units. VERIFIED. |
| Unauthenticated access | MET | Both GETs return 401 without a user. POST port-conditions admin only. VERIFIED. |
| Voyage columns (0049) and backfill | MET; downgrade drops history | Audit event 22 matches (below). Backfill guard and idempotence by code and cip_test dry run. 0049 downgrade drops `port_condition` with its history (m). |
| Click refreshes only the grid | MET for the map; gap for tiles | `buildOnTheWaterUrl` keeps only page identity; `replaceState` only; tests pass. With another filter active, a vessel click still refetches the tiles (m). VERIFIED by sub-agent tests. |
| Badge "N days overdue · ETA moved +M days" | MET, edge defect | When the ETA was pulled in, slip is clamped to 0, so the badge says "ETA unchanged" and the history text is false; a vessel with no ETA is drawn at 100% (m). |
| Side panel min 360 px | UNVERIFIED | Source only. |
| Port labels, map caption | Defect seen in a writer render | `renders/1280-dark-3-vessel-panel.png` (fixture): the "Durban · No figure entered · Planned" pill overlaps the map caption and the cluster box partly covers "City Deep / Durban". ASSERTED pixels, observed by me. |
| Tenant isolation | Latent defect (M5) | `_HISTORY_SQL` (`shipping_water.py:133-153`) joins observations by `line_identity_key` with no tenant: a probe on cip_test showed tenant B's vessel with slip 60 taken from tenant A's observation. cip has one tenant today. |

### Shipment fixes since 23 October

| Fix | Status | Evidence |
|---|---|---|
| Open-book close on apply (complete-book types, scope, report date) | MET for dated newer reports; gaps | Older-report guard ignores operating unit (a lagging OU's book writes nothing). **An undated complete-book file still writes facts**: `job_is_older_than_applied_book` returns False with no date (`shipment_open_book.py:80-86`), so a `closed_disappeared` fact goes back to `open_order` and an old-key and new-key fact can both be open (probes P4, P5). Partial shipment: open 100 with 60 shipped closes as `closed_shipped` for 100, the missing 40 not flagged. |
| One-off close on cip (audit event 18) | MET as described | 1,031 facts (538 `closed_shipped`, 493 `closed_disappeared`, 77,496 units), 21 reclassified, report date 2026-09-11. VERIFIED. But **`reclassify_unconfirmed_shipped` (`shipment_open_book.py:209-222`) is an unscoped table-wide UPDATE**: it also turned 3 leaked test facts (`AUD-PARI-*` from `tests/test_data_integrity_audit.py`, 2 Jul, no job, report type `shipped`, 30 units) into open orders on cip (ids 99964, 99966, 99968). Only the already-run script calls it. |
| Loader source key keeps `ord:<order>\|<line>` on a blank invoice line | MET | Key shape and legacy helpers by code and probes. Guarded against double counting only within one job (see undated row). |
| Fact-writer chunking (one key in one chunk) | MET | Probe P7. |
| PO-less twin retire (audit events 23, 25) | MET | 37 + 10 retired; 47 facts, 3,597 units; every pointer resolves (0 dangling). VERIFIED. |
| Re-process job 1697 (audit event 24) | MET | Evidence lines 7,967 → 8,071 (8,071 on cip now). "fact_rows 8071" is rows read, not facts (job 1697 holds 7,358 facts). Observations 16,065 (append-only). VERIFIED. |
| Orphan retire `retire_orphaned_open_rows` (audit event 26) | MET on cip; edge gaps | Event 26 lists the 9 facts; each now `closed_superseded` pointing at an open fact of job 1697 with the same quantity. **Repeat dry run: 0 rows, 0 units.** No open fact in any job has a null evidence line except the 3 test facts above. Edge cases (probe P6): no quantity check on the replacement; with no order line two orphans point at one fact; a line that moved sheet closes as disappeared, not superseded; at load time it writes no audit event. |
| 0050 downgrade | NOT SAFE | `20261101_0050` downgrade sets **every** `closed_superseded` row to `shipped`, including the 9 orphan-retired open orders (921 units with no confirm date). VERIFIED by code. |
| Import friction (saved mapping, remembered sheets, decision reuse) | MET for one tenant; gaps | A new or renamed sheet is silently left out once sheets are remembered. Mapping memory, remembered sheets and token aliases carry no tenant and are reused automatically (code read, not executed). |

### Audit events (VERIFIED, read-only)

| Event | Action | Matches the description |
|---|---|---|
| 18 | `open_book_close`, job 1339, 29 Oct 10:06 | yes: 1,031 closed (538/493), 21 reclassified |
| 22 | `shipment_water_backfill`, 0049, 1 Nov 17:50 | yes: 110,834 lines, 112,232 observations, 15,788 facts (15,785 filled), 0 conflicts |
| 26 | `shipped_fact_orphan_open_retire`, job 1697, 2 Nov 14:57 | yes: 9 superseded, 0 disappeared, the 9 fact ids |

Also on cip: alembic `20261101_0050` (CURRENT.md's deployment-boundary paragraph still says 0048; the paragraph above it is current). Clones `cip_otw`, `cip_retire*` reported as not dropped (not checked).

## 2. Findings ranked

### Blockers (stop closing N-0115 and the shipment fixes)

**B1. Closed shipment lines are counted as live by several readers on cip today.** The closed states added since 28 Oct (`closed_shipped`, `closed_disappeared`, `closed_moved`, `closed_superseded`) are excluded on On the water and supply overview but not by:
- the v2 model `shipments.quantity` and `lines` (`default.yaml:303-314`): +5,612 units / +76 lines on cip, 3,597 of them double counting a PO-key twin (VERIFIED by me);
- channel_ops `/cover-distribution` open inbound (`channel_ops.py:1134-1150`): 1,157 closed rows / 79,112 units on cip beside 668 / 45,316 live;
- `/movement-lens` (`channel_ops.py:246-256`), `/forecasts` (`channel_ops.py:1013-1024`), `cpor/intake_weighted_mac.py` (820 closed rows / 59,712 units weight intake cost), `twin_remainder` (`shipment_strict_pair.py:218-247`: a closed row falls through as kept), the inbound-shipments list, lineup attribution.
Failure: a dashboard widget on shipped quantity, the cover distribution and the forecast inputs show closed or duplicated units as shipped or inbound. Counts by sub-agent probe on cip (read-only); the model row re-run by me. Grep covered `apps/api/app` only.

### Major

**M1. 0050 downgrade turns open orders into shipped.** Every `closed_superseded` row becomes `shipped`, including 9 orphan-retired open orders (921 units). A rollback would create 921 shipped units with no confirm date.

**M2. An undated complete-book file re-opens closed lines and can double count.** `job_is_older_than_applied_book` treats no date as "not older", so the fact write runs while the close does not. Closed facts go back to open and an old-key and new-key fact of one line can both be open; the orphan retire is job-local and does not catch it. The "did not close open orders" notice does not say lines were re-opened. (Probes P4, P5, cip_test, rolled back.)

**M3. Migrated v1 saved reports lose rows and change order on export and delivery.** `saved_report_payload` (`report_delivery.py:175-186`) applies the 500-row cap and value sort to every definition, including migrated ones, though the comment says they are exempt. Probe: 522 rows → 500 reordered, `truncated: true`, totals unchanged. Latent on cip (0 migrated). Introduced by E4 (`ab5e5de4`).

**M4. One bad subscriber stops a schedule for everyone after it.** All recipients run inside one `try` (`report_schedule_runner.py:206-238`); the first `PermissionError` (deactivated or revoked user) rolls back and writes one failed row. Probe: [viewer, deactivated, admin] → the admin got only a failed row. Every failure is also labelled as a timeout, because the error text always includes `statement_timeout_ms`, and the failed row shows raw `[SQL: ...]` text to inbox recipients (pre-existing). Introduced by E3.

**M5. Shipment identity is not tenant-scoped.** `fact_upsert_key` is globally unique with no tenant: tenant B's shipped load deleted tenant A's fact (probe P8). The On the water history query joins observations across tenants (slip and first ETA leak). Mapping memory and aliases carry no tenant and are now reused automatically. No RLS policy checks tenant on any table. Latent: cip has one tenant and 0 key collisions.

**M6. E6 overlay bypass through `priced_units`.** Hiding or narrowing `sellout_units` leaves `dsi_sellout.priced_units` (same column, 44% of units on cip) queryable and listed. Semantic governance gap, not a row leak.

**M7. E8 period-start facts accept day and week grains.** Lineup and sell-in declare `floor: day` on a period-start date; a quarter's plan lands in its first week.

**M8. Per-week rate totals are wrong on non-platform calendars when no window is set** (`calc.window_weeks` uses Gregorian bucket edges): the total disagrees with its own rows.

**M9. Widget CSV export changes text.** Codes and names are re-cased by `displayPartyName` (`builder/table.ts:61`); a ratio column is headed `%` but holds the fraction.

### Minor

- Chart controls: table widget ignores a saved name sort; Sort menu label wrong for saved Z–A; editor "top 15" vs renderer 10; comparison legend lists 24 entries for 10 bars; dual axis has no shared long-name ticks and no sort control (probe P1–P3).
- Catalog offers grains the planner refuses (CST day, open-shipment period); pending measures refused as "Unknown measure".
- Open book: partial shipment closes the full open quantity with no flag; a cancelled remainder can be labelled `closed_shipped`; older-report guard ignores operating unit; remembered sheets drop a new sheet silently.
- Orphan retire: no quantity check, shared pointer with no order line, no audit event at load time.
- `reclassify_unconfirmed_shipped` is unscoped (already run; 3 test facts reclassified). The 3 `AUD-PARI-*` facts (30 units) are leaked test data still on cip and count in open units.
- Badge with a pulled-in ETA says "ETA unchanged"; vessel with no ETA drawn at 100%; tiles refetch on a vessel click when another filter is active; port code `XXX` accepted; a raw NaN body gives a 500 while rendering the 422.
- Writer render: Durban pill overlaps the map caption; cluster box covers the City Deep label.
- A widget accepts another tenant's `saved_report_id`; `units_per_week` without dates can be stored by direct POST; other XLSX/CSV exporters have no formula guard; on-hand for a product absent from the latest report is a null row, not 0; `catalog_for_tenant_cached` has no TTL.
- `refresh_superseded_pointers` updates the whole table on every load.
- Docs: CURRENT.md deployment boundary says cip is at 0048 (it is at 0050). D-0132 is in the programme ledger, not in `.eif/DECISIONS.md`.

## 3. Can it close?

| Node | Can it close? | What blocks it |
|---|---|---|
| **N-0114** | **No** | Dual axis without shared long-name ticks or sort; table ignores saved sort; Sort label and default top-N mismatches; comparison legend; widget CSV re-cases text and mislabels ratio units; rendered light/dark at both widths not independently seen; axis-title/unit per caller unverified. |
| **N-0115** | **No** | B1 (shipped quantity counts closed lines); M6 priced_units overlay bypass; M7 day/week on period-start facts; M8 per-week totals; avg/min/max missing for five families; sell-in and recorded prices unverifiable (empty on cip); sales value still a decision; non-owner RLS and tenant-level RLS not proven; R3 independence not reached. |
| **N-0116** | **No** | M3 migrated export rows; M4 schedule recipient failure; M9 CSV fidelity; starters' cover/restock/value/open still refuse (ASSERTED from E10); every visual and starter not rendered; R3 independence not reached. Quality dimensions on the node are all still `pending`. |
| On the water (no node) | Figures yes; code with limits | Figures match on cip. Before rollout to more users: M5 history query tenant filter, badge pulled-in ETA, map caption overlap, an independent render. |
| Shipment fixes (no node) | **No** | B1, M1, M2, M5. The cip data writes (events 18–26) did what they say. |

## 4. What this run records in the ledger

`node.verification` (kind `behavioral`, state `blocked`, evidence this file) on N-0114, N-0115 and N-0116 under `RUN-20261102-GOV008-OPUS`, actor `gov-008`. `blocked` clears the earlier pass provenance on N-0114 and N-0115, which was measured on older source (23 Oct) and no longer stands. No stage change, no acceptance, no lease. On the water and the shipment fixes have no node; their findings are listed here for the next session to record (for example a `finding.defer` or a new node).

Recorded: N-0114 → ledger rev 2795 (node rev 17 → 18), N-0115 → 2796 (26 → 27), N-0116 → 2797 (25 → 26). Payloads in `ledger/`. `program.py verify` after: integrity true, the same 9 acknowledged historical gate issues (N-0006, N-0013 ×5, N-0014, N-0015, N-0016), nothing new. Ledger files are uncommitted.
