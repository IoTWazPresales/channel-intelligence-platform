# CURRENT state

**Last updated:** 2026-09-15 (GOV-008 N-0025–N-0029)

**Branch:** `feat/ns-2-brief-nav-collapse`

**Last content pin:** `fc15436` (N-0029 product). Last ledger pin: `247034a` (pre-review snapshot **724**; this run’s `PROGRAM.yaml` add was `CONTROL_PLANE_PROTECTED`). Last evidence pin: `52c006e`. Last views pin: `ad24c3e`. Run `GOV008_N0025_N0029_20260915` / actor `gov-008`.

**Alembic (code):** `20260906_0022` (`cpor_case.intelligence_exclude`)

**Alembic on cip:** `20260906_0022`

## On feat/ns-2-brief-nav-collapse

- **Operator UX (uncommitted, not this GOV-008):** Steward row opens `/admin/mappings?workspace=resolve&job=&entity_type=&token=` on the Steward queue leaf. Queue hides distributor/customer tokens with exactly one approved alias (open 2684 vs SQL 2814). `EnterpriseDataGrid` clips cell overflow. Start work uses Overview `Panel`/`PanelRow`. Not staged by GOV-008.
- **Programme:** PRG-20260831T145514. **N-0018–N-0026 complete.** **N-0027–N-0029** `in_progress` / `validate`; leases released. Run `GOV008_N0025_N0029_20260915` / actor `gov-008`. Do not reopen N-0013. D-0002 remains open.
- **GOV-008 N-0025–N-0029** (this session, vs impl NS13–NS17 / `gov-001`): Playwright 1280×800, no `browser_cdp`, `current_database()=cip` read-only. N-0025 **VERIFIED_WITH_LIMITATIONS complete** (steward queue now lists work; viewer live; planner user absent; Payments leftover BACKLOG-182). N-0026 **VERIFIED complete** (Computer Mania 2026Q2 compose 40 products / SQL 46 lines; no 257%; no other-customer rank; draft not confirmed). N-0027 **VERIFIED_WITH_LIMITATIONS not complete** (groups from `entity_type`; failed_imports lists failed jobs; live row click is dirty resolve workspace, not HEAD `/admin/imports?job=`). N-0028 **VERIFIED_WITH_LIMITATIONS not complete** (HEAD outlined cards; live dirty Panel wrapper fails no-wrapper AC; Lineup cases HeadlineStrip+ScopeBar SQL 7309/1647). N-0029 **VERIFIED_WITH_LIMITATIONS not complete** (grid above fold; unmatched `C19A50693` lands unfiltered payment-evidence — not acceptable follow-through; BACKLOG-196). Evidence `.eif/audit/GOV008_N0025_N0029_20260915/independent-rendered-review.md`. Do not remediate.
- **N-0029 implementer:** `EnterpriseDataGrid` community cell text selection. Case book HeadlineStrip → ScopeBar → grid first; overlay after. Playwright 1280: unmatched `C19A50693` → payment-evidence-import `?code=`. Settlement `/cpor-cases/<id>` UNCOVERED. UNCOVERED → BACKLOG-191–196. Evidence `.eif/audit/NS17_GRID_CASEBOOK_20260915/implementer-evidence.md`. Do not run GOV-008 on this node in this session.
- **N-0028 implementer:** Start work outlined Import Center cards (no Panel wrapper). **Import a lineup** → `/admin/imports?unified=1`. Create promotion plan retained. Lineup cases HeadlineStrip + approval ScopeBar (7309 units / 1647 lines live). UNCOVERED → BACKLOG-189/190. Evidence `.eif/audit/NS16_START_LINEUP_20260915/implementer-evidence.md`. Do not run GOV-008 on this node in this session.
- **N-0027 implementer:** Steward queue grouped by `import_entity_mapping_candidate.entity_type` (D-0008). Playwright 1280: `/admin/mappings` Open candidates **2814**; Steward → `/admin/imports?job=900`; `/brief` **47 failed imports** → `/admin/imports?jobStatus=failed` (not mappings). UNCOVERED → BACKLOG-187/188. Evidence `.eif/audit/NS15_STEWARD_QUEUE_20260915/implementer-evidence.md`. Do not run GOV-008 on this node in this session.
- **D-0010 accepted** Option A: keep rail expansion. Rail and tabs are not one destination set.
- **N-0026 implementer:** propose a promotion plan from customer + period on Promotion Planner (D-0008). Playwright 1280: Start work **Create promotion plan** → `/promotions?propose=1`; Computer Mania 2026Q2 compose **40** `commercial_lineup_line` rows, **10** same-customer comparables. Create draft not confirmed. Strip: drafts 0 / ended 74 / settled 210 / planned reserve $253k / actual support $650k — no 257%. UNCOVERED → BACKLOG-183–186. Evidence `.eif/audit/NS14_PROMO_PLAN_20260914/implementer-evidence.md`. Do not run GOV-008 on this node in this session.
- **N-0025 GOV-008:** independent clicks closed CST (to Choose file), settle (to Confirm settlement on case 46), steward queue (empty legacy; 2814 per-job). Viewer live: no Start work verbs. Planner live UNVERIFIED (no tenant user). Payments “Back to Payments lens” same-URL residual → BACKLOG-182. Evidence `.eif/audit/GOV008_N0025_20260914/independent-rendered-review.md`. Do not remediate N-0025.
- **N-0025 implementer:** one Start work panel on Overview `/brief`. Role-gated verbs route to existing screens (unified lineup, CST import, inbound import, case book, steward queue). Payments/Terms default to wizard/editor. Claims rows route to Import Center `cpor_claim_evidence` and Case book. Data four LensTabs kept; also-here strip names rail-only leaves. Sell-through filters/grid show names; API still ids. Empty Business dashboard compact below; Attention 431px at 1280 (not lab 312). Evidence `.eif/audit/NS13_START_WORK_20260914/implementer-evidence.md`.
- **N-0023 GOV-008 VERIFIED** vs impl `NS11_RAIL_20260913`. Sticky pin-during-scroll independently VERIFIED.
- **N-0024 GOV-008 VERIFIED_WITH_LIMITATIONS** vs impl `NS12_NAV_DEST_20260913`. Named destinations land on the named jobs.
- **GOV-008 N-0019–N-0022:** still recorded in `docs/design/gov-008-n0019-n0022.md`.

**Mobile:** DIRECTION §6 desktop-primary with named 390px workflows. N-0025 Start work VERIFIED at 390×844 (above Attention).

**Next:** Do not remediate N-0027–N-0029 in a review chat. Remaining: steward row href charter vs dirty resolve workspace; restore Start work Import Center cards on the running tree; payment-evidence `?code=` (BACKLOG-196). Uncommitted operator UX is a separate commit if accepted.

**Design language:** Production follows implemented design-lab React. Do not cite a frozen design-language version or grammar number.

**Deferred:** BACKLOG-174–180. BACKLOG-181 token port done; IA settled D-0010 Option A. BACKLOG-182 Payments same-URL leftover. BACKLOG-183–186 N-0026 UNCOVERED. BACKLOG-187/188 N-0027. BACKLOG-189 lineup `?product=`. BACKLOG-190 lineup authoring workbench. BACKLOG-191 settlement workspace. BACKLOG-192 dual column pickers. BACKLOG-193 AG Grid Enterprise. BACKLOG-194 Lineup ApprovalBadge. BACKLOG-195 Import Center/Market chrome. BACKLOG-196 payment-evidence `?code=`. BACKLOG-173. Budget ledger writer not chartered. Leftover `/market` stub. Stores master grid UNCOVERED. Cross-job steward accept/reject until Design Language v2. Pin-as-widget on Overview UNCOVERED. `/dashboard` legacy UNCOVERED.

**Env:** local Windows. Web `:3000` + API `:8001`. Sync/async engine on `cip` (`current_database()=cip`).
