# Steward Experience Contract

**Version:** 1.0 · 2026-07-23 · Owner: Warren
**Role:** The definition of done for ANY import steward/resolve surface. CONSULT may
only scope units as subsets of these rows. VERIFY walks these rows — not the unit
prompt's own checklist. Any row excluded from a unit requires an explicit
`Warren waived <row-id> <YYYY-MM-DD>` line in the unit prompt. No waiver line = row
is in scope = missing row is a STOP.

**Canonical paths** are the current living reference. After the consolidation arc
(Units A–C) they migrate to `features/import-steward/engine/*` generic modules —
update this doc in the same commit.

---

## Slot inventory

| ID | Slot | Requirement | Behavior (what the operator gets) | Canonical (pre-consolidation) |
|----|------|-------------|-----------------------------------|-------------------------------|
| S1 | Viewport shell | REQUIRED | Two-column workspace; list scrolls inside viewport on md+; drawer sticky beside list | `features/import-steward/StewardWorkspaceViewportShell.tsx` |
| S2 | Entity tabs + counts | REQUIRED | Per-entity tabs with total + needs-work counts; tab switch resets filters/selection to tab default | `StewardEntityTabsBar` + `useDsiEntityTabCounts` |
| S3 | Filters | REQUIRED | Chip filters (queue/status/plan_class as domain provides) + free-text search debounced 300ms; clear-to-default; at-default detection | `StewardCandidateFilters` + `dsiStewardCandidateFilterLogic` |
| S4 | Row columns — evidence density | REQUIRED | Key/token, row count, plan_class, top suggestion + confidence band; units/value columns wherever the domain has them (null-stubbing a column the domain can fill = PARTIAL) | `dsiResolutionWorkspaceTableProps` |
| S5 | Drawer — chrome | REQUIRED | Shared drawer chrome, close affordance, a11y label, testids | `StewardDrawerChrome` |
| S6 | Drawer — evidence body | REQUIRED | Sample raw source values, affected rows/cases, value at stake for THIS candidate. Operator never maps blind. | `DsiCandidateStewardDrawer` body |
| S7 | Drawer — ranked suggestions + override | REQUIRED | Ranked suggestion cards (band/score/reason), one-click map per card, override search-any-master below; never auto-create | CPOR drawer (`CporCandidateStewardDrawer`) is now the best reference for card mechanics; DSI for evidence |
| S8 | Selection + bulk | REQUIRED | Selection model w/ header state + select-all-visible; bulk actions run **preview → apply** two-step with per-row error summary. Direct bulk apply without preview = PARTIAL. | `DsiBulkStewardSection` + `useDsiBulkSteward` |
| S9 | Resolution plan | REQUIRED | Compute plan (async, non-blocking) → preview dialog with per-row detail → **apply-all-ready where each row goes to its own suggested target** → async apply with progress. plan_class labels without a consuming apply engine = annotation, NOT this slot. | `DsiResolutionPlanToolbar` + `useDsiResolutionPlan` |
| S10 | Async dispatch | REQUIRED | Validate/apply endpoints mark running + `pipeline_queued_at`, dispatch-claim guard, write task slot, return `{async, task_id}` immediately; broker → dev in-process thread → sync fallback. No long sync write in request path. | shipment `_dispatch_shipment_apply` / `cpor_historical_import.py` endpoints |
| S11 | Progress | REQUIRED | Fire-and-poll progress with phase/pct shape (`dsi-progress` contract); phase descriptions; background-task (bell) registration; terminal + failed states rendered | `ImportJobValidateProgressPanel` + `dsi-progress` endpoint shape |
| S12 | Pagination | CONDITIONAL | Server pagination when candidate volume can exceed ~500; client-side acceptable below with a written volume rationale in the unit prompt | `StewardCandidatesPagination` + `useDsiCandidatesPage` |
| S13 | Error surfaces | REQUIRED | Action feedback alert w/ dismiss; partial-success summaries after bulk/plan apply; load-error alert distinct from empty state | DSI section feedback + `planApplySummary` pattern |
| S14 | Domain invariants | REQUIRED | Never auto-create dims; FLAG ≠ BLOCK; ambiguous stays reviewable; stable IDs (real IDs, not string-hash row keys) | project rules + this contract |

---

## Rules of use

1. **CONSULT:** every steward-surface unit prompt lists the S-rows in scope. Rows
   not listed and not waived are IN scope by default.
2. **VERIFY:** walks S1–S14 against the shipped tree at path:line, comparative not
   boolean. Any REQUIRED row absent or PARTIAL without a waiver line → `VERDICT: STOP`.
3. **Waiver format (in the unit prompt, Warren's words only):**
   `Warren waived S<id> <YYYY-MM-DD>: <one-line reason>`
4. **Contract changes** require Warren's written OK and a version bump; agents never
   edit this file on their own judgment.
5. **New importer test:** if building the surface requires writing more than a config
   object + one section file + domain-specific drawer evidence, the engine has a gap —
   extracting the missing slot into shared IS in scope for that unit (see
   `import-parity.mdc`).

## Known gaps at v1.0 (close in consolidation arc)

- CPOR historical: S9 absent, S6 absent (nulled evidence), S12 unverified at volume,
  S14 violated by `cporTokenRowId` string-hash row keys.
- Engine layer (S8, S9, S6 body) exists only as DSI-named + Shipment-named twins —
  Units A–B extract/unify; Unit C mounts on CPOR.
