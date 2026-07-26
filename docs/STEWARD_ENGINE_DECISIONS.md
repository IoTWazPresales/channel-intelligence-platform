# Steward Engine — Decisions Log

**Append-only.** Never rewrite or delete entries; supersede with a new dated entry
that references the old one. CONSULT **must** read this file before scoping any
steward/import unit. A proposal that contradicts a locked decision without citing
and superseding it is a defective prompt — bounce it.

Companion docs: `docs/STEWARD_EXPERIENCE_CONTRACT.md` (what done means),
this file (why it's built the way it is).

---

## D-001 · 2026-07-23 · Composition over capability flags
**Locked.** Domain-specific behavior is layered onto the engine core by
composition (a consumer-owned hook/slot wrapping the core), never by a
`capabilities` flag or branch inside the engine body.
**Origin:** DSI geo (region/channel catalogs, unresolved-geo, `refreshPlanEffective`,
`planGlobalSuspicious`, `partner_tier`) was baked into `useStewardResolutionPlan`.
Lifted into DSI composition in Unit B.
**Rejected:** `capabilities: { geo: boolean }` branching in core.

## D-002 · 2026-07-23 · Never fossilize a capability gap as an engine mode
**Locked.** When a consumer lacks a capability the engine requires, the consumer
keeps its local implementation and the gap is waived + scheduled. The engine does
**not** gain a mode to accommodate it.
**Origin:** Shipment bulk has no preview step (S8, PREVIEW-ABSENT, discovery-quoted).
**Rejected:** `bulkStrategy: 'direct' | 'preview'` on the bulk engine — would have
made "bulk writes with no preview" a permanently supported option for every future
importer and made S8 unenforceable.
**Test to apply:** is the divergence *domain variance* (consumer legitimately has no
such concept) or a *capability gap* (consumer should have it and doesn't)? Variance
→ compose. Gap → hold local, waive, schedule.

## D-003 · 2026-07-23 · Single canonical signature on core entry points
**Locked.** `applyResolutionPlan.mutate(candidateIds: number[])` — one shape.
Consumers adapt at their wrapper (`buildApplyBody`, section call sites).
**Rejected:** core accepting both `number[]` and `{ candidateIds, overrides }`.
Dual-shape entry points are where divergent behavior breeds.

## D-004 · 2026-07-23 · Ready predicate is core-minimal, gates compose
**Locked.** Core ready filter = `ready === true`. DSI's `duplicate_review_required`
gate composes on top as `dsiPlanRowIsReady`.
**Evidence required before this was allowed:** shipment plan services emit no
`duplicate_review_required` (zero hits in `shipment_resolution_plan.py`) — so this is
D-002 *variance*, not a shipment safety gap. **Any future consumer-specific gate must
prove the same** before composing it away.

## D-005 · 2026-07-23 · Apply-all has two valid placements (unresolved)
**Provisional.** DSI renders apply-all in the section workspace toolbar; shipment
renders it in the plan toolbar via optional `onApplyAllReady`. Both preserved in
Unit B for zero behavior change.
**Open:** normalize in Unit D. Unit C must pick one deliberately for CPOR and record
the choice here — do not coin-flip.

## D-006 · 2026-07-23 · Prefixed *modules* prohibited; API vocabulary is not
**Locked.** No importer-prefixed files (`Dsi*`, `Shipment*`, `Cpor*`) in
`features/import-steward/`. Importer code lives in its route folder.
**Clarified (C1):** `entity_type` string literals like `shipment_distributor` and
DSI corroboration markers are **API contract vocabulary**, not prefixed modules —
they may appear in shared code. Grep the module/export surface, not the substring.
**Tracked debt:** remaining `Dsi*` domain modules in `features/import-steward/`
(geo, product export, candidates page, cache updates, display helpers);
`inboundEvidence*` hardcoding shipment entity types. Sweep = Unit F.

## D-007 · 2026-07-23 · Baseline harness rules
**Locked.**
- Before/after must run an **identical, explicitly listed file set**. Different
  selections are not a no-regression proof (Unit B report claimed 19+93 → 84;
  rejected at VERIFY; re-run locked 17 files → 113 passed / 6 skipped both sides).
- `tsc` is compared as a **full error list before vs after**, not "clean on
  touchpaths." Unit A's only real defect was a tsc-only type-export error that all
  190 vitest tests passed over.
- Known pre-existing failures are recorded and excluded by name — never used as
  cover for a new one.

## D-008 · 2026-07-23 · Genericity requires a second consumer
**Locked.** An extraction with one consumer proves *relocation*, not genericity.
Unit A passed VERIFY with a DSI-shaped core because nothing could reveal it. Any
future "we made X generic" claim is graded PARTIAL until a second consumer binds it.

## D-009 · 2026-07-23 · Process scales with blast radius
**Locked.** Units touching working code (bind/migrate/refactor) get the full
discovery gate + dual baselines. Units on surfaces with no established behavior
(e.g. CST steward, currently a bare grid) get a light prompt: discovery →
implement, contract rows as done-state, no design-confirmation gate.
**Not negotiable regardless of weight:** contract-row scoping, waiver lines in
Warren's words, VERIFY against contract rows.

## D-010 · 2026-07-23 · Units are not deferrable; sessions are
**Locked.** Completion of an agreed unit is non-negotiable — no dropping contract
rows to make a unit smaller under schedule pressure (attempted and rejected for
Unit B2). **Session** boundaries between units are pure re-context tax and should be
collapsed: chain units inside one Cursor session, each keeping its own discovery,
baseline, commit, and CURRENT update.
