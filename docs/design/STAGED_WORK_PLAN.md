# Staged work plan — remaining CIP work

**Date:** 2026-09-21 · **EIF node:** N-0030 (`BACKLOG_AUDIT_20260921`) · **Branch:** `feat/ns-2-brief-nav-collapse`
**Inputs:** Warren's decisions of 2026-09-21 (below) · `docs/ROADMAP.md` · `docs/BACKLOG.md` after the N-0030 audit (`.eif/audit/BACKLOG_AUDIT_20260921/BACKLOG_AUDIT.md`) · `.eif/program/PROGRAM.yaml` (29 nodes: 22 complete, 5 rejected, N-0028/N-0029 open).
**Status:** **draft** — Warren said more may be missing and will know by Wednesday 2026-09-24. Treat Wednesday's input as a revision of this file, not a reason to hold it.

> Code is evidence; this plan is a claim. Every "measured" figure below was read from the running tree or from `cip` (read-only, `current_database()=cip` printed first) on 2026-09-21. Nothing here is complete until proven in the running tree.

---

## 0. Decisions this plan is built on (Warren, 2026-09-21)

| # | Decision | Consequence in this plan |
|---|----------|--------------------------|
| D1 | **Fresh independent GOV-008** for N-0028 and N-0029. No self-completion. | Stage 1 is review work by a distinct actor/run, one node per session. N-0029 is mechanically completable (`gates_valid=True`) but its `stage_note` says do not complete — respected. |
| D2 | **Density: 40/40 rows + 13px grid type**, not the lab's 36/36. Grid-scoped type token; unify the four duplicated height constants first. | Stage 2.1–2.3. Lands **before** N-0029's review so `grid_above_fold` is reviewed once. |
| D3 | **All columns pickable** on fact grids — searchability, analysis, intelligence. | Stage 2.4 becomes one generic "every field on the fact" picker, not curated groups. Simpler than BACKLOG-201 assumed. |
| D4 | `CporCaseWorkspace`'s five orphaned tabs **are needed** → merge onto the settlement desk. | Stage 2.7. Restores BACKLOG-093 promo-load recon, a roadmap-shipped A2 deliverable currently unreachable in production. |
| D5 | P1 sign-off: discover, then ask. | **Dissolved by discovery:** P1 exited 2026-08-01 (`ROADMAP.md:450`, `CONTEXT.md:438`; `DATA_CENSUS.md` sign-off log: Shipment yes, CPOR yes, DSI + Lineups deliberate leave-alone). Nothing to sign. |
| D6 | Build features 1–9. **Feature 10 (CST historical backfill) excluded** — Warren will source data from customers and distributors directly. | Stage 7 uplift and Stage 6 depth items are **data-gated**, not build-gated. |
| D7 | Customer/distributor **codes never in identity columns**; only as their own pickable column. | Stage 2.4 includes the name-only sweep and the `Customer code` / `Distributor code` columns. Memory rule saved. |
| D8 | External access: **R0/month**, local WSL, Cloudflare Quick Tunnel, **BLOCKED** until auth is real. | Stage 3.1 is one env var (`CIP_AUTH_MODE=session`) plus passwords Warren sets himself. |
| D9 | Use EIF for the checks it does. | Every stage below is meant to be chartered as node(s); this plan is the decomposition input (cf. BACKLOG-177). |

**Standing exclusions.** EIF-repo defects (BACKLOG-159, 166, 167, 169–177) are **out of CIP scope** by their own text ("do not fix in CIP") → one separate EIF-repo session, not in these stages. BACKLOG-193 (AG Grid Enterprise) is **dropped**: a paid licence breaks R0 and N-0029's acceptance criteria forbid it. BACKLOG-200 is **held**: N-0029's criteria say "do not unify `MasterColumnPickerDialog` and `ColumnSelectorModal`" — deleting the wrapper is that unification; needs the N-0029 review to rule.

---

## 1. Stages, in dependency order

Ordering rule: a stage sits after everything it needs to be *proven*, not merely written. Arrows name the dependency.

### Stage 0 — Ledger hygiene ✅ (this node, N-0030)
Backlog audited against the tree, stale entries stamped, this plan written, CURRENT/CONTEXT pinned. Deliverable of N-0030; **not** a build stage.

### Stage 1a — Independent GOV-008 on **N-0028** (no product dependency)
"Start work cards and Lineup cases on the lab composition." 11 gates pending — **3 required** (`quality.ux`, `quality.rendered`, `quality.content`) plus `verification.rendered`/`referent` and five optional design dims that NS21 reset because their evidence described a Panel/Pane composition that no longer ships. This is a real rendered review at 1280×800 **and 390×844** — the latter is now reachable: the browser tool catalogue has `resize_window`, so the `BROWSER_UNSAFE` CDP path (deferred finding seq 354) is no longer the only route. Distinct actor/run; do not touch product code in the same run.

### Stage 2 — Grid, desk and density parity (feature 7 + D2/D3/D4/D7)
Depends on nothing above. **Blocks Stage 1b.**

| # | Item | Depends on | Backlog / node |
|---|------|-----------|----------------|
| 2.1 | **Unify the four height numbers** now in three files (`EnterpriseDataGrid.tsx:121-122`, `gridPagination.ts:7-10`, dead emission in `packages/ui/agGridMuiTheme.ts:78-79`) into one source. No behaviour change; independently verifiable. | — | density proposal §5.2 |
| 2.2 | **Grid-scoped type token** so 13px reaches the grid and not the 721 `variant="body2"` usages. ⚠️ Option (a) edits `packages/ui/agGridMuiTheme.ts:25`, which is **outside the accepted `change_paths`** (`apps/api/**`, `apps/web/**`, `docs/**`). Either Warren amends `AUTONOMY_POLICY.md` to add `packages/ui/**`, or take option (b): set `--ag-font-size` in `EnterpriseDataGrid`'s `shellSx`. **Decision needed before 2.3.** | 2.1 | density proposal §5.1 |
| 2.3 | **Density 40/40 + 13px** (D2). Smoke a `wrapText/autoHeight` grid (settlement Corroboration column) and a paginated grid (plan-vs-executed), not only the lab. Keep `compact` at 34/36 so the toolbar toggle stays visible. | 2.1, 2.2 | `DENSITY_PROPOSAL_OPERATOR_DATA_SCALE.md` |
| 2.4 | **All-columns picker** on the ~15 Tier A fact grids (D3): one generic picker fed by the fact's field list, layout key per grid, via the existing `ColumnPickerDialog`. Includes **`Customer code` / `Distributor code` as pickable columns** and the **name-only sweep** of identity columns (D7). | — | BACKLOG-201, 140 (display half) |
| 2.5 | **SKU / sales model / both**: `LineIdentifierPreference` gains `'both'` as *two* columns (each sortable/filterable), so 2.4 and 2.5 are one mechanism. Tenant profile + ~13 consuming surfaces. | 2.4 | CURRENT line-identifier series |
| 2.6 | `MarketSurface` mappings grid → `ModuleDataSection` (the one open MIGRATE). | — | BACKLOG-199 |
| 2.7 | **Five orphaned CPOR tabs onto the settlement desk** (D4): USD pivot, Events, Exports, **Promo load recon**, Payments/recon. Desk now has `FundingChrome`, so they mount as lens/tabs under the case header. Then retire `CporCaseWorkspace`. | `492795c` (desk chrome) | BACKLOG-202, 093 |
| 2.8 | **Interaction honesty**, two cheap defects on programme-complete nodes: `LineupScopeBar` ships an inert primary **Apply** (`:106`, no handler); `market.py:12` reports `competitor_price_import: ready` while `fact_competitor_price` has **0 rows** and no template exists. | — | BACKLOG-156, 160, 157 |
| 2.9 | **Design-lab duplicates**: `design-lab/primitives` still carries its own `DomainHeader`, `HeadlineFigure`, `Panel`, `EntityContextPanel`, `charts`, `controls`, `CapabilityStatus`; `design-lab/shell` its own `CommandPalette`, `LabShell` (25 tsx). Production has them in `features/workbench-ui` and `features/shell`. Lab imports production or is deleted. Do this **after** 2.3 so the density lab is no longer needed. | 2.3 | BACKLOG-161, 158 |

### Stage 1b — Independent GOV-008 on **N-0029** (after Stage 2)
"Grid community clipboard in one wrapper, Case book working content first." One optional gate pending (`quality.design_signatures`), three stale signatures: `grid_above_fold` (changes with 2.3), `unmatched_case_id_link`, `payment_evidence_code_unread` (already superseded by `aee82a72`). Reviewing after Stage 2 avoids running it twice. This session's grid/desk commits (`b9a58a3`, `492795c`) are inside its scope and must be listed as evidence for the reviewer.

### Stage 3 — Access and operations (features 1 + 3; the tunnel)
Depends on nothing in Stage 2. Can run in parallel with it by a different actor.

| # | Item | Notes |
|---|------|-------|
| 3.1 | **`CIP_AUTH_MODE=session`** in `apps/api/.env` (currently **0 bytes**; effective mode measured `stub` → every unauthenticated request is `admin@local`, headers forgeable). Warren sets the two passwords (`admin@local`, `viewer@local`, both already have hashes; PBKDF2-SHA256 × 260k). Run `next build && next start` for the tunnel window, not `next dev`. | Security gate → PASS. `redirectToLoginOn401` already exists in the web client. |
| 3.2 | **RBAC**: one role-matrix CONSULT (Ken/PM/Wayne → admin/steward/planner/viewer), then `require_roles` on every CPOR write incl. export; steward panels `STEWARD+ADMIN` (today `shipment_evidence.py:203,228` are ADMIN-only); planner RBAC. | BACKLOG-136, 141, 021 |
| 3.3 | **Tenant scoping sweep**: 34 of 58 endpoint modules never reference `tenant_id`. Tolerable for one-tenant staff pilot; not for two tenants. | P2 exit |
| 3.4 | Login rate-limit / lockout (none today). | small |
| 3.5 | **Quick Tunnel** + multi-user test plan (Phase 7 of the brief). Only after 3.1. Re-test every route under `session` — some may have leaned on the stub admin. | R0 |
| 3.6 | **Operational safety net** (feature 3): job-failure alerting on Celery, error tracking, log aggregation, **automated `pg_dump` + a tested restore + RTO/RPO** (`docs/BACKUP_AND_DR.md` exists — verify it is executed, not just written). Admin data-health page. VACUUM runbook. Celery parity audit. AI resolver fail-loud **before** `AI_ASSIST_ENABLED` is ever flipped (today `False`; `_anthropic_client()` returns `None` silently). | BACKLOG-031, 032, 048, 168 |
| 3.7 | **Import-complete merged-id assertion**: `customer_leftover_repair.py` exists with **zero callers** — wire it to the import-complete rail; fold 134 (measured 0 today). | BACKLOG-133, 134 |

### Stage 4 — Data integrity and CPOR correctness (small, measured, necessary)
Independent of Stages 1–3. Several need Warren's approval because they touch `cip` or schema.

| # | Item | Measured 2026-09-21 | Needs |
|---|------|---------------------|-------|
| 4.1 | `dim_product` inverted launch/retire windows | **2,795** rows (entry recorded 319 — grown ~9×) | audit → repair on clone → Warren approves cip repair · BACKLOG-034 |
| 4.2 | `cpor_case.status` vs `workflow_status` drift | **4** rows: settled/ended ×2, cancelled/draft, cancelled/ended | pick owner column, repair · BACKLOG-139 |
| 4.3 | Customer SOH for the MAC check | `fact_inventory_customer` **0** rows; `fact_customer_sellthrough` **1,823** | point MAC-check at CST; stop claiming the inventory fact · BACKLOG-135 |
| 4.4 | `cpor_case_line` week-aligned windows | **no** `window_*` columns on the line | migration — Warren approval · BACKLOG-137 |
| 4.5 | **CIP-minted customer codes** on promote (the other half of D7) | `dim_customer.code`; TMP count in audit | settings + collision-safe sequence; `mode=mint` on existing promote · BACKLOG-140 |
| 4.6 | Open→shipped fact double-count policy | diagnostic exists (`shipment_plan_d_cutover.py`) | Warren approves remediation policy · BACKLOG-062 |
| 4.7 | ACZA workbook non-operational sheets (BOM Not Ready) | no allowlist in `_load_frames_for_job` | business rule then allowlist · BACKLOG-046 |
| 4.8 | Customer merge **alias seal** + companions | not in tree; consult READY (memory) | merge-engine wave · BACKLOG-081, 083 |

### Stage 5 — Analytics delivery (feature 2)
P3-5: Excel/PDF export, event-triggered refresh (load completes → dependents refresh → subscribers notified) **and** calendar delivery; every report declares its vintage on its face. Depends on Stage 3.6 (a scheduler that can alert on failure) — do not ship scheduled delivery with no failure signal.

### Stage 6 — Planning journey (features 4 + 9)
| # | Item | Backlog |
|---|------|---------|
| 6.1 | **B2 end-to-end PM run** — a PM authors next quarter's lineup in CIP and exports tenant format (demo gate #4, "the dependency moment"). Components exist; the journey is unproven. | roadmap B2 |
| 6.2 | Lineup **authoring workbench** beside unified import (feature 9). | BACKLOG-190 |
| 6.3 | Unified lineup import **1H → Q1+Q2 fan-out** (bulk path has it; unified path status in audit). | BACKLOG-103 |
| 6.4 | Bulk-backfill completion UX (dialog still `onClose()` at `:269`; activity-bell pointer only). | BACKLOG-060 |
| 6.5 | Lineup data rules: PF `Qty` vs `Total Qty`, BU resolver thresholds, monthly-phased 1H. | BACKLOG-105, 055, 065 |

### Stage 7 — Promotion intelligence v2 (feature 8) — partly **data-gated**
| # | Item | Gate |
|---|------|------|
| 7.1 | Listing + competitor evidence on plan lines — buildable now with honest empties (`customer_listing` 218, `listing_observation` 168, `fact_competitor_price` **0**). | BACKLOG-183 |
| 7.2 | Observed weeks-of-cover as proposal input (`weeks_of_cover_observation` 194k rows; `target_cover_weeks` all null). | BACKLOG-184 |
| 7.3 | A2-05 comparable ranking scope decision. | BACKLOG-186 |
| 7.4 | **Uplift from settled claims** — `cpor_claim_evidence_line` **0** rows against **211** settled cases. Cannot be built honestly until claim evidence lands. **Unlocked by Warren's customer/distributor data drive (D6), not by code.** | BACKLOG-185 |
| 7.5 | Supply: stored "Arrived" state (facts today only `shipped` 13,477 / `open_order` 1,775); plan-unit PO coverage by distributor. | BACKLOG-178, 179 |

### Stage 8 — Steward and import engine (helpful; trigger-gated)
DSI mailbox auto-ingest (shipping slice **is in tree** under `services/mailbox_ingest/`; DSI batch-propose slice open) · layout-coalesce follow-ons · **CST article-alias batch confirm/reject** (P4 is live, so the trigger has effectively fired) · unresolved-volume worklist reader (`apply_exclusion` writer exists) · post-apply reconciliation report · catalogue semantic column mapping · backfill file-provenance retention · PoAutoLink S1–S14 parity · ResolutionWorklist migration · DSI replay after catalogue-gap apply · non-candidate steward coverage · wizard componentisation · DSI post-tier orchestrator · catalog bulk upsert (still per-row `flush()` at `pm_commit_catalog.py:72,294`) · geo indexes · candidates payload slimming.
BACKLOG-077, 078, 080, 049, 051, 059, 067, 106, 123, 187, 188, 004, 037, 011, 018, 006, 008, 016, 019, 020.

### Stage 9 — Distributor merge (feature 6)
Customer-merge engine extended to `dim_distributor`; pairs with 4.8 and the ResolutionWorklist migration (BACKLOG-123 names the distributor auto-link grid as the second consumer).

### Stage 10 — Multi-tenant productisation (feature 5, P6)
Tenant config surface (BU vocabulary, period conventions, legal-form normaliser, column-map profiles, metric definitions, export templates), tenant-#2 onboarding, branding, provisioning. Pulls in BACKLOG-059, 067 and the **`catalog_product` grain decision** (BACKLOG-198 — Warren's).

---

## 2. The same work, grouped by the kind of work it is

| Kind | Items |
|------|-------|
| **Config / env only** (minutes) | 3.1 `CIP_AUTH_MODE=session`; `next build && next start` |
| **One-line honesty fixes** | 2.8 `market.py:12`; 2.8 `LineupScopeBar` Apply; 2.6 mappings grid MDS |
| **UI parity (web only)** | 2.1, 2.3, 2.4, 2.5, 2.7, 2.9, 6.4 |
| **Needs a policy or licence decision** | 2.2 (`packages/ui` outside `change_paths`); 193 dropped (licence) |
| **API + schema (migration, Warren approves)** | 4.4 line windows; 4.5 code mint sequence; 7.5 Arrived state; 2.5 tenant profile field |
| **Data repair on `cip` (clone first, Warren approves)** | 4.1 (2,795 rows), 4.2 (4 rows), 4.6 |
| **Security / RBAC** | 3.1–3.5 |
| **Infrastructure / ops** | 3.6, 3.7, 5 |
| **Journey proof (browser, not code)** | 6.1 B2 PM run; 3.5 multi-user test |
| **Data-gated (Warren's data drive)** | 7.4 uplift; P5 observation depth |
| **Governance (distinct actor)** | 1a N-0028; 1b N-0029 |
| **Out of CIP scope** | EIF repo: 159, 166, 167, 169–177; `.cursor/hooks` |
| **Dropped / superseded** | 193; 149–154 (six-container IA superseded by N-0013); 009/010 PIM → fold into Stage 10 or drop; 017; 014 unless business asks |

---

## 3. Decisions still needed from Warren

1. **2.2** — add `packages/ui/**` to `change_paths`, or accept option (b) (`--ag-font-size` in `EnterpriseDataGrid.shellSx`)?
2. **4.1** — approve repair of the 2,795 inverted `dim_product` windows on cip after a clone run?
3. **4.4** — approve the `cpor_case_line` window-column migration?
4. **3.2** — the role matrix: Ken / PM / Wayne onto admin / steward / planner / viewer, or new roles?
5. **BACKLOG-198** — does `catalog_product` stay the catalogue, get retired, or is it unrelated to per-line column sets?
6. **3.5** — go for the tunnel once 3.1 and passwords are done?
7. **2.9** — delete design-lab duplicates outright, or keep lab as a fixture skin over production components?

## 4. Sequencing at a glance

```
Stage 0 ─┐
         ├─► Stage 1a (N-0028 review)            ── distinct actor
         ├─► Stage 2 (grid/desk/density) ──► Stage 1b (N-0029 review)
         │                              └──► Stage 2.9 (lab dupes)
         ├─► Stage 3 (auth → RBAC → tunnel → ops) ──► Stage 5 (delivery)
         ├─► Stage 4 (data integrity)  ── approvals
         ├─► Stage 6 (planning journey)
         ├─► Stage 7 (promo intelligence) ── 7.4 waits for claim data
         ├─► Stage 8 (steward/import)    ── trigger-gated
         └─► Stage 9 (disti merge) ──► Stage 10 (multi-tenant)
```

Stages 2, 3, 4, 6 are mutually independent and can be chartered as parallel EIF nodes with different actors. Stage 1b must follow Stage 2. Stage 5 must follow 3.6.
