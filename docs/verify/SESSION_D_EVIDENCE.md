# SESSION D Evidence — VERIFY debt runbook (6f + 7)

## Run 2026-08-30 ~22:20+ UTC+2 — fill-rate discrepancy + unit 6f cip_test writes

**Collection timestamp:** 2026-08-30 (Sunday), from ~22:20 UTC+2  
**Collector:** Cursor agent (this chat; continuation of SESSION D)  
**Branch:** `feat/ns-1a-fx-readiness-chips`  
**HEAD at collection:** `32e0af60da04780bc4195f4af64cc218c2cd0a47`  
**No PASS/FAIL verdict.** Prior gap records below are kept.

---

### Task 1 — 26Q3 fill rate 13.2% (2026-08-14) vs 19.5% (today)

**Finding: (a) DATA MOVED.** The fill formula and its inputs in code did not change between the 14 Aug pin and HEAD. Today’s numerator/denominator on `cip` are `6352 / 32509 = 19.5%`. That identity is the current readout; 13.2% is not reproducible from today’s rows with the same formula. This is **not** a unit 7 calculation regression.

#### Git (quoted)

Pin commit on 2026-08-14:

```
d80d13c 2026-08-14 17:59:00 +0200 docs: pin full audit and test results on main
```

`plan_vs_executed.py` last touched **before** that pin:

```
e87f6e8 2026-08-01 15:58:13 +0200 commercial: resolve Q-001/002/009 tenant profile + Channel Ops VERIFY fixes
```

Empty log / empty diff (no commits, no file change 14 Aug → HEAD):

```
$ git log --since=2026-08-14 -- apps/api/app/services/commercial_planner/plan_vs_executed.py
(empty)

$ git log --since=2026-08-14 -- apps/api/app/services/commercial_planner/lineup_po_reconciliation.py
(empty)

$ git diff --stat d80d13c HEAD -- apps/api/app/services/commercial_planner/plan_vs_executed.py
(empty)

$ git diff --stat d80d13c HEAD -- apps/api/app/services/commercial_planner/lineup_po_reconciliation.py
(empty)

$ git diff --stat d80d13c HEAD -- apps/web/src/features/plan-vs-executed/
(empty)
```

Formula at HEAD, blamed to `a35a8ae` (2026-07-06) — unchanged at `d80d13c` (`git show d80d13c:...plan_vs_executed.py` still has the same lines):

```
sum_min = sum(min(float(r["shipped_units"]), float(r["planned_units"])) for r in in_plan)
fill_rate = sum_min / sum_p if sum_p > 0 else None
```

UI percent format, also `a35a8ae` 2026-07-06:

```
return `${(n * 100).toFixed(1)}%`;
```

`git show d80d13c:...plan_vs_executed.py` matches on `fill_rate` / `sum_min`. Post-14-Aug commits under `commercial_planner/` (`fc14962` merge-redirect, bulk-apply slot, parser notes, token stamp, attribution resolver) **do not** include `plan_vs_executed.py`. `git diff --stat d80d13c HEAD -- apps/api/app/services/commercial_planner/` lists eight other files; none is the scorecard aggregator.

#### Today’s 26Q3 all-BUs counts (read-only, `cip`)

`apps/api/scripts/ops/session_d_fill_rate_evidence.py` via `collect_execution_rows(..., period_from="26Q3", period_to="26Q3")` + `compute_scorecard_from_execution_rows`:

```
current_database() cip
in_plan_row_count 224
all_row_count 230
denominator_sum_planned 32509.0
numerator_sum_min_shipped_capped 6352.0
shipped_units_in_plan_uncapped 6352.0
fill_rate 0.19539204527976867
fill_rate_pct_1dp 19.5
scorecard_planned_units 32509.0
scorecard_shipped_units_in_plan 6352.0
scorecard_shipped_units_total 6640.0
13.2pct_of_today_planned 4291.2
implied_planned_if_num_fixed_at_sum_min_for_13.2pct 48121.2
```

`6352 / 32509 = 0.19539…` which is the headline **19.5%**. The Aug 14 gate (`docs/UNIT8_DEMO_P2_GATE.md` A6: `/plan-vs-executed` fill **13.2%** (26Q3) on 2026-08-14) did not store the scorecard components, so we cannot say whether planned shrank or shipped grew — only that **today’s counts alone produce 19.5%, not 13.2%**, and the code that divides them is the same as on 14 Aug.

Capped vs uncapped in-plan shipped are equal (6352); the min() cap is not the 13.2→19.5 move.

---

### Task 2 — unit 6f write-path on cip_test

**.env not edited.** API process env only. `.cursor/hooks` untouched.

#### Retarget (required for `/health/ready`)

`GET /health/ready` uses async `DATABASE_URL` / `AsyncSessionLocal`, not `DATABASE_URL_SYNC`. Overriding only the two sync vars would leave `/health/ready` on `cip` and is a **STOP**. This run also set `DATABASE_URL` (async) to `cip_test` in the **child process only**, together with `DATABASE_URL_SYNC` and `DATABASE_URL_SYNC_MIGRATE`. That is how the proof gate can pass; it is not a guard weakening.

Stopped the listener on `:8001` only (did not run `stop-dev.ps1`). Started `apps/api/scripts/ops/session_d_run_api.py cip_test` (no `--reload`).

```
GET /health/ready
HTTP 200
{"status":"ready","database":"cip_test","ok":true}
```

Writes proceeded only after that body.

#### Seed (cip_test, after ready proof)

`cip_test` had **0** lineup lines and **0** `conflict` rows (`SELECT count(*) … status = 'conflict'` printed `current_database() cip_test` → `(0,)`).

Disposable case **43** (`SESSION-D-UNIT6F`, `inferred_period_start=2026-07-01`):

| line | token | before | purpose |
|------|--------|--------|---------|
| 22 | SESSION-D-ACCEPT | dist NULL, `token_proposed` | Accept (sole exact-qty ship dist 92) |
| 23 | SESSION-D-CLEAR | dist 92, `token_proposed` | soft-clear |
| 24 | SESSION-D-CONFLICT | dist 94, `token_proposed` | confirmer → conflict, keep dist |

Ships: product/qty 36 → dist 92; conflict SKU qty 20 × dist 92 and 93 (proposed 94 absent from ships). `OPEN_CHANNEL` customer id 1. Every SQL block printed `current_database() cip_test`.

#### Proposed → Accept

Confirmer preview (HTTP 200): `action=offer_accept`, `ship_corroboration_offer.reason=sole_resolved_distributor_exact_qty`, `distributor_id=92`.

`POST .../accept-ship` 200: `stamped_count=1`, `status=steward_set` (this is the Accept path; it sets `steward_set`, not `shipment_confirmed`).

```
AFTER accept-ship line  current_database() cip_test
(22, 43, 92, 'steward_set', 'SESSION-D-ACCEPT')

AFTER accept-ship audit
(17, …, 'anonymous', 'lineup_ship_corroborated_distributor_accept', 'customer_token', 'session-d-accept', 'dim_distributor', 92)
```

#### Soft-clear

`POST .../soft-clear` 200: `cleared_count=1`, prior dist 92 / `token_proposed`.

```
AFTER soft-clear line  current_database() cip_test
(23, 43, None, None, 'SESSION-D-CLEAR')

AFTER soft-clear audit
(18, …, 'anonymous', 'lineup_distributor_soft_clear', 'distributor_attribution', None, 'commercial_lineup_line', None)
```

#### No auto-clear on conflict

`cip` has zero conflict rows; `cip_test` had zero before seed. Confirmer apply on SESSION-D-CONFLICT:

```
POST 1: updated_count=1 action=conflict prior=token_proposed new=conflict distributor_id=94
AFTER confirmer-1  current_database() cip_test
(24, 43, 94, 'conflict', 'SESSION-D-CONFLICT')
audit 19 lineup_distributor_attribution_confirm

POST 2: updated_count=1 action=conflict prior=conflict new=conflict distributor_id=94
AFTER confirmer-2  current_database() cip_test
(24, 43, 94, 'conflict', 'SESSION-D-CONFLICT')
```

`distributor_id` stayed **94** (never null). Status stayed `conflict`. Second apply re-stamped conflict→conflict; it did not clear the distributor.

Final seed lines on `cip_test`:

```
(22, 43, 92, 'steward_set', 'SESSION-D-ACCEPT')
(23, 43, None, None, 'SESSION-D-CLEAR')
(24, 43, 94, 'conflict', 'SESSION-D-CONFLICT')
conflict count (1,)
```

#### Restore

Stopped `:8001`. Started `session_d_run_api.py env` (DATABASE_* forced from `.env` file; no inherited cip_test). `.env` still not edited.

```
GET /health/ready
HTTP 200
{"status":"ready","database":"cip","ok":true}
```

No writes were sent to `cip`.

---

## Run 2026-08-30 ~21:50–22:15 UTC+2 (this chat)

**Collection timestamp:** 2026-08-30 (Sunday), ~21:50–22:15 UTC+2  
**Collector:** Cursor agent (this chat)  
**Branch:** `feat/ns-1a-fx-readiness-chips` (already checked out at chat start; `git branch --show-current` printed this name)  
**HEAD at collection:** `eb65b5ccacd505acbb3f106e89b5c4140619dee9`  
**Environment:** local Windows; web `:3000` responded HTTP 200; API `:8001` `/health` 200 and `/health/ready` `{"status":"ready","database":"cip","ok":true}` (API's own connection)  
**Database policy:** read-only queries on `cip`; no HTTP writes (Accept / confirmer / soft-clear / override) because the running API's `current_database()` is `cip`  
**Collection method:** `scripts/restart-dev.ps1` then no-reload uvicorn on `:8001` after `--reload` drops; Playwright MCP + cursor-ide-browser after navigating to `http://127.0.0.1:3000` first; `apps/api/scripts/ops/session_d_readonly_evidence.py`; HTTP GET `/health/ready`, `/api/v1/shipping/lineup-quarter-summary?plan_quarter=26Q2`, `/api/v1/commercial-planner/lineup/distributor-attribution/review`

**Hooks:** `.cursor/hooks/` was already present in the working tree at chat start (untracked). First shell call returned git output (not mute `hook returned no output`). One later burst of parallel Playwright MCP calls was fail-closed (`eif_guard.cmd` exit 1); subsequent serial browser calls succeeded. Shell `Add-Content : Stream was not readable` appeared after several commands; command stdout was still captured.

**Services:** `scripts/restart-dev.ps1` spawned Redis/worker/API/web. First `/health/ready` on the spawned API returned `database=cip`, then the reload API dropped (`WinError 10061`). Web stayed up. App import of `app.main` succeeded (552 routes). Uvicorn without `--reload` then stayed up for the browser walk.

**No PASS/FAIL verdict.**

### Outstanding from prior gap record (kept; this run's status)

Prior run (~21:09) was blocked by API HTTP 500 and Signed out. That record is preserved below.

---

### Unit 6f — DistributorAttributionReviewSection

#### Observed

- **Login:** Session already authenticated after `http://127.0.0.1:3000` → redirected to `/dashboard` with **Sign out** and shell name **Local Admin**. No login POST in this run.
- **Case 1016:** still absent on `cip` (no case row, no lines).
- **Substitute (UI, newest review page):** **case 146** — lines **8420** / **8419** (`token_proposed`, Compuspeed id 12, period 2026 Q3). Review list is `ORDER BY line id DESC LIMIT 200`.
- **Substitute (prior record, still on `cip`):** **case 7** lines **344** and **345** (`token_proposed`, distributor_id 51). Not on the first 200 UI rows.
- **Section chrome (verbatim innerText / screenshot):** heading `Distributor attribution review`; helper `Token proposes; shipment confirms. Soft-clear removes distributor only (keeps Open Channel).`; chips `All 1035` / `Proposed 1035` / `Conflict 0`; buttons `Run shipment confirmer`, `Override selected`, `Soft-clear dist`.
- **GET review (API, unauthenticated, 200):** `total=1035`, `status_counts={"token_proposed":1035,"all":1035}`, first item `line_id=8420, case_id=146, distributor_attribution_status=token_proposed`.
- **Conflict filter (click, read-only GET):** innerText `Conflict 0` / `No lines in selected attribution statuses.` SQL `distributor_attribution_status = 'conflict'` → no rows.
- **After returning to All filter:** `All 1035` / `Proposed 1035` still; line 8420 still `token_proposed` with selection mark `✓`. Soft-clear **enabled** after select (`disabled: false`); **not clicked**.
- **Accept control:** no button whose text matches `/Accept/i` on `/admin/po-management` this run. Ship-corroborated Accept lives on Customer-token stamp (`Accept OC + dist {id}`) when `ship_corroboration_offer` is present; that section had no such offer. `Run shipment confirmer` is the in-section confirm path and POSTs `/confirmer/apply`.
- **Post-walk SQL:** `steward_audit_event` latest still id 62 dated 2026-08-08 (no new attribution events). Lines 344, 345, 8419, 8420 remain `token_proposed`.

#### Blocked

- **Proposed → Accept (HTTP write):** not performed. Running API `/health/ready` printed `API_CURRENT_DATABASE cip`. Prior note stands: env override of `DATABASE_URL_SYNC` in a probe script does not retarget the running API. Reason: would write `commercial_lineup_line` / `steward_audit_event` on `cip`.
- **Soft-clear (HTTP write):** control observed enabled after selecting line 8420; POST `/soft-clear` not sent. Same reason (`cip`).
- **Confirmer apply / no-auto-clear-on-conflict under write:** not performed (confirmer POST would write on `cip`). Zero `conflict` rows exist to demonstrate auto-clear vs remain-reviewable after a confirmer run.

#### Still outstanding

1. Point the **running** API at `cip_test`, prove `current_database()` from `/health/ready` (not from a sidecar script), then Accept / confirmer / soft-clear on a disposable row; post-query audit + `distributor_attribution_status`.
2. Re-seed or name a disposable analogue of historical smoke case **1016** if VERIFY still requires that id.
3. Exercise confirmer against a real `conflict` row (none on `cip` now) to capture no-auto-clear under mutation — only after (1).

---

### Unit 7 — Shipping labels and plan-vs-executed

#### Observed

- **Strip labels (rendered, plan quarter 26Q2, verbatim):** `Shipped (awaiting POD)` with value `10`; `Landed this quarter` with value `39,074`. Full strip innerText:

```
Lineup plan quarter — 2026 Q2
Planned

47,775

Shipped (awaiting POD)

10

Landed (plan quarter)

18,484

Landed this quarter

39,074

Pipeline

4,535

Slipped in

328

Slipped out

1,877

Unattributed

1,266,781

11 PO(s) link to multiple plan quarters — row attribution uses customer×product lineup match where possible.
```

- **HTTP `GET /api/v1/shipping/lineup-quarter-summary?plan_quarter=26Q2`:** 200; `planned_units=47775.0`, `shipped_units=10.0`, `landed_units=18484.0`, `landed_this_quarter_units=39074.0`, `shipped_not_landed_units=10.0`, `pipeline_units=4535.0`, `slipped_in_units=328.0`, `slipped_out_units=1877.0`, `unattributed_units=1266781.0`, `ambiguous_po_count=11`. Matches the rendered strip and the service-layer `lineup_quarter_summary` for 26Q2.
- **Fact spot-check (read-only, global, not lineup-attributed):** `fact_inbound_shipment` `line_state` counts `open_order=1405`, `shipped=13319`. Calendar 26Q2 (`pod_date >= 2026-04-01 AND pod_date < 2026-07-01`): **485 rows, 39074.0000 units** — equals summary `landed_this_quarter_units`. Global `line_state='shipped' AND pod_date IS NULL`: **308 rows, 26163.0000 units** — not equal to lineup-attributed `shipped_not_landed_units=10` (expected: summary is plan-quarter attributed).
- **`/plan-vs-executed` fill %:** From **26Q3** / To **26Q3** / All BUs. Tile **Fill rate (headline) 19.5%** (Line-hit 8.5%; 32,509 planned; 6,352 shipped against plan; Total shipped in scope 6,640). Pre-change cited value: `docs/UNIT8_DEMO_P2_GATE.md` **13.2%** (26Q3) on 2026-08-14. Copy still says `Fill rate uses in-plan shipped only.` Console: AG Grid pagination warnings only (no API 500).

#### Blocked

- None for read-only strip / HTTP summary / PvE tile once the no-reload API stayed up. (Earlier in this same run, `--reload` API drop caused `WinError 10061` until uvicorn was restarted without reload.)

#### Still outstanding

1. Consultant review of fill **19.5%** vs historical **13.2%** (26Q3) — data/time drift vs formula change; this artifact does not decide.
2. Write-path items remain those listed under 6f (API still on `cip`).

---

### Environment notes (this run)

| Item | Value |
|------|-------|
| `git rev-parse HEAD` | `eb65b5ccacd505acbb3f106e89b5c4140619dee9` |
| `git branch --show-current` | `feat/ns-1a-fx-readiness-chips` |
| Origin used for browser | `http://127.0.0.1:3000` (navigate first; origin-gated interact) |
| Web session | Already signed in (Local Admin); Sign out present |
| API `current_database()` via `/health/ready` | `cip` |
| `cip_test` write path | **not used** (API not pointed at it) |
| HTTP writes | **not attempted** |

---

## Prior gap record — 2026-08-30 ~21:09–21:20 UTC+2

**Collection timestamp:** 2026-08-30 (Sunday), ~21:09–21:20 UTC+2  
**Collector:** Cursor agent (subagent under parent VERIFY debt run)  
**Branch:** `feat/ns-1a-fx-readiness-chips`  
**HEAD:** `159b838f8393858dfdd68e23de7421353d14f041`  
**Environment:** local Windows; web `:3000`, API `:8001` (operator-declared); Redis `:6379` (not probed)  
**Database policy:** read-only on `cip` for queries; writes only on `cip_test` with `DATABASE_URL_SYNC` + `DATABASE_URL_SYNC_MIGRATE` env overrides; `ALLOW_TESTS_ON_DEV_DB` unset  

**Collection method:** Playwright MCP (`user-playwright`) for browser; Python sync/async service layer via `apps/api/scripts/ops/session_d_readonly_evidence.py` for read-only `cip` queries (psql not on PATH).

---

## Runtime blocker (material — browser + write paths)

**OBSERVED:** Live API through web proxy returns **HTTP 500** on authenticated and unauthenticated routes during this session. Browser console (Playwright) sample:

```
[ERROR] Failed to load resource: the server responded with a status of 500 (Internal Server Error) @ http://localhost:3000/api/v1/auth/login:0
[ERROR] Failed to load resource: the server responded with a status of 500 (Internal Server Error) @ http://localhost:3000/api/v1/shipping/lineup-plan-periods:0
[ERROR] Failed to load resource: the server responded with a status of 500 (Internal Server Error) @ http://localhost:3000/api/v1/commercial-planner/lineup/distributor-attribution/review?limit=200&status=token_proposed%2Cconflict:0
```

**OBSERVED:** Login attempt (`admin@local` / `changeme`) → UI alert **"Request failed (500)"**; session remains **Signed out**.

**Consequence:** Lineup-quarter strip labels, fill-rate tiles, distributor-attribution review rows, and Proposed→Accept / soft-clear browser actions **could not be exercised** against live data. Read-only DB + service-layer spot-check completed on `cip`. **No PASS/FAIL verdict.**

---

## VERIFY register context (from `docs/BACKLOG.md`)

| Unit | Shipped | VERIFY would check |
|------|---------|-------------------|
| **6f** | 2026-08-08 · PR #18 / D-040 | D-040 propose→confirm attribution: `distributor_attribution_status` transitions; Accept ship-corroborated; soft-clear; confirmer exact-qty Phase-1; no auto-clear on conflict; browser smoke Proposed **1016** |
| **7** | 2026-08-12 · BACKLOG-068 | Shipping lineup-quarter strip: `landed_this_quarter_units` (pod_date quarter) + `shipped_not_landed_units`; PvE fill rate untouched; strip labels match semantics |

**Prior shipped smoke (historical, not this session):** `CONTEXT.md` changelog records PR #18 merge with browser smoke PASS (Proposed 1016) on 2026-08-08. Case **1016 is absent on current `cip`** (see 6f.1).

---

## Section 6f — DistributorAttributionReviewSection

### Step 6f.1 — Pre-action DB query on `cip` (read-only)

**Command:**

```text
Set-Location apps\api; .\.venv\Scripts\python.exe scripts\ops\session_d_readonly_evidence.py
```

**Verbatim output (excerpt):**

```text
=== SESSION D read-only cip evidence ===

--- 6f.1 current_database ---
SELECT current_database()
('cip',)

--- 6f.1 cases (1016 or token_proposed) ---
SELECT c.id AS case_id, c.commercial_status, c.period_label
            FROM commercial_lineup_case c
            WHERE c.id = 1016
               OR c.id IN (
                 SELECT DISTINCT cll.case_id
                 FROM commercial_lineup_line cll
                 WHERE cll.distributor_attribution_status = 'token_proposed'
               )
            LIMIT 10
(135, 'draft_imported', '2025 Q2')
(114, 'po_pending', '2025 Q1')
(117, 'po_pending', '2025 Q2')
(123, 'po_pending', '2026 Q3')
(7, 'po_issued', '2026 Q2')
(125, 'po_pending', '2025 Q3')
(127, 'po_pending', '2026 Q1')
(119, 'superseded', '2026 Q1')
(144, 'superseded', '2026 Q2')
(121, 'po_pending', '2026 Q2')

--- 6f.1 lineup lines ---
...
(344, 7, 'token_proposed', 51, 9470, Decimal('15.0000'))
(345, 7, 'token_proposed', 51, 7323, Decimal('30.0000'))
...

--- 6f.1 status distribution ---
('token_proposed', 1035)
('shipment_confirmed', 3)
('steward_set', 2)

--- 6f.1 case 1016 lines (explicit) ---
(no rows)
```

**OBSERVED:** `current_database()` = `cip`. Case **1016 does not exist** (no case row, no lines). Nearest substitute with `token_proposed` lines: **case 7** (`po_issued`, `2026 Q2`), lines **344** and **345** (`distributor_id=51`). Status enum in DB is `token_proposed` (not literal `proposed`).

**EXPECTED:** Case 1016 or substitute with `token_proposed` rows for Accept workflow.

---

### Step 6f.2 — Browser: `/admin/po-management` → DistributorAttributionReviewSection

**Navigation:** `http://localhost:3000/admin/po-management` (Playwright MCP)

**Verbatim snapshot (excerpt):**

```yaml
- heading "Distributor attribution review" [level=6]
- paragraph: Token proposes; shipment confirms. Soft-clear removes distributor only (keeps Open Channel).
- button "All 0"
- button "Proposed 0"
- button "Conflict 0"
- button "Run shipment confirmer"
- button "Override selected" [disabled]
- button "Soft-clear dist" [disabled]
- alert: No lines in selected attribution statuses.
```

**OBSERVED:** Section **renders** (`data-testid="distributor-attribution-review"` in source). Review list **empty** (counts 0) — consistent with API 500 on review endpoint; operator **Signed out**.

**EXPECTED:** Proposed rows visible when review API returns `token_proposed` / `conflict` items (historical smoke targeted case 1016).

---

### Step 6f.3 — Proposed → Accept; soft-clear; no auto-clear on conflict

**Planned actions:** Select proposed row(s) → Accept / soft-clear / conflict check.

**Verbatim output:** *(not collected — no review rows in UI; login blocked by API 500; write path not attempted on `cip`)*

**OBSERVED:** No Accept, soft-clear, or conflict scenario performed in browser this session.

**EXPECTED (D-040 / BACKLOG VERIFY 6f):** `distributor_attribution_status` transitions (`token_proposed` → `shipment_confirmed` / steward paths); ship-corroborated confirmer; soft-clear; no auto-clear on conflict.

**Unit test evidence (prior session artifact, not live DB):** `apps/api/.tmp_session_a_unit6f.txt` — 10/10 passed in `tests/test_lineup_distributor_attribution.py` (sole_exact, multi_dist, conflict, phase2 DAP).

---

### Step 6f.4 — Post-action audit queries

**Pre-action baseline (read-only `cip`, same script):**

```text
--- 6f.4 recent steward_audit_event (pre-action baseline) ---
(62, datetime.datetime(2026, 8, 8, 17, 17, 17, ...), 'distributor_token', 'distributor_source_token_alias_mint', {...})
(52, datetime.datetime(2026, 8, 8, 16, 21, 13, ...), 'distributor_attribution', 'lineup_distributor_attribution_confirm', {'updated_count': 3, ...})
(51, datetime.datetime(2026, 8, 8, 16, 21, 12, ...), 'distributor_attribution', 'lineup_distributor_attribution_backfill', {'updated_count': 1019})
```

**Post-action (this session):** *(not collected — no browser write performed)*

**OBSERVED:** Latest attribution audit events dated **2026-08-08**; no new events from this collection run.

**EXPECTED:** Post-Accept audit row + line-level `distributor_attribution_status` consistent with UI action.

---

### Section 6f summary

| Check | OBSERVED | EXPECTED |
|-------|----------|----------|
| Pre-query case 1016 / proposed substitute | **1016 absent**; case **7** lines 344–345 `token_proposed` on `cip` | Case + proposed lines identifiable |
| PO Management section present | **Yes** — section chrome renders | `DistributorAttributionReviewSection` renders |
| Proposed → Accept | **Not exercised** (API 500, empty list) | Status transition + corroborated accept |
| Soft-clear | **Not exercised** | Soft-clear per D-040 |
| No auto-clear on conflict | **Not exercised** | Conflicts remain reviewable |
| Post-action audit + status | **Not exercised**; baseline audit 2026-08-08 | New audit + column state match action |

---

## Section 7 — Shipping labels and plan-vs-executed

### Step 7.1 — SH-01 / SH-02 definitions (grep)

**Grep:** `landed_this_quarter_units` / `shipped_not_landed_units` in `apps/` — hits in `inbound_lineup_quarter.py`, `ShippingLineupQuarterSummary.tsx`, `test_inbound_lineup_quarter.py`.

**Doc reference:** `docs/COMMERCIAL_SEMANTICS.md` §4 — fill uses `line_state='shipped'` only; landed axis uses `pod_date`.

**Unit test evidence (prior session artifact):** `apps/api/.tmp_session_a_unit7.txt` — 12/12 passed in `tests/test_inbound_lineup_quarter.py` including `test_accumulate_landed_this_quarter_vs_plan_landed`.

---

### Step 7.2 — Browser: `/shipping` lineup-quarter strip labels

**Navigation:** `http://localhost:3000/shipping` (Playwright MCP)

**Verbatim snapshot (excerpt):**

```yaml
- heading "Inbound shipments" [level=5]
- heading "Lineup plan quarter" [level=6]
- combobox "Plan quarter"
- alert: Request failed (500)
- paragraph: Signed out / Sign in required
```

**Verbatim `browser_find` for `"Shipped (awaiting POD)"`:** `No matches found` (strip not mounted — no plan quarter selected; API 500 on `lineup-plan-periods`).

**Source labels (tree evidence — `ShippingLineupQuarterSummary.tsx`):**

```text
label="Shipped (awaiting POD)"   → data-testid="lineup-q-shipped-not-landed"
label="Landed this quarter"      → data-testid="lineup-q-landed-this-quarter"
```

**OBSERVED:** Rendered strip labels **not captured** in live UI this session.

**EXPECTED:** Strip shows **"Shipped (awaiting POD)"** and **"Landed this quarter"** when plan quarter is selected and summary API succeeds.

---

### Step 7.3 — Browser: `/plan-vs-executed` fill %

**Navigation:** `http://localhost:3000/plan-vs-executed` (Playwright MCP)

**Verbatim snapshot (excerpt):**

```yaml
- heading "Plan vs Executed" [level=5]
- strong: Fill rate uses in-plan shipped only.
- alert: Request failed (500)
- combobox "From" (no value loaded)
- combobox "To" (no value loaded)
```

**OBSERVED:** No **Fill rate (headline)** tile value captured (`fmtPct(sc.fill_rate)` not rendered — scorecard API 500).

**EXPECTED:** Fill rate displayed per A1-01 shipped-basis semantics.

---

### Step 7.4 — Summary endpoint vs fact counts (one quarter)

**Service-layer read (same DB `cip`, `lineup_quarter_summary` — verbatim):**

```text
--- 7.4 fact_inbound_shipment by line_state ---
('open_order', 1405)
('shipped', 13319)

--- 7.4 lineup_quarter_summary 26Q2 ---
plan_quarter: 26Q2
plan_quarter_label: 2026 Q2
landed_this_quarter_units: 39074.0
shipped_not_landed_units: 10.0
landed_units: 18484.0
shipped_units: 10.0
planned_units: 47775.0
```

**HTTP API:** `GET /api/v1/shipping/lineup-quarter-summary?plan_quarter=26Q2` — **not collected** (API 500 via web proxy during browser session).

**OBSERVED:** For **26Q2**, service layer returns `shipped_not_landed_units=10`, `landed_this_quarter_units=39074`. Fact table has **13319** `shipped` + **1405** `open_order` rows (global, not quarter-filtered).

**EXPECTED:** Summary strip counts consistent with fact-layer predicates for chosen quarter (BACKLOG-088 residual gaps noted in semantics doc).

**OBSERVED vs EXPECTED:** Quarter-scoped reconciliation arithmetic **not completed** (no live API JSON; no manual SQL quarter aggregate run).

---

### Section 7 summary

| Check | OBSERVED | EXPECTED |
|-------|----------|----------|
| SH-01/SH-02 / BACKLOG-068 fields | Service + unit tests; source labels in TSX | Lifecycle + quarter strip semantics |
| `/shipping` strip labels (rendered) | **Not visible** (API 500, no quarter) | "Shipped (awaiting POD)", "Landed this quarter" |
| `/plan-vs-executed` fill % | **Not visible** (API 500) | Shipped-basis fill unchanged |
| API vs fact spot-check | **Partial** — service `26Q2` summary + global fact counts | Full HTTP + SQL quarter reconcile |

---

## Environment notes

| Item | Value |
|------|-------|
| `git rev-parse HEAD` | `159b838f8393858dfdd68e23de7421353d14f041` |
| `git branch --show-current` | `feat/ns-1a-fx-readiness-chips` |
| `docs/memory/CURRENT.md` | Branch `design-language-v1` — **differs** from working tree branch |
| Web session | Signed out; login 500 |
| API health (via web proxy) | **Degraded** — widespread 500 |
| `cip_test` write path | **not attempted** |
| Evidence script | `apps/api/scripts/ops/session_d_readonly_evidence.py` |

---

## Outstanding items (SESSION D incomplete)

1. **Restore API** on `:8001` / web proxy — re-run browser smoke after `auth/login`, `shipping/lineup-plan-periods`, and review endpoints return 200.
2. **6f:** Browser Accept + soft-clear on substitute case **7** lines 344–345 (or re-seed case 1016 on disposable DB); post-query `steward_audit_event` + `distributor_attribution_status` on `cip_test` for writes.
3. **7:** Select plan quarter on `/shipping`; capture rendered strip labels and PvE fill %; HTTP `GET /api/v1/shipping/lineup-quarter-summary` vs quarter-filtered SQL.
4. **Consultant review** — replace BLOCKED rows above when runtime green; still **no PASS verdict** until consultant sign-off.

---

## Verdict

**Evidence-only artifact.** Read-only `cip` DB + service-layer quarter summary collected; browser paths **blocked by API 500** and unsigned session. Historical 2026-08-08 smoke and pytest artifacts cited where live runtime unavailable. **No PASS/FAIL.**

---

## Run 2026-08-31 — Unit 6f browser VERIFY gap (cip_test writes)

**Collection timestamp:** 2026-08-31 (Monday), ~12:00–13:15 UTC+2  
**Branch:** `main` @ `15ab61ab99bf5db6e37691dfb43334b08aea220c`  
**Origin:** `http://127.0.0.1:3000` (cursor-ide-browser, serial)  
**API proof gate:** `GET /health/ready` → `{"status":"ready","database":"cip_test","ok":true}` before writes  
**Post-session restore:** `GET /health/ready` → `{"status":"ready","database":"cip","ok":true}`  
**Evidence only — no PASS verdict.**

### Seed + prep (cip_test)

| Item | Value |
|------|-------|
| Case | **44** |
| Lines | **25** ACCEPT (`SESSION-D-ACCEPT`), **26** CLEAR (`SESSION-D-CLEAR`), **27** CONFLICT |
| Prep script | `session_d_unit6f_browser_prep.py` — NULL `customer_id` on line 25; remove blocking alias so worklist shows `ship_corroboration_offer` (dist **92**) |

### Browser journey — `/admin/po-management`

1. **Before:** Drawer open; worklist item `SESSION-D-ACCEPT` shows **Accept OC + dist 92** (`customer-token-accept-ship-*`).
2. **Accept:** Green alert — *Accepted ship-corroborated distributor 92 on 2 line(s) (steward_set)*.
3. **Soft-clear:** Select line **26** → **Soft-clear dist**.

**Screenshots:** `docs/verify/artifacts/session-d-6f-before-accept.png`, `session-d-6f-after-accept.png`, `session-d-6f-after-soft-clear.png`

### Post-action SQL (`cip_test`, `verify_browser_query.py`)

```text
--- seed lines ---
current_database() cip_test
(25, 44, 92, 'steward_set', 'SESSION-D-ACCEPT')
(26, 44, None, None, 'SESSION-D-CLEAR')
(27, 44, 94, 'token_proposed', 'SESSION-D-CONFLICT')

--- audit tail ---
current_database() cip_test
(21, ..., 'lineup_ship_corroborated_distributor_accept', 'customer_token', 'session-d-accept', 'dim_distributor', 92)
(22, ..., 'lineup_distributor_soft_clear', 'distributor_attribution', ...)
```

### Unit 6f gap status

| Check | Captured? | Note |
|-------|-----------|------|
| Browser Accept on `token_proposed` / ship-corroboration offer | **Yes** | Case 44 line 25 |
| Browser soft-clear | **Yes** | Line 26 |
| `steward_audit_event` | **Yes** | ids 21–22 |
| `distributor_attribution_status` on seed lines | **Yes** | `steward_set` / cleared |

**Outstanding (not in scope this run):** Unit **7** browser strip / PvE fill still per prior BLOCKED rows above.
