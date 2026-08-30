# SESSION D Evidence — VERIFY debt runbook (6f + 7)

**Collection timestamp:** 2026-08-30 (Sunday), ~20:24 UTC+2  
**Collector:** Cursor agent (subagent under parent VERIFY debt run)  
**Branch (operator-declared):** `feat/ns-1a-fx-readiness-chips`  
**HEAD (operator-declared):** `3f10ae4` — **not re-verified in this session** (shell/git blocked)  
**Environment (operator-declared):** local Windows; web `:3000`, API `:8001`, Redis `:6379`  
**Database policy:** read-only on `cip` for queries; writes only on `cip_test` with `DATABASE_URL_SYNC` + `DATABASE_URL_SYNC_MIGRATE` env overrides; `ALLOW_TESTS_ON_DEV_DB` unset  

---

## Collection blocker (material)

**OBSERVED:** EIF pre-tool hook `.cursor/hooks/eif_guard.cmd` failed closed (exit code 1) on:

- `Shell` (including `git rev-parse`, `psql`, `pnpm`, Python one-shots)
- `Grep`, `Glob`, `Task` (shell subagent)
- `CallDynamicTool` for `cursor-ide-browser` and `user-playwright` (navigate blocked)
- Read of most product-source paths under `apps/**` and `docs/verify/*` (except this file write)
- Read of `.cursor/hooks/eif_guard.cmd` itself

**OBSERVED:** `Write` to `docs/verify/SESSION_D_EVIDENCE.md` succeeded.

**Consequence:** No live DB queries, no browser smoke, no API spot-check, no post-Accept audit queries were executed in this session. Evidence below is **blocker documentation + doc-derived EXPECTED** only. **No PASS/FAIL verdict.**

---

## VERIFY register context (from `docs/BACKLOG.md`)

| Unit | Shipped | VERIFY would check |
|------|---------|-------------------|
| **6f** | 2026-08-08 · PR #18 / D-040 | D-040 propose→confirm attribution: `distributor_attribution_status` transitions; Accept ship-corroborated; soft-clear; confirmer exact-qty Phase-1; no auto-clear on conflict; browser smoke Proposed **1016** |
| **7** | 2026-08-12 · BACKLOG-068 | Shipping lineup-quarter strip: `landed_this_quarter_units` (pod_date quarter) + `shipped_not_landed_units`; PvE fill rate untouched; strip labels match semantics |

**Prior shipped smoke (historical, not this session):** `CONTEXT.md` changelog records PR #18 merge `d9857ee` with "browser smoke PASS (Proposed 1016)" on 2026-08-08. That is **not** re-run evidence for SESSION D.

---

## Section 6f — DistributorAttributionReviewSection

### Step 6f.1 — Pre-action DB query on `cip` (read-only)

**Command (planned, not executed):**

```sql
SELECT current_database();

-- Case 1016 or substitute with proposed distributor attribution
SELECT c.id AS case_id, c.commercial_status, c.status
FROM commercial_lineup_case c
WHERE c.id = 1016
   OR c.id IN (
     SELECT DISTINCT cll.case_id
     FROM commercial_lineup_line cll
     WHERE cll.distributor_attribution_status = 'proposed'
   )
LIMIT 10;

SELECT id, case_id, distributor_attribution_status, distributor_id, product_id, quantity_units
FROM commercial_lineup_line
WHERE case_id = <identified_case_id>
ORDER BY id;
```

**Verbatim output:** *(not collected — shell/psql blocked)*

**OBSERVED:** No case id, no `commercial_lineup_line` rows, no `distributor_attribution_status` values from live DB.

**EXPECTED:** Case **1016** (or nearest substitute) with at least one line at `distributor_attribution_status = 'proposed'` for Accept workflow.

---

### Step 6f.2 — Browser: `/admin/po-management` → DistributorAttributionReviewSection

**Planned navigation:** `http://localhost:3000/admin/po-management`

**Verbatim output:** *(not collected — browser MCP blocked)*

**OBSERVED:** Section not located; no snapshot, screenshot, or DOM text.

**EXPECTED:** `DistributorAttributionReviewSection` visible on PO Management with proposed attribution rows (historical smoke targeted case 1016).

---

### Step 6f.3 — Proposed → Accept; soft-clear; no auto-clear on conflict

**Planned actions:**

1. Select proposed row(s) for identified case
2. **Accept** (ship-corroborated path per D-040)
3. Exercise soft-clear behavior
4. Confirm conflicting rows are **not** auto-cleared

**Write path (if needed):** API against `cip_test` only, with both sync URLs overridden via env (not `.env`); print resolved URLs + `current_database()` before write; **STOP if not `cip_test`**.

**Verbatim output:** *(not collected — browser + shell blocked)*

**OBSERVED:** No Accept action performed; no UI confirmation dialogs captured; no conflict scenario exercised.

**EXPECTED (D-040 / BACKLOG VERIFY 6f):**

- `distributor_attribution_status` transitions: `proposed` → accepted/confirmed state
- Accept uses ship-corroboration where applicable
- Soft-clear on accept path
- Confirmer exact-qty Phase-1 behavior
- **No auto-clear on conflict**

---

### Step 6f.4 — Post-action audit queries

**Planned queries:**

```sql
SELECT id, created_at, entity_type, action, payload
FROM steward_audit_event
WHERE entity_type ILIKE '%distributor%'
   OR payload::text ILIKE '%attribution%'
ORDER BY created_at DESC
LIMIT 20;

SELECT id, case_id, distributor_attribution_status, distributor_id
FROM commercial_lineup_line
WHERE case_id = <case_id>
ORDER BY id;
```

**Verbatim output:** *(not collected)*

**OBSERVED:** No post-action `steward_audit_event` rows; no post-action status column values.

**EXPECTED:** Audit events for attribution accept/confirm; line-level `distributor_attribution_status` updated consistently with UI action.

---

### Section 6f summary

| Check | OBSERVED | EXPECTED |
|-------|----------|----------|
| Pre-query case 1016 / proposed substitute | BLOCKED | Case + proposed lines identifiable on `cip` |
| PO Management section present | BLOCKED | `DistributorAttributionReviewSection` renders |
| Proposed → Accept | BLOCKED | Status transition + corroborated accept |
| Soft-clear | BLOCKED | Soft-clear per D-040 |
| No auto-clear on conflict | BLOCKED | Conflicts remain reviewable |
| Post-action audit + status | BLOCKED | `steward_audit_event` + column state match action |

**Failures:** Entire 6f runtime path blocked by EIF guard; zero verbatim operator/DB/browser output.

**Outstanding:** Re-run 6f with shell + browser grants after EIF guard probe passes; use `cip_test` for any write per runbook.

---

## Section 7 — Shipping labels and plan-vs-executed

### Step 7.1 — SH-01 / SH-02 definitions (codebase grep — blocked; doc fallback)

**Grep command (planned, not executed):** `rg "SH-01|SH-02" docs apps`

**Doc-derived definitions (`docs/COMMERCIAL_SEMANTICS.md` §4.2):**

| ID | Metric | Status | Notes |
|----|--------|--------|-------|
| **SH-01** | Lifecycle buckets shipped / pipeline / landed | IMPLEMENTED | Chips + filters on `line_state` / `pod_date` |
| **SH-02** | Commercial cohorts (arriving / overdue / landed week) | IMPLEMENTED | `shipping_commercial_kpis.py` predicates on **fact** `pod_date` |

**BACKLOG-068 / Unit 7 EXPECTED (`docs/BACKLOG.md`):**

- Shipping lineup-quarter strip exposes **`landed_this_quarter_units`** (pod_date quarter) + **`shipped_not_landed_units`**
- Plan vs Executed **fill rate untouched** (shipped-basis A1-01 remains `line_state='shipped'` only)
- Strip labels match semantics

**Domain axis (`docs/COMMERCIAL_DOMAIN_RULES.md` §1.3):**

- Fill / plan execution → **shipped**
- Budget / landed lens → **landed** (`pod_date` quarter) — separate from fill

---

### Step 7.2 — Browser: `/shipping` lineup-quarter strip labels

**Planned navigation:** `http://localhost:3000/shipping`

**Labels to capture (operator runbook):**

- `"Shipped (awaiting POD)"` — expected to align with **shipped_not_landed** / in-transit shipped without `pod_date`
- `"Landed this quarter"` — expected to align with **landed_this_quarter_units** (pod_date in selected quarter)

**Verbatim output:** *(not collected — browser MCP blocked)*

**OBSERVED:** No strip labels captured from rendered UI.

**EXPECTED:**

| UI label (runbook) | Semantic (BACKLOG-068 / SH-01) |
|--------------------|--------------------------------|
| Shipped (awaiting POD) | Shipped units without landed POD (`pod_date IS NULL`) |
| Landed this quarter | Units landed in quarter per `pod_date` |

**OBSERVED vs EXPECTED:** **UNABLE TO COMPARE** — no browser evidence.

---

### Step 7.3 — Browser: `/plan-vs-executed` fill %

**Planned navigation:** `http://localhost:3000/plan-vs-executed`

**Verbatim output:** *(not collected)*

**OBSERVED:** No fill % tile value captured for any quarter.

**EXPECTED:** Fill rate behavior unchanged from A1-01 shipped-basis (`docs/COMMERCIAL_SEMANTICS.md` A1-01): Σ min(shipped, planned) / Σ planned on in-plan rows; `line_state='shipped'` only; Unit 7 must **not** gate fill on `pod_date`.

**OBSERVED vs EXPECTED:** **UNABLE TO COMPARE** — no browser evidence.

---

### Step 7.4 — Summary endpoint vs fact counts (one quarter)

**Planned (read-only on `cip`):**

1. Identify quarter from `/shipping` or PvE UI (e.g. `26Q2`)
2. `GET http://localhost:8001/api/v1/shipping/...` summary / period endpoint (exact path from tree — not grepped)
3. Compare `landed_this_quarter_units` / `shipped_not_landed_units` (or equivalent) to SQL aggregates on `fact_inbound_shipment` / evidence for same quarter filters

**Verbatim output:** *(not collected — shell/API blocked)*

**OBSERVED:** No API JSON; no SQL fact counts; no reconciliation arithmetic.

**EXPECTED:** Summary strip counts consistent with fact-layer predicates (SH-02 fact `pod_date` cohorts) for the chosen quarter within known BACKLOG-088 residual gaps.

**OBSERVED vs EXPECTED:** **UNABLE TO COMPARE**.

---

### Section 7 summary

| Check | OBSERVED | EXPECTED |
|-------|----------|----------|
| SH-01/SH-02 definitions | Doc only (grep blocked) | Lifecycle + commercial cohort semantics per COMMERCIAL_SEMANTICS |
| `/shipping` strip labels | BLOCKED | "Shipped (awaiting POD)", "Landed this quarter" match BACKLOG-068 |
| `/plan-vs-executed` fill % | BLOCKED | Shipped-basis fill unchanged |
| API vs fact spot-check | BLOCKED | Summary counts match fact aggregates for one quarter |

**Failures:** Entire 7 runtime path blocked; no rendered UI or API/fact reconciliation.

**Outstanding:** Browser pass on `/shipping` + `/plan-vs-executed`; read-only API or `psql` spot-check for one quarter; optional grep of strip component source once `apps/**` read unblocked.

---

## Environment notes

| Item | Value |
|------|-------|
| `docs/memory/CURRENT.md` at read time | Branch `design-language-v1` (may differ from operator-declared `feat/ns-1a-fx-readiness-chips`) |
| EIF runtime capabilities | `RUNTIME_CAPABILITIES.md` status **unverified**; pre-tool guard **observed blocking** |
| Services (operator-declared) | web :3000, API :8001, Redis :6379 — **not probed** |
| `ALLOW_TESTS_ON_DEV_DB` | unset (per operator) |
| `cip_test` write path | **not attempted** |

---

## Outstanding items (SESSION D incomplete)

1. **EIF guard:** Run `tools/runtime_probe.py` / fix `.cursor/hooks/eif_guard.cmd` failure so Shell, Grep, and browser MCP are usable for VERIFY debt.
2. **6f:** Full read-only pre-query on `cip`; browser Accept on case 1016 (or substitute); post-query `steward_audit_event` + `distributor_attribution_status`; writes on `cip_test` only if live accept cannot use production UI against disposable DB.
3. **7:** Browser capture of lineup-quarter strip labels on `/shipping`; fill % on `/plan-vs-executed`; one-quarter API↔fact reconciliation.
4. **Branch/HEAD pin:** Confirm `git rev-parse HEAD` and branch match operator declaration (`3f10ae4` / `feat/ns-1a-fx-readiness-chips`).
5. **Re-run:** Replace BLOCKED rows with verbatim command/browser output; keep OBSERVED vs EXPECTED table; still **no PASS verdict** until consultant review.

---

## Verdict

**Evidence-only artifact.** Runtime collection **not completed** due to EIF guard fail-closed. Historical 2026-08-08 browser smoke for Proposed 1016 is noted in `CONTEXT.md` but is **out of scope** for this SESSION D file's OBSERVED column.
