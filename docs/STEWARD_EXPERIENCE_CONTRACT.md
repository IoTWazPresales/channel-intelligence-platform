# Steward Experience Contract

**Version:** 1.5 · 2026-07-27 · Owner: Warren  
**Role:** The definition of done for ANY import steward/resolve surface. CONSULT may
only scope units as subsets of these rows. VERIFY walks these rows — not the unit
prompt's own checklist. Any row excluded from a unit requires an explicit
`Warren waived <row-id> <YYYY-MM-DD>` line in the unit prompt. No waiver line = row
is in scope = missing row is a STOP.

**Canonical paths** are the living reference after Unit A–E1 (generic engine +
composition + CPOR + shared drawer + CST import steward). Update this column when the consolidation arc moves modules.

**S6 split (v1.3):** payload enrichment (candidate API + list columns) vs drawer
evidence **UI** body. Unit C owns payload; Unit D owns shared drawer body UI (`StewardEvidenceSummary` / `StewardSuggestionCards`).

**Unit E (v1.5 / D-018):** CST **import** resolution (`customer_sell_through` candidates),
not the `/admin/cst-steward` ops page.

---

## Slot inventory

| ID | Slot | Requirement | Behavior (what the operator gets) | Canonical (v1.5) |
|----|------|-------------|-----------------------------------|------------------|
| S1 | Viewport shell | REQUIRED | Two-column workspace; list scrolls inside viewport on md+; drawer sticky beside list | `features/import-steward/StewardWorkspaceViewportShell.tsx` |
| S2 | Entity tabs + counts | REQUIRED | Per-entity tabs with total + needs-work counts; tab switch resets filters/selection to tab default | `StewardEntityTabsBar` + consumer tab-count hooks (`useDsiEntityTabCounts` / shipment route `useShipmentEntityTabCounts`) |
| S3 | Filters | REQUIRED | Chip filters (queue/status/plan_class as domain provides) + free-text search debounced 300ms; clear-to-default; at-default detection | `StewardCandidateFilters` + consumer filter logic |
| S4 | Row columns — evidence density | REQUIRED | Key/token, row count, plan_class, top suggestion + confidence band; units/value columns wherever the domain has them (null-stubbing a column the domain can fill = PARTIAL) | Consumer workspace column builders (e.g. `dsiResolutionWorkspaceTableProps`, shipment route columns, CPOR section columns) |
| S5 | Drawer — chrome | REQUIRED | Shared drawer chrome, close affordance, a11y label, testids | `StewardDrawerChrome` / `StewardCandidateDrawer` |
| S6 | Drawer — evidence body | REQUIRED | Sample raw source values, affected rows/cases, value at stake for THIS candidate. Operator never maps blind. **Payload** (API + list columns) may land before shared drawer UI. | `StewardEvidenceSummary`; DSI panel; shipment/CPOR drawers bind shared summary |
| S7 | Drawer — ranked suggestions + override | REQUIRED | Ranked suggestion cards (band/score/reason), one-click map per card, override search-any-master below; never auto-create | `StewardSuggestionCards` (CPOR + shipment); DSI domain actions compose |
| S8 | Selection + bulk | REQUIRED | Selection model w/ header state + select-all-visible; bulk actions run **preview → apply** two-step with per-row error summary. Direct bulk apply without preview = PARTIAL. | `StewardBulkSection` + `useStewardBulkSteward` (DSI via `DSI_ENGINE_CONFIG`; shipment via `SHIPMENT_ENGINE_CONFIG`) |
| S9 | Resolution plan | REQUIRED | Compute plan (async, non-blocking) → preview dialog with per-row detail → **apply-all-ready where each row goes to its own suggested target** → async apply with progress. plan_class labels without a consuming apply engine = annotation, NOT this slot. | `useStewardResolutionPlan` + `StewardResolutionPlanToolbar`; DSI `useDsiResolutionPlan`; shipment `SHIPMENT_ENGINE_CONFIG`; CPOR `CPOR_HISTORICAL_ENGINE_CONFIG` |
| S10 | Async dispatch | REQUIRED | Validate/apply endpoints mark running + `pipeline_queued_at`, dispatch-claim guard, write task slot, return `{async, task_id}` immediately; broker → dev in-process thread → sync fallback. No long sync write in request path. Interactive steward plan/bulk may use a dedicated steward slot (not SLOT_MAIN) mirroring shipment. | shipment `_dispatch_shipment_apply` / CPOR case-apply + `resolution-plan/*-async` |
| S11 | Progress | REQUIRED | Fire-and-poll progress with phase/pct shape (`dsi-progress` contract); phase descriptions; background-task (bell) registration; terminal + failed states rendered | `ImportJobValidateProgressPanel` + `dsi-progress` / CPOR `resolution-plan-task` poll |
| S12 | Pagination | CONDITIONAL | Server pagination when candidate volume can exceed ~500; client-side acceptable below with a written volume rationale in the unit prompt | `StewardCandidatesPagination` + `useDsiCandidatesPage` / `useCporCandidatesPage` / shipment page hooks |
| S13 | Error surfaces | REQUIRED | Action feedback alert w/ dismiss; partial-success summaries after bulk/plan apply; load-error alert distinct from empty state | Section feedback + `planApplySummary` pattern |
| S14 | Domain invariants | REQUIRED | Never auto-create dims; FLAG ≠ BLOCK; ambiguous stays reviewable; stable IDs (real IDs, not string-hash row keys) | project rules + this contract; CPOR `import_cpor_historical_token_surrogate` |

### Apply-all placement (D-016)

Canonical placement for apply-all-ready is the **plan toolbar**
(`StewardResolutionPlanToolbar` `onApplyAllReady`) for DSI, shipment, and CPOR.
Workspace toolbar keeps **Apply selected ready** only. (Supersedes dual-placement
provisional D-005.)

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
6. **Engine genericity:** `useStewardResolutionPlan` core must not reference
   region/channel/geo or assume bulk preview. Geo is composed by the consumer (DSI).
   Do not add `bulkStrategy` / capability flags that fossilize S8 gaps in the core.

## Known gaps (v1.5)

- **`/admin/cst-steward`:** key-account / report-slot / article-alias **ops** page —
  **outside** this contract (D-018). Not an import-resolution surface.
- **Waivers (shipment, D-012):** plan toolbar omits DSI global-suspicious checkbox;
  plan apply does not use plan-level suspicious confirm (variance, not gap).
- **inboundEvidence\* entity-type leakage:** `inboundEvidenceMappingCandidateDisplayUtils`
  retains API literals `shipment_distributor` / `shipment_customer_token` inside
  `features/import-steward/` (cannot rename without endpoint change). Follow-up debt —
  isolate or alias without changing wire values.
- **Remaining `Dsi*` domain modules** still under `features/import-steward/` (geo panels,
  product export, candidates page, cache updates, display helpers) — relocate follow-up
  (Unit F). Deprecated `DsiResolutionPlanToolbar` retained for advanced accordion only.

## Consolidation arc

- **Unit A** — engine extracted; DSI consumer #1 (PASS `ead4e9f`)
- **Unit B** — engine genericity via composition; shipment consumer #2
- **Unit B2** — shipment bulk preview + toolbar parity (PASS `f9c49f9`)
- **Unit C** — CPOR S9 plan + S12 pagination + S14 surrogate + S6/S4 payload (PASS `4a63a30`)
- **Unit D** — shared drawer evidence + suggestion cards; apply-all normalize (PASS `cc0138a`)
- **Unit E1** — CST import steward (suggestions + resolve + UI on Import Centre); VERIFY deferred (no-Opus)
- **Unit E2** — CST resolution-plan + async (shipped 2026-07-27; VERIFY deferred)
- **Unit F / follow-up debt** — relocate remaining `Dsi*` domain modules out of
  `features/import-steward/`; clear inboundEvidence entity-type string leakage
