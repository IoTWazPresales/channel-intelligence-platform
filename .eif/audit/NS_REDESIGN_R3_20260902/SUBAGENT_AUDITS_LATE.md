# Late subagent audits — corroboration record

Two explore subagents were launched early in run `NS_REDESIGN_R3_20260902` and were blocked mid-audit by
the EIF guard (FAULT_FINDINGS E-9). Their reports surfaced only after the r3 package commits
(`b9d20ee`…`f5e251b`). They are recorded here **as corroboration**; the authoritative audits remain
`PRODUCT_CAPABILITY_AUDIT.md` and `COMPONENT_ECOSYSTEM_AUDIT.md`, which the parent run wrote from its own
source reads. Both subagents ran the same model as the parent — this is not independence.

Agent ids: `e633f1f2-a2d1-44a3-baab-f667ef3368b3` (product capability), `83434a12-fb1b-4a1b-99a5-5e7805be2a70`
(component ecosystem). Full transcripts live in the session's subagent output folder.

## Agreement with the committed audits

- `packages/ui` = tokens/theme/AG-Grid bridge only (5 files); reusable behavioural UI is web-local
  (`components/`, `features/import-steward`, `features/shell`, `features/import-mapping`,
  `features/steward-worklist`). The reconciliation's "no reusable UI" inference is false.
- Duplication is concentrated in North-Star container chrome (TaskCrumb / RegimeStrip / ScopeBar / a forked
  LineupReadStrip), confirm dialogs, column pickers and four inline Recharts call sites — not "everything".
- Brief signal set, SOH derivation (`reported − sell_out + landed`), weeks-of-cover, replenishment flag
  (`0 < woc < 4.0`), dashboards as governed semantic widgets (`kpi|table|bar|line|area`, promote-to-saved-report)
  all match the capability audit.
- `RecommendationMixin` entities (StockRisk, BuyRecommendation, PricingRecommendation, PromoReadiness,
  CompetitivePositioning, LineupGapAnalysis, RoadmapRecommendation, BudgetJustificationSummary) are populated
  only by `seed_demo.py` — confirms the prototype's rule of showing no recommendation/impact figures.
- `/market` is placeholder-only and outside the spine; promotions page text says scaffold plans/readiness are
  parked; roadmap is a thin list — consistent with data-gating Competition / Roadmap / Budgets.

## Details the committed audits did not state (new, minor)

| Finding | Source | Effect on direction |
|---|---|---|
| `useUiStore.openDrawer` is called (dashboard, buy-plans, exceptions) but nothing renders `drawerOpen/drawerTitle/drawerContent` — orphaned API | component audit §4 | Supports `EntityContextPanel` as the drawer primitive; retire the store fields in Phase A |
| `useMediaQuery` has zero matches in `apps/web/src` (production); responsive = shell breakpoints only | component audit §7 | Confirms the mobile gap; prototype introduces `useMediaQuery`-driven card transforms |
| IBM Plex Mono is referenced by string in NS `sx` but not loaded via `next/font` in root layout | component audit §3 | Design-language v2 must decide the mono face and load it; today it falls back |
| Competition page has working CRUD for competitor mappings/prices (medium), not a pure stub | product audit §8 | **Nuance for D-0007:** the data-gating rule hides Competition because it *derives* nothing; it does *store* competitor prices. Options: keep hidden until a derived metric exists (current), or surface it as a second leaf under Commercial inputs beside Price observations. Flag for Phase A scoping, no prototype change |
| Control-tower `/dashboard` route still exists but middleware redirects it to `/brief`; its `dashboard/summary` KPIs are unreachable | product audit §2 | The composed Overview absorbs this — nothing lost |
| `/admin/mappings` legacy queue coexists with import-steward engine; banners point to DSI resolution | product audit §9 | Matches D-0002 deferral: both paths remain reachable |
| `fx_blocked_zar` is a hard `0.0` placeholder in Brief | product audit §1 | Prototype's funding "blocked" figure is a count, not an amount — keep it that way |

## Coverage gaps the subagents declared

Endpoint bodies for channel-ops, cpor_cases, query, lineup, plan-vs-executed, commercial_planner, report
services; AppShell badge wiring; NS container mobile behaviour. The parent run's audits covered lineup,
CPOR, reports and the semantic layer from direct reads; the remaining UNKNOWNs (report schedule/delivery
formulas, plan-vs-executed fill % formula) do not affect the IA decision and are not claimed anywhere in
the prototype.
