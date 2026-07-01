# Spec C — Bulk historical lineup backfill

**Status:** Design locked (2026-06-30). Implementation not started.  
**Purpose:** Proposed-vs-executed intelligence asset — backfill all historical commercial lineup workbooks into `CommercialLineupCase` / `CommercialLineupLine`, then link to PO/shipment truth.  
**Branch context:** `feat/unit-6-unified-lineup-import-centre` (Session B unified importer is operational baseline; bulk panel is net-new).

---

## 1. Goals

- Ingest **all** historical lineup files (~3–4 per quarter × ~5 years; **~30 workbooks** found on disk in discovery sample — **confirm full archive location before Step C**).
- Produce steward-reviewed, supersession-safe cases at grain **(period, customer, business_unit)**.
- Enable PO↔lineup reconciliation and proposed-vs-executed reporting without blocking on catalogue completeness.
- Reuse DSI **engine** patterns (async dispatch, task ledger, preview/collision, idempotent apply) — **not** the row-grain steward UI.

---

## 2. Scope

### In scope

- File-grain bulk steward panel (preview → collision review → apply).
- Multi-**file** batch upload for backfill (see §4 — status changed 2026-06-30).
- Multi-**case-per-file** sheet/BU fan-out (see §3.4).
- Layered period inference + `1H` → Q1+Q2 split.
- Latest-wins supersession on `(period, customer, BU)`.
- Advisory `referenced-but-not-in-catalogue` worklist (see §6).

### Out of scope (this spec)

- Changing DSI resolution tier order or eligibility.
- Auto-create `dim_product` / `dim_customer` / `dim_distributor` from lineup evidence.
- Retaining dual versions of superseded planned-qty history (Warren: latest-wins only).

### Known parse-failure shapes (bulk panel must detect → `needs_attention`, not force-parse)

| Shape | Example | Signal |
|-------|---------|--------|
| **PF spec-dump sheet** | `PD Lineup 13 Feb 25` (job **#217** on `cip`) | 200+ PM attribute columns; near-zero product-resolution rate |
| **Multi-BU in one sheet** | `1. ACZA Q1 2025 Consumer` = **NB + NR** | Current unified importer ingests **one sheet only** → silently drops half; **multi-sheet fan-out mandatory** |

---

## 3. Import model

### 3.1 Grain

- One `CommercialLineupCase` per **(file, sheet/BU slice, period quarter)** after fan-out.
- Customer rows remain line-grain inside the case (existing `CommercialLineupLine` model).

### 3.2 Period inference

**Amended 2026-06-30 — Q2 RESOLVED.**

Period = **layered inference stack** (never silent auto-pick on conflict):

1. **Folder path** — e.g. `NR\2025\Q3`, `26Q2` (required when filename/title lack year).
2. **Title band (F1)** — e.g. `2026 1H NEW PLAN`, `2025 Q2 NEW PLAN`.
3. **Filename** — year + quarter or `1H`.
4. **Manual fallback** — steward entry when all signals fail.

**Rules:**

- **`1H` ALWAYS splits into Q1 + Q2** — planning is per-quarter everywhere; one `1H` file → two cases (or two period labels in preview).
- **Conflicts** (title vs filename vs folder disagree, e.g. Q4 filename / Q3 title band) → surface to steward in bulk panel; **never** auto-picked.

**Discovery evidence (30-file sample, 2026-06-30):** 63% title-band; 67% filename; 20% folder-only; ≥1 title/filename mismatch.

### 3.3 Header row and sheet selection

- Header row floats (row 1 NR/NV/PF/XB `Sheet1`; row 4 NB consumer; row 2 NV Q4) — reuse historical signature scan + unified token heuristics.
- Skip junk sheets (`summary`, empty trailing `Sheet1`).
- Reject spec-dump sheets to `needs_attention` (§2 table).

### 3.4 Multi-case-per-file (sheet / BU fan-out)

**Confirmed mandatory 2026-06-30.**

When a workbook contains multiple data sheets (e.g. `NB` + `NR` on `1. ACZA Q1 2025 Consumer`), the bulk importer must **fan out** one case per sheet/BU slice — not first-sheet-wins (`lineup_case_parser._load_df` behaviour today).

Customer-slice files (Desktop `…AMAZON.xlsx` vs master `1./2. ACZA Q2 2026 Consumer`) are separate collision/supersession inputs, not silent overwrites.

### 3.5 Business unit resolution

**Amended 2026-06-30 — prerequisite for supersession key.**

BU derivation hierarchy (mismatches + multi-BU-in-one-sheet surfaced to steward):

1. **Product-derived** (strongest) — SKU → `dim_product` → `business_unit` (catalogue-grounded).
2. **Shipment-derived** — when SKU absent from catalogue, corroborate from shipment evidence for same customer/period.
3. **Sheet code** — `NB`, `NR`, etc.
4. **Folder** — archive path segment (`NB/`, `NR/`, …).
5. **Manual** — steward override in bulk panel.

`product_line` (catalogue-majority / filename) remains for display/grouping; **it is not a substitute for BU on the supersession key**.

---

## 4. Upload model (multi-file)

**Status changed 2026-06-30 — was non-goal, now IN-SCOPE.**

> **Reversal note:** Earlier Spec C drafts marked multi-**file** bulk upload as **non-goal** (single embedded Commercial Planner upload was sufficient for forward ops). That is **superseded**: ~30+ file historical backfill is required for the proposed-vs-executed intelligence asset. Session B Unit 6 (`UnifiedLineupImportDialog`) ships multi-file upload with **shared manual period** and **one case per file** — adequate for forward ops only, **not** for bulk backfill (missing collision panel, `1H` split, multi-sheet fan-out, supersession).

Bulk backfill needs:

- Multi-**file** batch + multi-**case-per-file** (§3.4).
- File-grain steward preview (collisions, supersession, period conflicts).
- Step C link-apply after steward commit.

---

## 5. Sequencing and delivery

**Amended 2026-06-30.**

| Step | Deliverable | Blocks |
|------|-------------|--------|
| **A — Schema prereq** | `business_unit` as first-class column on `commercial_lineup_case` + BU derivation resolver wired at parse/preview. Supersession key `(period, customer, BU)` is undefined without it (today only `product_line` exists). | Step B |
| **B — Bulk file-grain steward panel** | New surface reusing DSI lifecycle/ledger/preview/collision **engine** (async apply, activity feed, idempotent commit). File-grain review, not row-grain. Handles §3 period/BU/collision rules + parse-failure rejection. | Step C |
| **C — Backfill session** | Operator-run import of full archive → period-by-period link-apply (PO auto-link / confirm). **Confirm full archive path** before execution (~30 files found in OneDrive `Product Lineup`; 2021–2024 tree not in sample). | — |

**This spec update (2026-06-30) precedes Step B implementation.**

---

## 6. PO↔lineup linking and catalogue independence

**Added 2026-06-30.**

### Linking key

PO↔lineup links are **catalogue-independent**. Links reconcile on:

`(period, customer, business_unit, purchase_order)`

— **not** gated on `dim_product` membership. A line links, reconciles, and reports whether or not its SKU is in the catalogue.

### Catalogue absence

- Missing `dim_product` match → **flag** on line/case (`catalogue_miss` or equivalent diagnostic).
- **Never blocks** link, reconcile, or backfill apply (same philosophy as DSI-ignore).

### Referenced-but-not-in-catalogue worklist

New **advisory** worklist: SKUs / sales-model names appearing in lineups and/or shipments with no `dim_product` match, carrying referencing evidence (file, row, shipment line). Feeds catalogue stewarding (parked ~482-token gap). **Advisory only — never blocking.**

### Over-ship vs planned

Over-ship vs lineup planned qty is **expected** when PM deal-stock inflates real intake above planned. Confidence tier for auto-link **ignores** over-ship; over-ship is a **reconciliation flag**, not a confidence penalty (audited 2026-06-30: 0 linker false-negatives in 26Q2 where lineup exists).

---

## 7. Supersession

**Resolved 2026-06-30.**

- **Key:** `(period, customer, business_unit)` — requires Step A `business_unit` column.
- **Rule:** Latest-wins — a later file for the same key **replaces** the earlier case (mirrors `source_key` fact-table pattern).
- **Revised replaces original** — no dual-retention of superseded planned-qty history (Warren decision).
- Bulk panel must surface collision groups **pre-commit** (discovery: 18 groups in 30-file sample at customer grain).

---

## 8. Open questions

### Q1 — Full archive location

**Open.** Discovery scanned `OneDrive - ASUS\ACZA Consumer - Sales\Consumer PM Team\Product Lineup` (30 workbooks). Confirm whether additional years/BU folders exist before Step C.

### Q2 — Period inference vs manual entry

**RESOLVED 2026-06-30.** See §3.2 layered stack + `1H` split + conflict surfacing.

### Q3 — Multi-file upload scope

**RESOLVED 2026-06-30.** In scope — see §4 reversal.

### Q4 — Supersession retention

**RESOLVED 2026-06-30.** Latest-wins only — see §7.

---

## 9. Discovery references

- Variability inventory: `.tmp/lineup_variability_inventory.json` (read-only discovery, 2026-06-30).
- PO auto-link audit: `.tmp/audit_po_auto_link_engine.py` (0 false-negatives; 8,569 gap rows ~96% upload-backlog).
- Existing parsers: `lineup_case_parser.py`, `lineup_period_inference.py`, `historical_lineup.py`, `unified_lineup_import.py`.

---

## 10. Correction log

| Date | Change |
|------|--------|
| 2026-06-30 | First committed version. Locked Q2, §3.4, §4 (non-goal→in-scope), §5 sequencing (A→B→C), Step A `business_unit` prereq, supersession, catalogue-independent linking, advisory worklist, parse-failure shapes. |
