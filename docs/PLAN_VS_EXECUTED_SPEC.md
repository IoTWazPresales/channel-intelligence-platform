# Plan vs Executed — Intelligence View Spec (v1)

Status: build reference. Depends on rollup-attribution fix 1586f1e (reconciliation is
now BU-true per product_line). Hard trust dependency: BACKLOG-066 (#39/#40) — see §8.

## 1. Purpose & positioning
The differentiating asset — proposed-vs-executed — not an operational screen. Answers
one question at three altitudes: did the channel ship what the lineup planned, and
where did it diverge. Read-first; it never asks the user to DO work (that is PO
Management) — it reports what happened and what it means. Not a reskin of PO
Management (a worklist); this is the readout of the reconciliation that worklist
produces.

Personas → entry:
- Exec: did we ship what we said, what moved, how did the lineup perform → scorecard
  + fill-rate trend (loads above the fold).
- Sales: is my customer under/over-allocated, are PMs allocating right → exception
  list, customer lens.
- PM: did I plan correctly, where did deal-stock land above plan → exception list,
  product/BU lens.
Operational needs (what needs linking/POs/closing) stay on PO Management, reached by
deep-link, never duplicated.

## 2. Where it lives
Top-level primary nav "Plan vs Executed". NOT under /admin, NOT inside Commercial
Planner. Commercial Planner and PO Management deep-link INTO it. Lineup-page removal
is PARKED pending a consumer audit — not in scope here.

## 3. Scope boundaries — answered vs labeled-out
v1 reconciles plan vs shipped-to-channel. It does NOT know whether stock sold, or
whether a shipment was cancelled. These are labeled out-of-scope in-UI, never faked:
- Did it sell / is it aging → DSI sell-out + SOH velocity (different fact layer).
- Cancelled vs never-shipped-yet vs never-planned → not modeled; `unshipped` means
  "planned, nothing shipped on a linked PO yet", NOT "cancelled" (BACKLOG-063).
- Branch/location-tagged intake → deferred by design.
Worked example (Ryzen 3): "undershipped to my customers" = answered (short exposure
per customer); "one customer took far above need" = answered as intake above plan
(over/unplanned), NOT as justified-vs-not; "then it sat at distribution for months" =
OUT (sell-through/DSI); "or was it cancelled" = OUT (not modeled); "material bias" =
v2 longitudinal PM-bias, shaped-for here.

## 4. Information architecture — three layers
Layer 1 — Portfolio scorecard (above the fold, exec/BU default). KPIs per §5. Six
flags collapse to three buckets: Executed-vs-plan (matched+short+over), Off-plan
(unplanned+amended), Pending (unshipped+awaiting-PO). Six flags preserved for drill.
Layer 2 — Ranked exception lists (worst offenders first, not a full grid). Drill
spine B: ONE shared scorecard, exception lists pivotable across EXACTLY three lenses —
by customer / by product / by BU (no arbitrary pivots). Categories per lens: top
short-ships, top over-ships/deal-stock, biggest unplanned intake, no-PO blind spots.
Ranked by units or value (toggle).
Layer 3 — Drill: period → BU → customer → product to the six-flag grain.

## 5. Metric definitions (over-ship is never penalised)
Per plan line = (customer × product), planned P, shipped S on a linked PO. Off-plan
lines: P=0, S>0.
- Fill rate (HEADLINE): Σ min(S,P) / Σ P over in-plan lines. Over-ship capped at plan;
  over on one line never masks short on another.
- Line-hit rate (SECONDARY): % of plan lines where S ≥ P (fully filled). Shown beside
  fill rate.
- Planned vs shipped: Σ P vs Σ S.
- Short exposure: Σ max(P−S,0). Sales' pain number.
- Deal-stock landing (over): Σ max(S−P,0) on in-plan lines. PM-positive, its own
  measure, never red.
- Unplanned intake: Σ S on off-plan lines. The off-plan/assist story; a why, not the
  headline.
- No-PO blind spot (FIRST-CLASS KPI + lens): customers/lines with P>0 but no linked-PO
  shipment — count + units/value at risk. Surfaced prominently: hiding what cannot be
  reconciled erodes trust.
Value: every unit metric also in cost value, USD AND local (ZAR), carrying the
FX-partial annotation (state coverage, never silently mix). FX-completeness is NOT
this module. Ranking toggle: units | cost value.

## 6. Longitudinal
v1: KPI trend — scorecard KPIs by quarter (fill-rate-by-quarter etc.); period is a
TREND AXIS, not a locked filter. v2: PM planning-bias across years (systematic
under/over-call per customer/BU) — the moat; shaped-for now (period is a first-class
range dimension in the read model), built later. Data-shape rule: the read model must
aggregate the same reconciliation across an arbitrary period RANGE so v2 is a query,
not a re-architecture.

## 7. Data contract (derived-on-read, no schema change)
A read/aggregation layer over reconcile_case (post-1586f1e, per-product_line correct):
per period, union the per-(customer×product) rows across all linked cases; project/
rank by lens; aggregate to the scorecard. Nothing stored. It is a READER not a writer
— it MUST consume the corrected backlog/reconcile_case projection path, never a
parallel aggregation that reintroduces whole-case attribution (one reconciliation
truth). Projection note: a BU group can surface `unplanned` where the case has planned
lines in OTHER BUs — correct under the product_line filter; the view adds BU context
in drill so it reads correctly. Performance: aggregating reconcile_case across a
period's cases (and across quarters for trend) is potentially heavy on local PG — v1
bounds to the selected period(s); the trend series is a bounded/precomputed KPI query,
not N live reconcile_case calls per quarter.

## 8. Hard dependency & caveats
- BACKLOG-066 (#39/#40): under per-product_line projection the duplicated 72-line
  workbook double-counts planned units WITHIN a BU group for 25Q1 and 24Q4. Other
  periods are clean → build in parallel, but affected periods MUST carry an in-UI
  data-quality flag until repaired.
- Near-empty "linked" groups (e.g. 26Q1 NX, 24Q4 PF) are TRUTH not a bug — PO linked
  via a multi-BU shipment, real plan never uploaded/unlinked. Treat as a no-plan/no-PO
  blind-spot signal, do not hide.
- Evidence operand is clean (shipment_evidence_current; 0 implicated scopes on the
  parity worklist).

## 9. Multi-tenant discipline
BU grouped by product_line grain but display label is tenant config (never hardcode
NB/NR). Period calendar, currency, legal-form rules are tenant config. The three
lenses (customer/product/BU) are generic axes. Period is a trend axis, not a hardcoded
quarter set.

## 10. Non-goals (v1)
No sell-through/velocity; no cancellation modeling; no branch/location tagging; no
FX-completeness work (annotate only); no PM-bias statistics (v2, shaped-for); no new
writers; no migrations; no PO-Management slimming (separate surface); no #39/#40
repair.
