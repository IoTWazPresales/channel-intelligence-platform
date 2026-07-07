# Plan vs Executed — Shipped / Pipeline / Landed taxonomy (addendum to PLAN_VS_EXECUTED_SPEC.md)

Status: build reference. Corrects the fill-rate leak confirmed on cip 2026-07 (recon
summed open_order into shipped). One canonical lifecycle; every surface maps to it.

## Canonical states
| State | Rule (fact_inbound_shipment / evidence) | Executed? |
|---|---|---|
| Unshipped | zero evidence quantity on linked PO | No — planned, nothing yet (NOT cancelled; cancelled = BACKLOG-063) |
| Pipeline | line_state = 'open_order' (allocated, not shipped) | No — separate forward bucket, never in fill |
| Shipped | line_state = 'shipped' (left OEM, truth layer) | YES — the fill-rate bar |
| Landed | pod_date IS NOT NULL | Sub-state of shipped; OUT of PvE v1 fill; needed later for landing-quarter KPI attribution |

## Fill rate
fill_rate = Σ min(shipped, planned) / Σ planned, where shipped = line_state='shipped' only.
Over-ship capped (met plan). Pipeline and unshipped never count toward fill.

## Pipeline
open_order units surface as their own scorecard tile and split the pending story:
a plan line with open_order inbound but zero shipped = "inbound / pipeline"; a plan line
with neither = "cold". Never summed into shipped/fill.

## Landed (out of v1, flagged)
pod_date exists on shipping evidence only; reconcile_case does not read it. v1 fill does
NOT gate on landed. Known gap: ~3% of shipped-state units on linked POs are shipped-not-
landed (pod_date NULL) yet credited as executed. Landing-quarter attribution (crediting
units to the quarter they landed, not the plan quarter) is future work — see BACKLOG.

## Surface alignment (all converge on the table above)
- reconcile_case: was the ONLY leak (summed all evidence); now line_state='shipped' gated.
- PO Management coverage meter + lineup_po_auto_link: already gate on line_state='shipped'
  (pattern reused here); auto-link already splits pipeline — keep.
- Shipping module: lifecycle authority (line_state, pod_date filters). Unchanged.

## Corrected figures (cip, read-only 2026-07)
26Q2 fill 45.96%→41.80%; shipped_units_in_plan 16,751→12,648 (4,103 were open_order).
Full range fill 62.43%→61.10%.
