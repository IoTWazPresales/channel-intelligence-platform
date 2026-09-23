# D-h: Proposed vs executed intelligence (feature-definition seat, 2026-09-24)

Lenses: product-manager, commercial-sales-strategist, product-interaction-designer, ui-visual-design-specialist, architecture-specialist. The Skill tool was denied (`SHIM_TOOL_UNMAPPED`), so the lenses were applied from their charters. Nothing was rendered: UI claims come from source, not visual review.

## 1. AS-IS

- **VERIFIED:** `/plan-vs-executed` ships. API: `apps/api/app/services/commercial_planner/plan_vs_executed.py`, endpoint `api/v1/endpoints/plan_vs_executed.py`. UI: `apps/web/src/features/plan-vs-executed/PlanVsExecutedView.tsx`. Tests: `tests/test_plan_vs_executed.py` and the View test.
- **VERIFIED:** A1-01..A1-08 are built (`compute_scorecard_from_execution_rows`, `compute_volume_bias`, `compute_slip_summary`, `_compute_trend`) and catalogued in `docs/COMMERCIAL_SEMANTICS.md` §4.1.
- **VERIFIED:** "Deal-stock landing" was **renamed** to A1-02 Over-plan intake, defined as Σmax(shipped−planned,0), "overship vs plan, not POD". Nothing measures whether deal stock *landed* (POD).
- **VERIFIED:** A1-07 bias is an **unweighted mean of per-line ratios**. It needs at least 3 lines per BU (`VOLUME_BIAS_MIN_LINES`). The PM view copies the BU view (`pm_attribution_mode=business_line`), so no PM is identified as a person.
- **VERIFIED:** `apps/api/app/services/lineup/bias_correction.py` feeds A1-07 into the B2 net requirement (`apply_bias`, off by default). It uses the **single default quarter**, so a one-quarter bias can scale the next buy plan.
- **VERIFIED:** The trend is a per-quarter series over the selected range, limited by loaded history.
- **ASSERTED (brief measurement):** 36 lineup cases, 2025Q1..2026Q3. Three period labels are malformed. Pre-2025 history is absent (N-0060 blocked). `product_line` is NULL on 10 products.
- **VERIFIED:** W1 reconciliation audit PASS (`docs/audits/W1_PVE_RECON_AUDIT_REPORT.md`) for 26Q2 only: fill 43.4%, 75 of 330 rows unshipped.

## 2. Lenses

**Product / commercial**
- The job is "should I trust this PM's / BU's plan next quarter?" The measures today are too thin to answer that, so this is a **readout**, not a new module.
- Plan accuracy and bias belong in PvE. Adding a surface would split ownership, which COMMERCIAL_SEMANTICS §1 forbids.
- Over-plan intake answers "did we take more than planned." Warren's "landing rate" probably means "did deal stock arrive and sell". That is a different metric. It needs a definition from Warren.
- **Disagreement (commercial vs PM):** commercial wants a PM leaderboard. PM/product holds that without person attribution and at least 6 quarters, any ranking is noise and politically costly.

**UX / design**
- Put a **Planning accuracy** tab (or section) on `/plan-vs-executed`: a BU × quarter heatmap of signed bias with a history-depth badge per cell.
- Every cell shows n lines, n quarters and a confidence state (insufficient / indicative / established). Never show a bare percentage.
- The B2 `apply_bias` toggle must show which quarters and how many lines the correction came from before the user applies it.
- A drill-down from a cell to its lines already exists (exception lens). Reuse it.

**Architecture**
- Keep it derived-on-read over `reconcile_case`. Add no new fact table until history exceeds about 20 quarters × 24 lines, when performance would be measured.
- Bias math must be **unit-weighted** (Σ(s−p)/Σp), with the mean ratio kept alongside it. Otherwise small lines dominate.
- BU key = `dim_product.product_line` per D-g. The keys must match between PvE, bias_correction and B2 `product_bu`.
- Period canonicalisation (N-0058 data rules) is a precondition: a malformed label silently drops or double-counts quarters.
- **Disagreement:** a stored snapshot per closed quarter (immutable "as-judged") vs live recompute. Recommendation: live recompute now, and add a closed-quarter snapshot only once late POs are shown to rewrite history materially.

## 3. Recommendation

**When to start:** the **definition-only** node can start now. **Build starts after N-0040** (D-g BU sweep) and **N-0058** (period/import data rules). Plan accuracy v1 can ship on 2025Q1+ data. **Bias as a trusted signal is gated on N-0060** (historical backfill) or on 8 closed quarters accumulating naturally (about 2027Q1). Landing rate depends on **N-0062** (Arrived state). It is independent of N-0050, N-0057, N-0061 and N-0063.

| Measure | Numerator / denominator | Grain / period | Source | Min history | Must NOT claim when thin |
|---|---|---|---|---|---|
| Plan accuracy | 1 − Σ\|s−p\| / Σp (WAPE), with A1-01 fill alongside | product_line × closed quarter; SKU drill | `commercial_lineup_line`, linked POs, `shipment_evidence_line` shipped | 1 closed quarter (quarter is closed when no pipeline remains, or after +1Q) | Must not score open quarters: pipeline is not a miss |
| Deal-stock landing rate | Units over plan that reached POD in window ÷ units over plan (Warren to confirm) | product_line × quarter | A1-02 rows + `pod_date` / N-0062 Arrived | 2 quarters | Must not treat shipped as landed (BACKLOG-088 POD under-count) |
| PM planning bias | Σ(s−p)/Σp signed, with dispersion across quarters | planner (person when mapped, else product_line) × rolling 4–8 closed quarters | same as accuracy + slip A1-08 | ≥6 closed quarters and ≥3 lines per quarter to show direction; ≥8 to feed B2 | Must not show a "consistently over/under" label, a ranking or a B2 auto-correction below that threshold |

Surfaces: a PvE **Planning accuracy** section, plus provenance on the B2 bias chip in `/lineup`. Journey: open PvE → choose BU → see accuracy trend and bias with depth badge → drill to lines → use it (or not) in the next B2 plan.

## 4. Acceptance criteria (unstarted node)

1. The WAPE accuracy and unit-weighted signed bias per product_line × closed quarter tie out to a golden fixture and to W1-style recon for at least 2 quarters.
2. Every bias figure carries `quarters_n`, `lines_n` and `confidence ∈ {insufficient, indicative, established}`. Thresholds live in tenant config.
3. Open quarters, and lines with pipeline remaining, are excluded from accuracy and shown as "pending".
4. B2 `apply_bias` refuses (returns a reason) below the "established" threshold and exposes its source window.
5. Malformed period labels and NULL product_line are counted and reported, never silently dropped.
6. The landing rate uses POD / Arrived only and is labelled distinctly from Over-plan intake.
7. Person-level PM bias appears only when a person field is mapped. Otherwise the UI states "by business line".
8. COMMERCIAL_SEMANTICS §4.1 is updated in the same PR (new IDs A1-10..A1-12).

## 5. Findings

- **F1:** `.eif/CONTEXT.md`, `DECISIONS.md` and `JOURNEYS.yaml` are empty templates, and `DESIGN_EXPERIENCE_RECORD.md` is `status: template`. There was nothing to check against, so the actual canon is `docs/COMMERCIAL_SEMANTICS.md`.
- **F2:** The existing B2 bias correction uses one quarter at a mean-of-ratios with n≥3. This is a live over-claim risk (R2) today, before any new work.
- **F3:** The PM grain in COMMERCIAL_SEMANTICS lists NB/NR/NV/NX. The data holds NB/NR/NV/PF/XB, and D-g sets the grain at 14 product_lines. The three disagree.
- **F4:** PLAN_VS_EXECUTED_SPEC.md and the SHIPPED_TAXONOMY doc point at each other for the UX layout. The layout text exists only in git history.

**Questions for Warren:**
1. By "deal-stock landing rate", do you mean extra units **arriving** (POD), **selling through**, or just being **taken over plan** (already built as Over-plan intake)?
2. Is "PM" a person? If so, who owned each BU plan in each quarter? Should bias follow the person or the business line?
3. How many quarters of history must exist before you'd trust a bias number enough to let it change a buy plan?
4. When does a quarter count as "closed" for scoring: end of quarter plus how long?
5. Should late or slipped shipments count against the plan's own quarter, or be judged on the quarter they actually shipped in?
