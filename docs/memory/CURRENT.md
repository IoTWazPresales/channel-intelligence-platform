# CURRENT state

**Last updated:** 2026-08-02 (A2-04/05 smoke PASS on main)

**Branch:** `main` @ `d313e57` · prior schedules work on `feat/report-schedules-beat` (PR #17)

**Alembic:** `20260802_0009` on cip / code head

## Done

- Merged + pushed `fix/commercial-foundation-pod` → main (`094c3ee`); WoC ~13.6→~25.0 = correct POD-backfill consequence.
- Merged + pushed `feat/a2-norms-comparable-close` → main (`42b61a3` + provenance `d313e57`).
- **Browser smoke PASS** CPOR Cases:
  - Norms: trailing **4Q** window `2026Q2·2026Q1·2025Q4·2025Q3`, anchor `2026Q2`, **source=`commercial_tenant_profile`**, `env_override_active=false`.
  - Top customers (real $): Esquire avg **$25,560** / 11.3% SRP · Computer Mania **$16,946** / 17.8% · Game **$22,139** / 11.8% (19 customers in window).
  - Case `#292` comparables: **296** candidates ranked; axes visible (same customer · BU overlap · same promo · Q prox · vol).
  - Empty surfaces: **none** on norms/comparables. Portfolio correctly omits claim-rate (A2-03 non-computable).

## A-lane status (built vs SPEC)

| ID | Status |
|---|---|
| A1-01…08 | IMPLEMENTED (PvE) |
| A1-09 support bias | **SPEC ONLY** — planned side unblocked (Q-002); CPOR surface not built |
| A2-01/02/04/05/06 | **IMPLEMENTED** (browser-proven for 04/05) |
| A2-03 claim rate | **DO NOT BUILD** until distinct owed (Q-008/D-027) |
| A2-X incremental cost | **DO NOT BUILD** (BACKLOG-089) |
| A3-01…04 | IMPLEMENTED (Channel Ops; YoY coverage rule live) |

**A-lane remains:** A1-09 support-bias surface on CPOR Cases. Everything else A1–A3 is shipped or explicitly blocked.

## Next

1. A1-09 (support bias) **or** leave A-lane and pick B-lane / PR #17 / residuals.
2. Residuals: P4–P6 / Q-004 CST formats; SKU economics steward seed before B-lane UI.

**Env:** local Windows. API `:8001` (started this session), web `:3000`.
