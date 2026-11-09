# Warren decisions — 9 Nov 2026 (SAST)

Record of Warren's choices on 9 Nov 2026 (Africa/Johannesburg) for decisions that were accepted on 4 Nov 2026 without a recorded option. Source conversation: CIP manager chat, widget "How should I settle the 16 decisions with no recorded choice?" → "Show me the 16 with your proposed defaults first", then Warren's follow-up answers.

This file does **not** edit `.eif/program/PROGRAM.yaml` or any EIF ledger. A separate approved ledger update can promote these later.

---

## Settled

### D-0026 — answered by D-0042 (1 Oct 2026)

D-0026's five Plan vs Executed questions were settled by **D-0042** on 1 Oct 2026. No new choice needed on 9 Nov.

### D-0118 — accepted as proposed

Proposal (`.eif/program/PROGRAM.yaml` D-0118):

> N-0115 proposed for Warren: CST sales value converted to the tenant sales-value VAT setting per row vat_basis exactly as the sell-through overview does; no listing-price estimate for unpriced units.

**Warren 9 Nov 2026:** accepted.

### D-0120 — accepted as proposed

Proposal (PROGRAM.yaml D-0120):

> N-0115 proposed for Warren: Shipments period date = ship confirm date; alternative POD date (landed).

**Warren 9 Nov 2026:** accepted (ship confirm date).

### D-0123 — accepted as proposed

Proposal (PROGRAM.yaml D-0123):

> N-0115 proposed for Warren: CPOR open = cases that are not superseded and whose workflow_status is not in a closed set (settled, ended, cancelled, rejected, voided), as the portfolio service excludes; CPOR value = support USD (ttl_support_usd, the compute currency) with ZAR shown beside it. Alternatives: status column instead of workflow_status; estimate value instead of support.

**Warren 9 Nov 2026:** accepted.

### D-0124 — accepted as proposed

Proposal (PROGRAM.yaml D-0124):

> N-0115 proposed for Warren: per-customer stock cover and restock flags on the starter dashboards reuse the sell-through code definitions if they exist (per-customer replenishment weeks of cover setting); if not, the widget shows reported on-hand beside per-week sell-through and no derived cover number.

**Warren 9 Nov 2026:** accepted.

### D-0126 — accepted as proposed

Proposal (PROGRAM.yaml D-0126):

> N-0116 proposed for Warren: Migration 0048 and the definition script run on the clone (rolled back) and cip_test only; applying them to cip waits for Warren's go (dual path: not migrating is safe).

**Warren 9 Nov 2026:** accepted.

### D-0119 — proposal REJECTED; carry-forward rule recorded

Proposal that was rejected (PROGRAM.yaml D-0119):

> N-0115 proposed for Warren: Distributor reported stock by period = latest count per distributor and product in each bucket, no carry-forward, shown with pairs reporting; Channel Ops derived stock and weeks of cover stay governed and keep refusing period.

**Warren 9 Nov 2026 rule:** distributor reported stock **always carries forward** from the last count until a newer count replaces it. A period with no report shows the carried-forward count and must be **flagged as carried forward**. (No period starts from zero for want of a fresh report.)

**Build status:** not started (new work item below).

### D-0130 — agent review screenshots only

Proposal (PROGRAM.yaml D-0130):

> N-0116 proposed for Warren: Real-data screenshots of the starters: the agent does not sign in, so starters are rendered on design-lab fixtures shaped like v2 responses; alternative grant the app role on a cip clone and run an API on it.

**Warren 9 Nov 2026:** applies to **agent review screenshots only**. The product always shows live data. Dummy/fixture screenshots are for coding-agent review reports that cannot sign into the live app; they do not change product behaviour.

### D-0035 — remove smoke-test case; re-import may change status

**Warren 9 Nov 2026:**

1. The smoke-test case (**case 3 / BATCH0-SMOKE-001**) must **not** remain. Removal from `cip` is a **separate explicit, reviewed step** (pending — see new work items).
2. Case 310 cancel stays as recorded.
3. Re-importing historical data **may** change case status. No skip-guard for post-import lifecycle transitions. Re-import of history is not expected to repeat.

### D-0036 — accepted as built; cases stay editable

**Warren 9 Nov 2026:** accepted as built today:

- line windows stay as they are and are flagged;
- out-of-window claims are reported but not counted;
- a service check for overlapping windows comes later;
- historical lines keep their own windows;

and cases remain **manually editable** when needed.

### D-0037 — accepted as built defaults

**Warren 9 Nov 2026:** accepted as built defaults:

- product dates where end-of-life comes before launch: flag and leave; ask the data owner;
- steward edit that puts retirement before launch: warn;
- import warning `launch_after_end_of_life` stays **FLAG** (not a commit block).

### D-0038 — add tolerance flag (future build)

**Warren 9 Nov 2026:**

- Add a **tolerance flag** to the customer SOH check (default **10%** gap, tenant-adjustable setting).
- Flag stock **wherever it sits**.
- Evetech is compared on **units only** (no cost supplied in their SOH/CST rows).

**Build status:** not started (new work item below). Today's check remains report-only until this lands.

### D-0025 — BOM Not Ready stays out; user picks sheets

**Warren 9 Nov 2026:**

- **BOM Not Ready** sheets stay out of standard shipment import.
- The user selects which sheets to import at import time.

**Code status (read-only check 9 Nov 2026 on `feat/integrate-20261103` tip):**

- Sheet-selection feature **is already built**:
  - API: `default_selected_sheets`, `selected_sheets_for_job`, `initial_sheet_selection`, `remember_selected_sheets` in `apps/api/app/services/imports/shipment_evidence_import.py` / `shipment_field_mapping.py`.
  - UI: "Choose sheets to import" dialog (`data-testid="shipment-sheet-picker"`) in `apps/web/src/app/(app)/admin/imports/page.tsx` when `sheet_selection_confirmed` is false and more than one sheet is available.
- **BOM Not Ready is not excluded by default today.** `_PREFERRED_SHEET_KEYS` still includes `"bom not ready"`, so that tab starts selected and can be ingested as `acza_workbook_bom_not_ready` (`shipment_evidence_report_detect.py`). The operator can uncheck it. Aligning defaults with this decision (and with D-0046 of 1 Oct 2026) is remaining product work under BACKLOG-046 / N-0072 — not done in this docs PR.

### D-0020 — deferred to end of build

**Warren 9 Nov 2026:** pre-2025 lineup archive load will be done when the system is finished. **Not blocking** any current work.

### D-0034 — approved if safe; execute separately

**Warren 9 Nov 2026:** cleanup (stale worktrees / stale clone DBs per N-0046 inventory) is approved **if safe**. Must be executed as a separate careful step (never touch `cip` or `cip_test`; archive session notes first; wait until active pytest on those DBs is finished). **Pending** — see new work items.

---

## Still pending Warren

### D-0041 — PF Qty vs Total Qty; BU resolver thresholds

Still **PENDING Warren**. Research summary for the follow-up question (not a decision):

- **PF** is used in the repo as a **product-line code** (folder/grain alongside NB/NX/NR/…; e.g. `Product Lineup/PF/…` in `docs/STATE_AUDIT_2026-08-02.md`). No source in the repo expands the letters into words.
- **BACKLOG-105** / STATE_AUDIT proof on file `Copy of ACZA 1H 2025 Consumer Lineup - Gaming Desktop PD 13 Feb 2025.xlsx`: source row 1 had `Qty=0.15`, `Total Qty=1`, `May (TBC)=1`. Code aliases map header `Qty` → `quantity_units` (`lineup_header_mapping.py`: `["qty", "quantity", "units", "forecast_qty"]`) and do **not** map `Total Qty`. Stored quantities were the uniform half of the mis-mapped `Qty` cell, not `Total Qty`.
- Newer local Gaming Desktop samples checked on 9 Nov (Q2 2026 / Q4 copies under Documents\Lineup Files) only exposed a `Qty` header on the probed sheets — no `Total Qty` column on those files.
- **BU thresholds (BACKLOG-055)** in `lineup_business_unit_resolution.py`: `LIKELY_NOT_LINEUP_RESOLUTION_RATE = 0.05` flags `bu_likely_not_lineup` when under 5% of rows resolve to products; `PRODUCT_DERIVED_MIN_RESOLVED_FRACTION = 0.25` means the product-derived BU tier only wins when at least 25% of rows resolve. Both are provisional guesses, not empirical archive rates.

Await Warren's choice on which quantity column the PF/desktop family should use, and whether to keep or retune the 0.25 / 0.05 thresholds.

---

## New work items (not yet started)

| ID | From | Work | Status |
|----|------|------|--------|
| WI-D0119-carry-forward | D-0119 | Distributor reported-stock by period: carry forward last count; flag carried-forward periods | not started |
| WI-D0038-soh-tolerance | D-0038 | Customer SOH check tolerance flag (default 10%, tenant setting); units-only for Evetech; flag stock wherever it sits | not started |
| WI-D0035-smoke-remove | D-0035 | Explicit reviewed removal of case 3 BATCH0-SMOKE-001 from `cip` | not started (cip write — held until dedicated step) |
| WI-D0034-cleanup | D-0034 | Safe stale worktree + stale clone DB cleanup per N-0046 inventory | not started (separate safe execution) |
| WI-D0025-bom-default | D-0025 / D-0046 | Align shipment default sheet selection so BOM Not Ready does not start selected / is not ingested unless the operator explicitly chooses it | not started (feature exists; default still includes BOM) |

---

## Explicit non-goals of this PR

- No edits to `docs/BACKLOG.md`, `docs/memory/CURRENT.md`, or anything under `.eif/`.
- No code, migrations, or pytest.
- Do not merge until reviewed.