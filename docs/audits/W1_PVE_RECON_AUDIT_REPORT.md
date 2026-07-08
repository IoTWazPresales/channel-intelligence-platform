# W1 Plan vs Executed Reconciliation Audit

**Date:** 2026-07-08  
**Database:** `cip` (read-only)  
**Script:** `apps/api/scripts/ops/w1_pve_recon_audit.py`  
**Machine output:** `.tmp/w1_pve_recon_audit.json`  
**Gate:** **PASS** — all deltas explained by settled rules; no unexplained mismatches.

---

## 1a — Shipped (Job 310 ACZA)

| Layer | Shipped rows | Shipped qty | Unship rows | Unship qty |
|-------|-------------|-------------|-------------|------------|
| File (desktop xlsx) | 6,407 | 437,215 | 689 | 53,284 |
| `shipment_evidence_line` (active) | 6,391 | 436,593 | 689 | 53,284 |
| `shipment_evidence_current` | 6,391 | 436,593 | 689 | 53,284 |
| `fact_inbound_shipment` (job 310) | 5,960 | 436,468 | 689 | 53,284 |

**Explained deltas:**

- **+16 file rows / +622 shipped qty** vs evidence — invoice-line identity keys collapse multi-item rows within `(delivery, invoice_line)` groups.
- **Unship** — exact match file ↔ evidence.
- **Fact −431 shipped rows / −125 qty** vs evidence — `fact_upsert_key` collapse + latest-job-wins graduation (expected).

---

## 1b — Planned 26Q2

| Metric | Value |
|--------|-------|
| Active cases | 4 |
| Lineup lines | 336 |
| `quantity_units` sum | **27,218** |
| `raw_row_payload` parsed qty | **27,218** (0 delta) |
| 1H splits | None |

PvE linked-case scope sums **26,978** planned units — expected subset of all active 26Q2 cases.

---

## 1c — Category recompute 26Q2 (all BUs)

| Metric | Value |
|--------|-------|
| Execution rows | 330 |
| Fill rate | **43.4%** |
| Short exposure | 15,265 units |

**Exception categories** (direct = API): short_ships 13 · over_ships 4 · unplanned_intake 7 · no_po_blind_spots 8.

**Flag summary:** matched 74 · short 61 · over 8 · unshipped 75 · unplanned 28 · amended 39.

Scorecard + flag tie-out: **all checks pass**.

---

## 1d — PO Management

| Metric | Value |
|--------|-------|
| POs observed / linked | **2,241 / 389** |
| Period×BU need lineup upload | **139** |
| Gap worklist `total_gap_rows` | **6,706** |

**Gap grain** (`lineup_po_gap.py` lines 3–7, 97–101, 159):

> A **(PO, product)** shipment grain is a gap when `purchase_order_id` is not linked through `commercial_lineup_case_po` to a case whose lineup contains that `product_id`. Quantities from `fact_inbound_shipment` shipped lines only.

**W1d decision:** Metric is **line-grain** (PO×product pairs). Chip label should read **"6,706 gap lines"** not "shipment gaps" (W4).

---

## Gate outcome

Proceed to W2–W4. No UNEXPLAINED mismatches.
