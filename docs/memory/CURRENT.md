# Current state

**Last updated:** 2026-07-06 (Plan vs Executed UX + PO Management slim)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/unit-6-unified-lineup-import-centre` |
| **HEAD** | (pending) — plan-vs-executed UX repair + PO Management worklist slim |
| **PR** | None open |
| **Alembic (code)** | `20260702_0066` (head) |
| **Alembic (DB)** | **`20260702_0066`** on local `cip` |

---

## Database and environment

| Field | Value |
|-------|--------|
| **Active DB** | Local Postgres `cip` @ `127.0.0.1:5432` (topology B) |
| **Bitemporal flags** | `CIP_SHIPMENT_BITEMPORAL_DUAL_WRITE` / `_READ` — **default ON** |
| **Observation store** | View `shipment_evidence_current` **14,673** rows (post graduation repair; was 14,847) |
| **Invoice-line graduation** | **174** lineages quantity-graduated on cip; **432** blank observation versions superseded; audit `invoice_line_graduation_gap` = **0** |
| **Legacy supersede** | 35,134 + graduated blank corpus lines `corpus_superseded_at` |
| **Celery dispatch** | `broker` (apps/api/.env) |

---

## PO Management rollup attribution — CLOSED (2026-07-06, `1586f1e`)

| Item | Status |
|------|--------|
| `backlog()` BU-true projection | **Done** — product rows filtered by group `product_line` (product-first, `business_unit` fallback) |
| Customer chip re-summarization | From projected rows only |
| `po_no_match` | Deduped per linked PO in group |
| Formerly-identical BU pairs on cip | **Diverge** — 26Q2 NV/NR, 26Q1 NX/NV, 25Q1 NR/NB, 24Q4 PF/NR |
| `linked_po_count` / coverage counting | Unchanged |

**Projection flag-note (intelligence view):** `unplanned` / `amended` stay as computed per product row. A BU group may show `unplanned` where the case has planned lines in **other** BUs — correct per `product_line` filter; Plan vs Executed drill adds BU context in-UI.

---

## Plan vs Executed intelligence view — DONE (2026-07-06)

| Item | Status |
|------|--------|
| Spec | `docs/PLAN_VS_EXECUTED_SPEC.md` |
| Read model | `plan_vs_executed.py` — `reconcile_case` product rows + `product_line` projection filter |
| API | `GET /api/v1/plan-vs-executed` (commercial-planner gated) |
| UI | `/plan-vs-executed` — scorecard, 3-bucket + 6-flag, 3-lens exceptions, trend, drill grid |
| Nav | Commercial Planning group — "Plan vs Executed" (top-level route, not under `/admin`) |
| Deep-links | Commercial Planner guide + PO Management alert |
| 26Q2 KPI tie-out (cip read-only) | **PASS** — fill 45.96%, line-hit 35.36%; over-ship does not reduce fill rate |
| BACKLOG-066 UI flag | Warning when range includes 25Q1 / 24Q4 |
| Period enumeration fix (2026-07-06) | `available_periods` from `coverage()` groups — independent of active filter; default latest |
| Round-2 hardening (2026-07-06) | Exception AG grids, product lens SKU/sales-model/description toggle, cross-drill, PO Mgmt deep-link params, loading-state fix, golden tie-out tests all clean periods |
| UX repair + PO slim (2026-07-06) | One full-width exception category grid (tabs inside lens); human-readable product labels (description→sales_model→SKU) in exceptions + drill + chip; product selector drives drill column; PO Management linked cards → compact status + PvE deep-link only (recon chips removed; APIs unchanged) |

---

## Lineup PO lifecycle + Open Channel plan — DONE (2026-07-05, `88f8db4`)

| Item | Status |
|------|--------|
| PO link → `po_pending` (not `po_issued`); steward open through `in_fulfillment` | Wired + unit-tested |
| Explicit `POST …/close-work` → `work_closed`; list hides work-closed by default | Wired + unit-tested |
| Open Channel plan parity | TMP provisional dim **#19** aliased to system **OPEN_CHANNEL #1** for plan/reconcile/auto-link; `effective_lineup_customer_id` on staging |
| PO auto-link proposals | `group_planned_units` = full customer-period plan (not PO-matched SKUs only) |
| Bulk link UX | Chunked apply (100/request), top progress bar, success counts |
| Bulk link on cip | **191** new `commercial_lineup_case_po` rows proven live (~2026-07-05) |

**Mental model:** PO linked (`po_pending`) ≠ work closed (`work_closed`) ≠ archive. Restart API + hard-refresh web after pull.

**Data hygiene (optional):** merge/remap TMP Open Channel customer **#19** → **OPEN_CHANNEL #1** — reads already alias.

---

## Invoice-line mint graduation — DONE (2026-07-04)

| Step | Status |
|------|--------|
| Write path (dual-write hook) | Quantity-gated supersede / `invoice_partial_graduation` flag |
| One-time repair | Preview 174 full / 0 partial; **13,685** double-count units; clone + cip green |
| Integrity audit | `invoice_line_graduation_gap` check added |
| Change events | `graduated` + `graduation_kind: invoice_mint` on lineage thread |

**Preview impact (pre-repair):** 174 lineages · top double-count 26Q2 Open Channel 5,581 units.

**Sample invoice_mint event:** order `151126051002768` line `1.1` item `90NR0NG1-M00C30` → `ship:15260187716|…|8883|1`.

---

## Plan D cutover — DONE (2026-07-02)

| Phase | Commit | Gate |
|-------|--------|------|
| 1 Identity + clone proof | `9109664` | `cip_planD_smoke` green; 0 split collapse |
| 2 cip cutover | `1b77efc` | Migration 0066; jobs 153/154 backfilled; dual-write ON |
| 3 Consumers + supersede | `6de21b8` | Audit **5b=0**; 35,134 superseded; parity worklist measured post-cutover |
| 4 Change events v1 | `91f227e` | API + CLI; unit tests green; real chain spot-check jobs 32/40 |

**Integrity audit (cip):** `evidence_true_dupes` (5b) = **0** · `evidence_fact_parity` = **10** on cip today (2026-07 audit; **184** was the pre-audit Plan-D cutover figure — steward worklist shrank after graduation/supersede) · `duplicate_qty_inflation_groups` = **0**.

**Open→shipped fact double-count (diagnostic only, BACKLOG-062):** 104 matching pairs; open qty 5,752 / shipped qty 7,224 — remediation deferred.

**Sample change event (jobs 32→40):** `order:151126031011047|1.1|90NR0KS1-M00EW0` — `est_pod` slip −1 day, `erd` slip −1 day.

---

## Consumer read sources (after Plan D)

| Consumer | Read source |
|----------|-------------|
| DSI corroboration (cache + per-row) | `shipment_evidence_current` |
| DSI receipt disambiguation | `shipment_evidence_current` |
| DSI product tiebreak | via corroboration (current view) |
| Lineup PO reconciliation / suggested POs / BU resolution | `shipment_evidence_current` |
| Shipment evidence API list/get | `shipment_evidence_current` |
| Shipping ETA LAG metrics | `shipment_evidence_observation` partitioned by `line_identity_key` |
| Channel ops, usage counters | `shipment_evidence_current` |
| Steward writes / import apply | `shipment_evidence_line` (unchanged) |

---

## Dev topology

Local desktop (no Docker): `pnpm dev:api` :8001 · `pnpm dev:web` :3000 · `pnpm dev:worker` (Redis :6379) or `CIP_DEV_CELERY_DISPATCH=in_process_thread`.

---

## Next

- **Unit 6 browser soak** — Plan vs Executed category tabs + drill labels + PO Management worklist-only cards.
- **BACKLOG-066** — #39/#40 duplicate-ingestion repair (steward soft-supersede; Plan vs Executed flags affected periods in-UI until repaired).
- **BACKLOG-067** — backfill file-provenance gap (unified_lineup / bulk_backfill paths retain no original bytes).
- **Spec C Step C:** archive lineup backfill + link-apply.
- **BACKLOG-062:** Warren decision on open→shipped fact remediation (104 pairs measured).
- **BACKLOG-057/058:** D4/D5 legacy column deprecation after soak.
- **Perf (defer):** bulk PO apply still one DB commit per item — batched writer if volume grows.

---

## Discovery hints (for next agent — verify in code + cip)

| Surface | Grain / trigger (code truth — re-verify) |
|---------|------------------------------------------|
| `po_management.backlog` | Groups: `(year, quarter, product_line)` from `fact_inbound_shipment`; linked groups **project** `reconcile_case` product rows matching group `product_line` → `reconciliation_summary` + `reconciliation_customers` |
| `plan_vs_executed` | Period options from `po_management.coverage` observed groups (full history); scorecard/trend filtered by From..To range; default latest quarter |
| `reconcile_case` | `(case × customer × product)`; product rows carry `product_line` + `business_unit` |
| Current Lineup recon UI | `CaseReconciliationInline` = case-level (out of scope for BU projection) |
| Assign distributor button | `RESOLUTION_UI_STATUSES` && `!superseded` — no unassigned-line gate in UI |

---

## Prior session context (abbreviated)

Unified lineup import Units 1–8 backend done; Unit 6 frontend wired. Spec C Step A/B done (`20260701_0064`/`0065`). Distributor full merge on `cip`. PO rollup attribution fixed `1586f1e`. Data integrity audit tool (`10fd3ea`).
