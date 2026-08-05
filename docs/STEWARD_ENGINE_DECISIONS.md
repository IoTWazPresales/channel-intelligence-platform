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

## D-011 · 2026-07-26 · Provisional display_names via getBulkBodyExtras
**Locked.** Per-candidate provisional customer `display_names` are supplied by the
consumer through optional `getBulkBodyExtras(action)` merged into `buildBulkBody()` —
not an engine mode or shipment-specific branch inside `useStewardBulkSteward`.
Shipment keeps `bulkProvNamesById` local and gates ready state via optional
`validateBulkForm`. DSI unchanged (shared geo/tier fields remain in the hook body).

## D-012 · 2026-07-26 · Shipment waives plan-level global-suspicious toolbar
**Locked (variance).** Shipment resolution plan apply bypasses
`confirm_for_suspicious_distributor_token` at plan level; there is no plan payload
field for global suspicious confirm. Do **not** render the DSI global-suspicious
checkbox on shipment plan toolbar — single-row create retains its own confirm.
Shipment toolbar options menu: **Update plan after edits** only (effective refresh).

## D-013 · 2026-07-27 · CPOR gets a real resolution plan; plan-apply ≠ case-apply
**Locked.** CPOR historical builds the S9 resolution-plan engine (compute-async →
preview → apply-all-ready → apply-async) by mirroring shipment — **no S9 waiver**.
Plan apply is a **new, separately-named** operation:
`imports.cpor_historical_resolution_plan_compute` /
`imports.cpor_historical_resolution_plan_apply`. Distinct from
`imports.cpor_historical_apply` (whole *cases* → production). Plan-apply is
**per-token → its own suggested target** (never bulk single-target map — that stays
"Map selected to…"). Ledger kind `"steward"`; own slot
`SLOT_CPOR_RESOLUTION_PLAN` / `cpor_resolution_plan_task` — **never `SLOT_MAIN`**
(owned by validate/case-apply).
**Rejected:** reusing case-apply for plan apply; sharing SLOT_MAIN.

## D-014 · 2026-07-27 · Persisted reversible token surrogate is S14/S9/S12 identity
**Locked.** Table `import_cpor_historical_token_surrogate`
(`id BIGSERIAL PK`, `UNIQUE (import_job_id, entity, token)`, FK CASCADE). Get-or-create
on candidate list; that `id` is the row key, plan `candidate_ids`, and page key.
**Rejected:** client `cporTokenRowId` string-hash; teaching the engine string keys
(D-002/D-003); `min(staging_line_id)` (cross-entity collision).

## D-015 · 2026-07-27 · CPOR renders apply-all in the plan toolbar
**Locked (resolves D-005 for CPOR).** CPOR uses `StewardResolutionPlanToolbar`
`onApplyAllReady` — same placement as shipment. DSI workspace-toolbar placement
unchanged until Unit D normalizes globally.

## D-016 · 2026-07-27 · Apply-all normalizes to the plan toolbar (resolves D-005)
**Locked.** Canonical placement for apply-all-ready is `StewardResolutionPlanToolbar`
`onApplyAllReady` (shipment/CPOR placement; D-015). DSI converges: wire
`onApplyAllReady`/`applyAll*` into its existing shared-toolbar mount and remove the
workspace-toolbar apply-all button; **"Apply selected ready" stays in the workspace
toolbar**. Supersedes the "two valid placements" clause of D-005. Opportunistically
retire deprecated `DsiResolutionPlanToolbar` by inlining its call site.
**Origin:** Unit D CONSULT READY 2026-07-27.

## D-017 · 2026-07-27 · S6/S7 drawer UI is shared by extraction, not per-consumer
**Locked.** `StewardEvidenceSummary` (S6: samples, affected rows, units, value, +
neutral `extras` ReactNode slot) and `StewardSuggestionCards` (S7: 1..N ranked cards
`{label, band, score, reason, targetId, onMap}` + override-search slot) live in
`features/import-steward/` with **no importer prefix and no importer-typed imports**
(D-006). Consumers pass neutral data + callbacks. Second consumer proves genericity
(D-008): evidence summary = shipment + CPOR; cards = CPOR + shipment.
**Origin:** Unit D CONSULT READY 2026-07-27.

## D-018 · 2026-07-27 · Unit E is CST import resolution (not /admin/cst-steward ops)
**Locked.** Unit E brings **customer_sell_through** import token steward
(`cst_product_token` / `cst_location_token` on `ImportEntityMappingCandidate`) onto
the shared engine on Import Centre. `/admin/cst-steward` (key accounts, report
slots, article aliases) is **outside** the import-steward contract (ops/master
config — not per-job token→dim resolution). Article-alias curation is out of Unit E.
**E1 (this pass):** suggestion enrich + resolve/ignore + steward UI. **E2 (shipped 2026-07-27):**
resolution-plan compute/apply-async + own steward slot (D-019, mirror D-013).
**Origin:** Unit E CONSULT NEED_HUMAN + Warren no-Opus execute authorization 2026-07-27.

## D-019 · 2026-07-27 · CST gets a real resolution plan; own steward slot
**Locked (mirror D-013).** CST import steward (`customer_sell_through`) uses
`SLOT_CST_RESOLUTION_PLAN` (never SLOT_MAIN) for resolution-plan compute/apply-async.
Ready rule: open status, exactly one suggestion with score ≥ 0.90; collisions not ready.
Plan apply maps per-candidate → its own suggested target via `resolve_cst_candidate_sync`.
**Origin:** Unit E2 BACKLOG-074 TRIGGER (Warren prioritized, VERIFY waived) 2026-07-27.

## D-020 · 2026-07-28 · Audit branch content, never branch labels
**Locked.** Before proposing a merge, cherry-pick, or kill on any branch, diff its
actual content against `main`. Branch names describe intent at creation time and
age badly — work named in a branch may already have shipped by another route.
**Origin:** `feat/ops-master-grid-shell-parity` was assessed as unshipped
`MasterDataGridShell` work. In fact the shell shipped for masters
(`admin/customers`, `admin/products`, `admin/distributors`) in BACKLOG-061 Theme B
(U-G2 → U-B2 → U-B3b), PR #7, merged 2026-07-10. The branch only extends the shell
to *ops lists*. Warren caught the error; the recommendation had been built from the
branch name plus a discovery line that was read past.
**Applies to:** any branch-hygiene pass, and to the base-integrity check in
`scripts/verify-gate`.
**Note:** Renumbered from colliding D-013 (2026-07-28) → D-020 so 2026-07-27
D-013–D-019 (CPOR/CST) stay authoritative under their original IDs.

## D-021 · 2026-07-28 · Kill `feat/ops-master-grid-shell-parity`
**Locked.** Delete the branch (local + remote) rather than reconcile it.
**Reasoning:** Tip was `d789ad9` (~36 ahead / ~66 behind `main` at kill time); base
`618448c`. `main` advanced through Unit F (path moves), shipping commercial KPI
rebuild, and steward A–F — conflict cost exceeds recoverable value.
**Diff findings (content audit, not labels — D-020):**
- **Extract (non-trivial):** `customer_merge_alias_seal`; CST article-alias batch
  confirm/reject (`bf2afd4`); customer merge companions
  (`customer_merge_redirect.py`, `customer_related_master_groups.py`, RelatedName UI,
  repair/backfill scripts) — merge-engine adjacent, clone-proven E2E required.
- **Extract (mechanical / fold-in):** Ops-list `MasterDataGridShell` parity (CPOR
  cases, PM gaps, shipment evidence, PVE); ops-list pagination chrome; shared
  helpers `useDebouncedUrlQuery` + `skipLimitSearchParams`. Fold into whichever
  phase touches those pages — **do not schedule standalone**.
- **Do not extract / do not resurrect:** Channel-ops KPI cards (Waves 1–3) and
  `shippingUtcDates.ts` (+ tests) — **superseded by `main`'s commercial KPI
  rebuild**. Re-applying ops-master shipping/ops KPI chrome would overwrite newer
  correct contracts.
**BACKLOG targets:** 079–081, 083–085 (plus 082 from D-022 stash extract).
**Rejected:** merging. **Do not take:** `fix/web-grid-community-stabilization`
(forces community AG Grid; conflicts with Enterprise pattern).
**Note:** Renumbered from colliding D-014 (2026-07-28) → D-021.

## D-022 · 2026-07-28 · Header vocabulary is template config, never code constants
**Locked.** Accepted spellings for a canonical import field, and the never-auto-map
denylist, are **per-template configuration**. No tenant or vendor header string is a
literal in Python.
**Debt being retired:** `dsi_mapping_workflow.py` hardcodes `"dealer name group"`,
`"customer name"`, `"dealer_name_group"` in `_looks_like_dealer_name_group_column`,
`_looks_like_raw_source_customer_name_column`, and
`apply_exact_raw_customer_header_overrides`. Adding ASUS's `Dealer Name` plus a
`Dealer Code` / `Dealer Name 1` denylist on top would compound it.
**Rejected:** landing stash `park-dsi-asus-dealer-name-automap` as written. Its
domain knowledge (ASUS header spellings, denylist names) is extracted into the
template seed; the implementation is dropped.
**Precedence fix, same unit:** confirmed steward memory > template alias > heuristic.
`apply_exact_raw_customer_header_overrides` currently forces its mapping
*"regardless of learned memory"* — a heuristic overriding a confirmed human decision,
which is backwards.
**Safety note:** the denylist is the high-value half. A mis-mapped identity column
sets the wrong customer resolution identity, and per the docstring on
`dsi_customer_alias_normalized_token`, an alias stored under one token while the
resolver looks up another leaves rows `customer_unresolved` permanently while the
candidate reads `resolved`. Silent and persistent.
**Note:** Renumbered from colliding D-015 (2026-07-28) → D-022.

## D-023 · 2026-08-01 · One concept, one owning surface
**Locked.** Every metric, filter and lifecycle state has exactly one owning surface
(`docs/COMMERCIAL_SEMANTICS.md`). Other surfaces read or link; they never re-implement.
**Origin:** ROADMAP v3 stated POD completeness was "A1 core scope". A1 is the
Plan-vs-Executed screen, so POD-completeness tiles and a `landing` scorecard block
were built onto Plan-vs-Executed — duplicating Shipping, which already owns
shipped/pipeline/landed/POD ageing. Warren caught it; the PvE wiring was reverted.
**Root cause:** the roadmap named the metric but never named the owner. "Matters to
phase X" collapsed into "renders on phase X's screen."
**Rule:** a metric mattering to a phase means that phase may *consume* it. Ownership
is declared separately and explicitly.

## D-024 · 2026-08-01 · AMBER halts at design for new commercial semantics
**Locked.** New metrics, lifecycle states, or tiles/filters on user-facing surfaces
halt **before any code** — reporting concept, owning surface, pre-build
existence-audit output, and justification if proposing a new home. Data-load sign-off
and first-use-of-a-new-file-family remain post-build halts.
**Reasoning:** a post-build halt cannot catch building the wrong thing correctly. The
POD work passed its unit tests and rendered fine; it was simply on the wrong screen.
**Companion gate:** pre-build existence audit (grep `apps/web/src` +
`apps/api/app/services`) is mandatory and its output is printed in the unit report.

## D-025 · 2026-08-01 · Metrics live in COMMERCIAL_SEMANTICS or are not built
**Locked.** Metric definitions (formula, grain, source facts, owning surface) are
authoritative in `docs/COMMERCIAL_SEMANTICS.md`. If a metric is absent from that file, agents
do **not** invent or ship it. WoC grain is **distributor × product only** — matching
customer-grain velocity to distributor-grain stock is a **correctness error**, not a
preference. Cost per incremental unit is **DO NOT BUILD** until a validated baseline model
exists (BACKLOG-089). “Deal-stock landing” is renamed **over-plan intake** (overship vs plan,
not POD). Execution process (zones, dual-agent) lives in `docs/AUTONOMOUS_BUILD_CHARTER.md`
v1.2; former `WORKFLOW_DUAL_AGENT.md` is a stub.
**Origin:** governing-doc sprawl + contradictory ownership/taxonomy/roadmap claims after the
PvE POD misfire.

## D-026 · 2026-08-01 · DB writes follow autonomy zones (not a blanket ban)
**Locked.** The charter’s **Autonomy zones** are the single rule for `cip` writes.
**Supersedes** the dual-agent standing line “no cip writes without Warren” (blanket).
**Rationale:** Import loads and steward resolution applies are **idempotent / reversible by
deleting the job** — they run unattended under GREEN/AMBER as already stated in zones.
**Still require clone-proof + halt:** customer/distributor merges, supersessions, destructive
bulk applies (physically irreversible pointer rewrites). **Still require Warren’s explicit
approval:** Alembic migrations against `cip`, and any schema change (STOP and report).
**Do not** reintroduce a second contradicting blanket ban in skills or overlays.

## D-027 · 2026-08-01 · CPOR claim rate is non-computable (no distinct owed amount)
**Locked.** Do not ship a “claim rate” KPI alongside delivery rate. Settlement / claim evidence
captures **units**, then recomputes `ttl_result = support_unit × result_qty` with approval
`support_unit` — no independent **owed** amount. Former A2-03 lives in
`COMMERCIAL_SEMANTICS` **non-computable register**. **TRIGGER:** settlement stores **owed** ≠
computed support. **Not “paid”:** paid would require reconciling distributor payments
(Ken / admin) — separate from claim rate / settlement owed. **Currency for A2:** USD aggregate;
ZAR display summed per-case FX (never one period rate on a USD total).
**Correction 2026-08-01:** wording was briefly “paid”; Warren clarified owed vs paid.

## D-028 · 2026-08-03 · 1H commercial parse: month-derived split only (no uniform_half)
**Locked.** When a commercial lineup 1H workbook **has** month phasing columns, Q1/Q2
case quantities are derived from real monthly values (fiscal Q1 = months 1–3, Q2 = 4–6;
`month_split_json` written in historical shape `{header: float}`). When a 1H workbook
has **no** month columns, the parse **refuses** the split, surfaces
`half_year_split_requires_month_columns` via job `warnings` + `staged_metadata.attention_reasons`
/ `needs_attention` (existing mechanism), and does **not** fabricate quantities.
**`allocation=uniform_half` / `allocate_uniform_half` are retired from the commercial
parse path** (`lineup_case_parser`); `apply_half_year_allocation_to_row_dict` remains
hardened (safe coerce, no bare `float` on promo labels) but is unreachable from parse.
**Origin:** STATE_AUDIT §6 Q2–Q4; Warren settled decision 2026-08-03.
**Rejected:** falling back to ceil/floor(Qty/2) when months are absent.

## D-029 · 2026-08-03 · period_signal_conflict is a steward call (do not hand-set)
**Locked.** When layered period inference surfaces `period_signal_conflict` (folder /
title_band / filename quarters disagree), the proposal stays `needs_attention`. Agents
must **not** hand-set `period_label` / `inferred_period_start` to “fix” the corpus.
**Proven example:** `f3:NB:NB:unknown` — folder `NB/2025/Q4` → 2025 Q4, filename → 2025 Q4,
title band `2025 Q3 NEW PLAN` → 2025 Q3; conflict is by design (`resolve_layered_period`).
**Warren decides** which signal wins (folder/filename Q4 vs stale title Q3) before apply.
**Rejected:** silently preferring folder tier over title when quarters conflict.

## D-030 · 2026-08-03 · Lineup file numeric prefix = revision preference
**Locked.** PMs file newer quarter lineups alongside older ones with an incremented
leading numeric prefix (`1. X.xlsx`, `2. X.xlsx`). After stripping the leading `N. `
prefix, when two competing cases share an **identical base name**, the **same period**,
and the **same customer** (on the competing PO proposal), the **higher prefix wins**.
The lower-prefix case is **soft-superseded** via existing fields
(`commercial_status='superseded'`, `superseded_by_case_id=<winner>`). Active filters
(`active_lineup_case_filters`) exclude losers from planned_units and auto-link.
**Does not apply** when base names differ — those remain genuine steward conflicts.
**Does not touch** survivors 7/9/90 without explicit Warren override (version rule may
match but survivor hard-constraint wins).
**Origin:** Warren settled decision 2026-08-03 clearing the 211 auto-link queue.
**Rejected:** inventing a new supersession table/status; hard-delete of loser cases.

## D-031 · 2026-08-04 · D-030 may supersede po_issued; PO links MUST carry (blocker)
**Locked intent (Warren 2026-08-04):** D-030 applies to `po_issued` cases. Explicit
authorisation: case **122** (`2. ACZA Q2 2026 Consumer Lineup - Sales.xlsx`) supersedes
case **9** (`1. …` same base, NB 2026 Q2). Case 9 is exempt from survivor protection for
that supersession only; cases **7** and **90** remain fully protected.
**PO-link carry is mandatory:** on supersession, `commercial_lineup_case_po` rows belonging
to the loser must be preserved on the winner — not dropped, orphaned, or left only on the
superseded case (active consumers use `active_lineup_case_filters` and would lose the links).
**Engine gap (STOP):** bulk/apply supersession today only sets
`superseded_by_case_id` + `commercial_status='superseded'`
(`lineup_bulk_backfill_apply.py` ~377–382). It does **not** carry, move, or copy
`commercial_lineup_case_po` rows. No dedicated carry service exists. Unit stopped before
applying 9→122. **Do not** hand-write link rows to simulate carry.
**f3 path exists** (manual tier): `resolve_layered_period(..., manual_period_label=...)`
via steward period override; session 752 still has `f3:NB:NB:unknown` /
`period_signal_conflict` — applicable once carry + apply resume.
**Origin:** Warren D1/D2 2026-08-04; Cursor discovery STOP A2.
**Rejected:** superseding po_issued without carry; inventing ad-hoc SQL inserts as “carry”.

## D-032 · 2026-08-04 · PO-link carry on supersession is COPY (not move)
**Locked.** Soft-supersession of a lineup case **copies** `commercial_lineup_case_po`
rows from loser → winner via `soft_supersede_lineup_case` /
`carry_case_po_links_on_supersession` (`lineup_case_supersession.py`).
- Loser rows are **preserved** (historical record) — never deleted, moved, or
  repointed.
- Idempotent on unique `(case_id, purchase_order_id)`; skip-existing when the
  winner already holds a PO.
- All-or-nothing with the status change in the same DB transaction (caller commits).
- Insert path reuses `insert_case_po_link_if_missing` (same semantics as
  `link_case_to_existing_po`). Provenance on winner `notes`:
  `supersession_carry:from_case=<loser_id>` (existing Text column — no schema change).
- Wired into bulk backfill existing-case supersede
  (`lineup_bulk_backfill_apply.py`). New superseded shells (born empty) need no carry.
**Proven:** clone `cip_po_carry_smoke` C2–C6; cip 9→122 carried 28/28 (set-diff empty);
NB 2026 Q2 planned 68881→46830. Cases 7/90 untouched.
**Origin:** BACKLOG-118; Warren W1 2026-08-04; closes D-031 engine gap.
**Rejected:** move/repoint loser links; hand-written SQL inserts; provenance column migration.

## D-033 · 2026-08-05 · Contested PO requires shipment evidence that fails to explain claims
**Locked.** Multiple BUs may legitimately share one PO (domain truth). Competition /
contested classification consults ``fact_inbound_shipment`` + ``dim_product.product_line``
(never ``business_unit`` / CONSUMER).
- **not_contested** ``po_multi_bu_shared``: shipment shows ≥2 BUs and each claiming case
  overlaps shipped products in its own BU.
- **contested** ``po_competes_same_bu_same_period`` / ``po_competes_cross_period``.
- **indeterminate** ``po_compete_indeterminate_no_shipment``: stays visible; never
  silently cleared; never hard-blocks.
- FLAG ≠ BLOCK: ``competition.blocks_apply`` is always false; apply/link ignores it.
- Shared function: ``classify_po_competition`` / ``classify_proposals_competition``
  in ``lineup_po_competition.py``; wired into ``po_auto_link_proposals`` (preload only —
  no per-row queries in the classify loop).
**Live on cip after 9→122:** multi-case norms 35 → contested **13** / multi_bu_shared **22**
/ indeterminate **0**. Match key unchanged. No acceptances in the detector unit.
**Origin:** BACKLOG-119; Warren 2026-08-05.
**Rejected:** BU from ``business_unit``; treating multi-BU share as conflict; gating apply
on contested; trusting stale warren-queue JSON.

## D-034 · 2026-08-05 · Slice identity comes from the apply parser (never cross-parser align)
**Locked.** Bulk-backfill BU split emits each slice's `source_row_number` list from
`_parse_file_to_row_dicts` / parser #2 rows (the parser apply re-runs), by running BU
resolution over *those* rows. `parse_historical_workbook` (parser #1) remains the source
for sheet selection / period / title-band / schema, but **never** for per-row slice
identity. Cross-parser `row_match_key` alignment (`map_slice_rows_to_source_row_numbers`)
is retired from the identity path — keeping a tolerant/fuzzy match mode is prohibited
(D-002). Unclassifiable rows → `needs_attention` with `slice_row_unclassified_bu`, never
a silent mis-slice. Workbook sheets whose content is a subset of a sibling sheet
(e.g. `Sheet1` ⊆ `NR`) are **excluded** (`sheet_content_subset_ignored`) so apply does
not double-count — Warren Unit3 2026-08-05.
**Proven:** NR 2026 Q3 Gaming workbook — open-channel customer nulling made aligner fail
(49 unmatched); D-034 preview `f0:NR:NR:2026 Q3` ready **120** / NB **6** / Sheet1
excluded; clone `cip_unit3_smoke` + cip case **146** = **120** lines; case **130**
(Sheet1, 14 lines) soft-superseded → 146; protected 7/90/122/145 unchanged.
**Origin:** BACKLOG-108; PROGRAM-A Unit 3 CONSULT 2026-08-05; Warren answers (bar=~120,
ignore Sheet1).
**Rejected:** loosening `row_match_key` / `strict=False`; unifying both parsers in this
unit; hand-inserting the 126 sheet rows; treating sheet-row count as case-line count.

**Correction 2026-08-05 (PROGRAM-A §0):** Evidence pack implication that sheet `NR` =
Amazon-only and `Sheet1` = Computer Mania-only was **incomplete**. Live cip case **146**
(`sheet=NR`) customer_token breakdown includes Computer Mania **14**, Amazon **5**,
Evetech **20**, IC **17**, null/open-channel **49**, plus others (120 total). Case **130**
(`sheet=Sheet1`, superseded→146) is Computer Mania **14** only — those rows are present
inside 146 (Sheet1 ⊆ NR content identity from Unit 3 discovery). Supersession retained.
**New lock (Warren §0/§5):** supersession requires **same period AND same customer**;
different customer is never a revision. Subset-sheet exclusion remains correct for
Sheet1⊆NR; do not supersede across distinct majority customers without that lock.

