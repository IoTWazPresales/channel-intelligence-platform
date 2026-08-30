# SESSION D Evidence — VERIFY debt runbook (6f + 7)

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
