# SWEEP C — docs/BACKLOG.md lines 2064-3294

- Date: 2026-10-07. Branch `feat/ns-2-brief-nav-collapse`.
- Lenses: business-analyst (PB-003) for rules, traceability and edge cases; product-manager (PB-002) for whether the outcome is met and how to group the remaining work.
- Mode: read-only. This file is the only write. The programme CLI was not run.
- Scope: every `## BACKLOG-NNN` heading from line 2065 to the end of the file. That is 61 entries: 149-154, 156-179 and 181-211. There is no BACKLOG-180. BACKLOG-155 sits at line 2048, outside the range. The open-work sub-sections inside the range were folded into their parent rows: the BACKLOG-201 toolbar-parity table, and the B1/B2/D1/F1-F4/N1-N4/Stop-hook follow-ups under BACKLOG-204.
- Method: status comes from code (`apps/api`, `apps/web`, `scripts`, `alembic`), from git, and from the programme engine source (read with the Grep tool only). It does not come from the backlog entry's own status text.
  - Every commit hash cited below was confirmed with `git log --oneline -1`: `6111634`, `41a8c4b`, `3abad04`, `7656f67`, `b6e38fe`, `b5f7e13`, `39f457d`, `3f101a9`, `027f7e0`, `caf4bf8` and `5c8c7f5c`.
  - `.cursor/**`, `.claude/**` and `CLAUDE.md` were not opened, per the brief. Rows that depend on those files are marked UNCLEAR or carry a "not code-checked" note.
- Key: W = `apps/web/src`, A = `apps/api/app`. "—" in covered_by means the work is done and closed by a commit or node, so no open node owns it.

## 1. Entry table

| id | short title | status | evidence | covered_by | needs_warren |
|---|---|---|---|---|---|
| 149 | NS-2 nav collapse + Brief landing | DONE (delivered in domain IA) | `W/app/(app)/brief/page.tsx` renders `OverviewHub`; `A/api/v1/router.py:124` mounts `brief.router` at `/brief`. **Doc/code contradiction:** the 2026-09-21 audit stamp says "no `/brief` route", but the route exists. | N-0004 (complete) | no |
| 150 | NS-3 Stock merge (lenses) | DONE (delivered in domain IA) | `W/app/(app)/stock/page.tsx` mounts `StockContainer`. **Doc/code contradiction:** the stamp says "no `/stock` container route". | N-0007 / N-0016 (complete) | no |
| 151 | NS-4 Settlement queue + case split | DONE | `W/features/settlement/SettlementDeskLive` is mounted at `cpor-cases/[id]/page.tsx:6,16`. | N-0008 / N-0014 (complete) | no |
| 152 | NS-5 Lineup plan origination | DONE | `W/features/lineup/` holds LineupContainer, LineupPlanGrid, LineupPlanActionBar and LineupWorkspace. | N-0009 (complete) | no |
| 153 | NS-6 Response ranked actions | OBSOLETE | N-0010 was rejected (ROADMAP:14). `W/app/(app)/response` does not exist. | — | no |
| 154 | NS-7 Steward factory + worklists | DONE | The `W/app/(app)/admin/{imports,mappings,cst-steward,product-master-gaps,steward-audit}` routes exist; `W/features/data-stewardship/StewardQueueOverview.tsx` exists. | N-0011 / N-0027 (complete) | no |
| 160 | Commercial doc/code contradictions (market readiness, /promotions scaffold, N-0010 ACs) | DONE | `A/api/v1/endpoints/market.py:15-18` reports `competitor_price_import` as `"status": "substrate"`. No "scaffold" or "parked" text remains in `promotions/page.tsx`. N-0010 was rejected. | N-0031 (complete) | no |
| 156 | Lineup scope bar inert-control honesty | DONE | `W/features/lineup/LineupScopeBar.tsx` is deleted. Residual: `SettlementScopeBar.tsx` survives inside the unmounted `SettlementContainer` subtree (see WP-1). | N-0031 (complete) | no |
| 159 | EIF remedies R-1..R-9 for N-0013 governance defects | PARTIAL | Some remedies exist: the `rejected` and `deferred` node states (ROADMAP:5,63), independence provenance (`.eif/runtime/programme/eif_program/independence.py:49-99`), and retroactive and disclaim events (`engine.py:410-415`). A remedy-by-remedy check needs the EIF repo, which is outside this sweep. | none | no |
| 158 | Design-lab prototype disposition | PARTIAL (parked by decision) | 9 of 10 `W/design-lab/primitives/*` files are now re-exports of production modules. The `W/app/(design-lab)/design-lab/` route group is still present. | N-0054 (blocked, BL-0012) | no (decided 2026-09-29: leave as is) |
| 157 | Design language: interaction-honesty rule | OPEN | `docs/design/CIP_DESIGN_LANGUAGE.md` has no interaction-honesty rule. The only "honest" match is line 25, about pagination. | none | no |
| 161 | Design-lab duplicates of the production shell | PARTIAL (parked by decision) | The lab `CapabilityStatus` is a re-export (`design-lab/primitives/CapabilityStatus.tsx:1`). The lab still has its own `shell/CommandPalette.tsx` and `surfaces/DirectorySurface.tsx`. | N-0054 (blocked, BL-0012) | no (decided: leave until Warren asks) |
| 162 | Vitest 5s timeout flake | DONE | `apps/web/vitest.config.ts:17` sets `testTimeout: 15000`. | — | no |
| 163 | `eif_guard.py` dirty on CRLF | DONE | `.gitattributes:6-8` sets eol rules for the hooks directory. | — | no |
| 164 | I2 mapping-score explanation | DONE | `W/features/market-listings/MarketSurface.tsx:720` shows the stored "Why" column. Lines 1618-1621 show the stored explanation and the note that there is no factor panel. The rule carries forward: any future factor panel must show weights that sum to the displayed score. | N-0077 (carries that constraint forward) | no |
| 165 | EIF friction recorded in CIP (stdin watchdog) | DONE (CIP slice) | Commit `6111634` ("arm stdin watchdog before read"). The EIF-side remainder is tracked in 171 and 175-177. | — | no |
| 172 | Launcher passes hook event name before allow-on-crash | UNCLEAR | Not checked: the code lives in the hooks launcher and `hooks.json`, which this sweep excluded. The Claude Code adapter does carry `hook_event_name`, according to BACKLOG-204 text. | none | no |
| 166 | CONSULT writes no invocation record | OPEN | `.eif/CONSULT.md` has no rule for recording model, timestamp or exit code. No consult-invocation sidecar was found under `.eif/audit`. | none | no |
| 167 | CONSULT seed/response files are transcriptions | OPEN | Same check as 166. No capture-hash convention was found. | none | no |
| 168 | `ai_import_resolver` fails loudly without a key | DONE | `A/services/imports/ai_import_resolver.py:55-69` defines `AiResolverUnavailable` and raises it when the key or package is missing. Line 107 re-raises it, so it is not swallowed. Edge case: nothing catches it into a steward banner, so the operator sees an API error. | N-0052 (complete) | no |
| 169 | Engine cannot record post-hoc caveat resolution | DONE | `.eif/runtime/programme/eif_program/engine.py:410-411` now declares a `caveat.resolve` event type. | — | no |
| 170 | N-0006 cannot complete without a post-hoc implementation stamp | DONE | N-0006 is `complete` and labelled RETROACTIVE (ROADMAP:10), through `node.retroactive_complete` (`engine.py:410`). | — | no |
| 171 | Programme cannot reconcile out-of-order work | PARTIAL | `node.retroactive_charter`, `node.retroactive_complete` and `node.independence.disclaim` exist (`engine.py:410-415`, `retroactive.py`). Gap still open: a retroactive node cannot take a recorded historical implementation run without disclaiming independence (ESCALATION seq 1049, N-0035). | none | no |
| 173 | Guard NO_PROGRESS fingerprint degrades to None | UNCLEAR | Not checked: the code is in `eif_guard.py`, which this sweep excluded. | none | no |
| 174 | EIF-R1 verify semantics (structural vs live vs debt) | DONE | `.eif/runtime/programme/eif_program/cli.py:174-199`: `cmd_health` reports integrity separately from acknowledged and unacknowledged gate debt. | — | no |
| 175 | EIF-R2 durable run continuity | PARTIAL | Leases, stage notes and the `.eif/runs/` folders exist. No dedicated run-state artifact (next action, outstanding checks) was found: grep for `run_state` returned nothing. | none | no |
| 176 | EIF-R3 contract staleness vs superseding decisions | OPEN | grep for `stale`, `staleness` and `contract_stale` in `eif_program/` returned nothing. | none | no |
| 177 | EIF-R4 autonomous decomposition | PARTIAL | `engine.py:558` records the node origin `decomposition`. The GOV-001 rule now lets agents decompose work under a charter. There is no engine-side proposal generator. | none | no |
| 178 | Inbound "Arrived" lifecycle state | DONE | `A/services/commercial_planner/inbound_lineup_quarter.py:9,48,98-99` defines an `arrived` bucket, separate from the others. | N-0062 (complete) | no |
| 179 | Plan-unit PO coverage by distributor | DONE | `A/services/supply_overview.py:33-45`: `shape_plan_unit_po_coverage` returns `plan_units` and `backlog_units` per distributor. | N-0062 (complete) | no |
| 181 | Port the LabShell rail into production | DONE | `W/features/shell/CapabilityRail.tsx:32,85,98` keeps `NAV_STORAGE_GROUP_EXPANDED`. D-0010 Option A accepted. | N-0023 (complete) | no |
| 182 | "Back to Payments lens" same-URL leftover | DONE | `payment-evidence-import/page.tsx:271` has only "Back to cases". | — | no |
| 183 | Listing and competitor evidence on promotion plan lines | DONE | `A/services/cpor/promo_plan_builder.py` has `load_promotion_line_evidence`. Residual: it swallows exceptions into the same shape as an honest empty result (ESCALATION seq 1448). | N-0061 (complete) | no |
| 184 | Observed weeks-of-cover as a promotion input | DONE | `promo_plan_builder.py:614-634` sets the `observed_cover` flag and payload. | N-0061 (complete) | no |
| 185 | Uplift from settled claim evidence | OPEN (data-gated) | `cpor_claim_evidence_line` has 0 rows (D-0021). Nothing to build until claim rows exist. | N-0063 (deferred); N-0084 is adjacent | no (Warren 2026-10-05: no backfill) |
| 186 | A2-05 comparables include other customers | DONE | `A/services/cpor/norms_and_comparable.py:332` docstring "for the same customer"; lines 503-532 return `other_customers_excluded`. | N-0061 (complete) | no |
| 187 | Replay unresolved DSI facts after a catalogue-gap apply | OPEN | `A/services/imports/product_master_gap_resolve.py:5,101` is still FLAG-only, because `source_key` includes `product_id`. | N-0069 | no |
| 188 | Steward-queue coverage for non-candidate failure types | OPEN (trigger-gated) | No href registry for new entity types was found. Those failures stay on their dedicated surfaces. | N-0069 | no |
| 189 | Lineup cases `?product=` from the Cover lens | DONE | Commit `3abad04`; `W/features/lineup/LineupContainer.tsx:99` filters by `product_id`. | — | no |
| 190 | Lineup authoring workbench besides unified import | DONE | Commit `5c8c7f5c`. `.eif/audit/PROGRAMME_20260930/N-0057.md` shows a next-quarter bar, Apply net requirement (`/lineup/apply-net-requirement`), import and export on `/lineup/cases`. Manual line-by-line authoring was not built; the node chose the computed workbench. | N-0057 (complete) | no |
| 191 | Settlement workspace at `/cpor-cases/<id>` | DONE | `cpor-cases/[id]/page.tsx:16` renders `<SettlementDeskLive>`. Residual, per the entry: paid and closed are not stored on `cpor_case`. | N-0044 (complete) | no |
| 192 | One column picker for every grid host | DONE | Commit `7656f67`: `ColumnPickerDialog` covers both hosts with size md or wide. | — | no |
| 193 | AG Grid range selection and Excel export | OBSOLETE (dropped) | `apps/web/package.json:27-28` has only `ag-grid-community` and `ag-grid-react`; the Enterprise licence was refused. N-0043 shipped CSV export instead. | — | no |
| 194 | Lineup ApprovalBadge leftover | DONE | Commit `b6e38fe`. No `ApprovalBadge` remains in `W`. | — | no |
| 195 | Explanatory chrome above the grid (Import Center, Market) | DONE | Commit `b5f7e13`. | — | no |
| 196 | Payment-evidence import reads `?code=` | DONE | `payment-evidence-import/page.tsx:67-68` calls `parseExactPaymentEvidenceCode(search.get('code'))`. | — | no |
| 197 | Steward "restore vs retire" copy vs D-0011 KEEP | DONE | Commits `39f457d` and `3f101a9`. No "restore vs" or "restore or retire" text remains in `W`. | — | no |
| 198 | Per-product-line PM column sets vs `catalog_product` | PARTIAL | `A/services/imports/pm_mapping_memory.py:36,50` reads the `by_product_line` overlay (this file has uncommitted changes in the working tree). N-0040 settled the sellable grain as every `product_line`, which contradicts the entry's 2026-10-05 note "sellable grain five vs sixteen is still open". | N-0068 (blocked, BL-0006 / D-0023) | **yes**: the entry records Warren's answer "keep multiple catalogs; do not retire `catalog_product`", but D-0023 ("does catalog_product stay the catalogue, get retired, or is it unrelated…?") is still open in the ledger. Warren should confirm that his answer closes D-0023. |
| 199 | MarketSurface mappings grid has no loading or error state | DONE | `MarketSurface.tsx:30,1051-1073` wraps the grid in `ModuleDataSection`. | N-0031 (complete) | no |
| 200 | `MasterColumnPickerDialog` is a dead test-only wrapper | OPEN | `W/components/masterGrid/MasterColumnPickerDialog.tsx` and its test still exist; no other file references the wrapper. The hold reason ("do not unify", N-0029 AC) went stale when `7656f67` unified the pickers. | none | no |
| 201 | Tier A fact grids have no column picker | DONE | `A/services/grid_fields.py`; `A/api/v1/router.py:138` mounts `/grid-fields`. The parity table's search, saved views and export went to N-0041, N-0042 and N-0043, all complete. | N-0034 (complete) | no |
| 202 | `CporCaseWorkspace` unmounted | DONE | The component is gone; only comments mention it (`CporUsdPivotPanel.tsx:38`, `page.fxReadiness.test.tsx:10`). Residual: the unmounted `SettlementContainer` subtree is kept pending D-0032(2). | N-0044 (complete) | no (residual is engineering hygiene) |
| 203 | Seven API tests assume a clean database | OPEN | None of the named test files changed after the entry was raised. Last commits: `test_distributor_sales_inventory_import.py` bd99ada4 2026-08-01, `test_shipment_resolved_entities.py` 40328497 2026-06-29, `test_data_integrity_audit.py` 6b84187f 2026-07-03, `test_dsi_validate_bulk_staging.py` b61e7db5 2026-08-01. | none | no |
| 204 | EIF guard does not fire under Claude Code | PARTIAL | Enforced since `027f7e0` and `caf4bf8` (B1 and B2 resolved). Still open: D1, the Stop hook (not registered) and N1-N4. N4 was seen again today: `SendMessage` and `SubagentHandback` were refused `SHIM_TOOL_UNMAPPED` (ESCALATION seq 1542). | none | **yes (D1)**: "should the writable part narrow to runtime state and `.eif/audit/**`, or is `.eif/**` meant to be agent-writable?" This is a governance policy question, not a domain rule. |
| 205 | Rotate pilot passwords | UNCLEAR | This is an operator credential action and leaves nothing in code to check. The pilot is still running (N-0073 always-on, N-0075 invites). | none (N-0075 is adjacent) | no (an action for Warren, not an undecided rule) |
| 206 | API binds `0.0.0.0` | DONE | `scripts/dev-api.js:135` binds `127.0.0.1`; line 213 warns when the bind is not loopback. | N-0036 (complete) | no |
| 207 | Guard `.env` sensitive-read matcher is root-only | PARTIAL | According to the entry, the read and search paths were fixed (re-probe P7) and a shell read of `.env` is still allowed (P7c). Not code-checked, because the policy lives in excluded paths. | none | no |
| 208 | Shim resolves the guard from cwd; one `cd` wedges the session | OPEN (not code-checked) | The compiled CLAUDE.md rule still says "Never `cd`" as a workaround. The shim lives in excluded paths. | none | no |
| 209 | VERIFY debt: ScopeBar holds the column picker | OPEN | No Opus CONSULT or VERIFY verdict is recorded under `.eif/audit/PROGRAMME_202610*`. This blocks promotion of the branch to `main`. | none (the debt sits on N-0034) | no |
| 210 | Line identifier `both`: text-slot consumers weld SKU and model | OPEN | `W/features/commercial-planner/CurrentLineupSection.tsx:3126,3288,3344` still has `colId === 'sku'` branches that build one welded string. | none (finding.defer on N-0053) | no (the per-caption choice is a UX call) |
| 211 | Second validation of nodes closed without Opus | OPEN | The set has grown: `.eif/audit/PROGRAMME_20260930/N-0043.md:17` cites BACKLOG-211 for N-0043. No second-pass record was found. | none | no |

## 2. OPEN or PARTIAL with covered_by none, as proposed work packages

Rows that are UNCLEAR and unowned (172, 173, 205) are placed in the closest package and tagged *(unclear)*.

**WP-1 — Remove dead web code** (S)
- ids: 200, plus residuals of 202 and 156: the unmounted `SettlementContainer` subtree, including `SettlementScopeBar.tsx`.
- Outcome: no component in `apps/web` is reachable only from its own test.
- Dependency: Warren answers D-0032(2) ("delete the SettlementContainer subtree?"). The N-0029 AC hold on 200 has to be lifted as stale: commit `7656f67` already unified the pickers.

**WP-2 — Make the API test suite environment-independent** (S-M)
- ids: 203.
- Outcome: the seven named tests seed and clean up their own rows, or run against `cip_test` with an `integration` mark, so a red suite always means a code defect.
- Dependency: none. Related to BACKLOG-144 and BACKLOG-100 (outside this range).

**WP-3 — Second-look verification of closed nodes** (S, no build)
- ids: 209, 211.
- Outcome: N-0034, N-0043, N-0049 and N-0053 (and any later self-verified closes) get an independent pass from a fresh session or another model. Each result is recorded as later evidence.
- Dependency: Opus or fresh-session capacity. This gates promotion of `feat/ns-2-brief-nav-collapse` to `main`.

**WP-4 — Split the lineup workbench identifier into two columns** (S-M)
- ids: 210.
- Outcome: the `CurrentLineupSection` workbench shows SKU and Sales model as two real columns under `both`. Captions and drawer titles keep the welded string unless Warren asks otherwise.
- Dependency: the workbench moves onto `useFactColumns` / `ColDef[]`.

**WP-5 — Write the interaction-honesty rule into the design language** (S, docs only)
- ids: 157.
- Outcome: `CIP_DESIGN_LANGUAGE.md` says an inert control must be disabled or labelled unavailable, so reviewers apply one standard across containers.
- Dependency: none. The rule applies to future work only.

**WP-6 — Fix the Claude Code guard and shim (EIF repo)** (M)
- ids: 204 residuals (Stop hook with a fail-open mapping; N1 Chrome origin gating; N2 server-scoped MCP grants; N3 install script; N4 unmapped `Skill`, `Artifact`, `SendMessage` and `SubagentHandback`), 207 (shell `.env` read), 208 (cwd root discovery), 172 *(unclear)*, 173 *(unclear)*.
- Outcome: Claude Code sessions do not wedge, subagents can hand back reports, and in-page Chrome actions are origin-checked.
- Dependency: Warren authorises an EIF-repo session. D1 needs his policy answer first.

**WP-7 — Programme engine and CONSULT provenance (EIF repo)** (L)
- ids: 171 (historical implementation run on a retroactive node), 175 (durable run state), 176 (contract staleness), 177 (proposal layer), 159 (remaining R-items), 166 and 167 (CONSULT invocation record and capture hash).
- Outcome: the ledger can record pre-existing work without disclaiming independence; stale node contracts are flagged; each CONSULT leaves its own invocation record in the repo.
- Dependency: an EIF-repo session. 176 and 177 depend on 174, which is done.

**WP-8 — Rotate pilot credentials** (S, operator action)
- ids: 205 *(unclear)*.
- Outcome: the placeholder `admin@local` and `viewer@local` passwords are rotated, or retired by the N-0075 invite flow.
- Dependency: the end of the pilot, or N-0075 landing.

**Residual finding, not a backlog id — make promotion-evidence read failures visible** (S)
- Source: BACKLOG-183 residual, ESCALATION seq 1448.
- Outcome: when `load_promotion_line_evidence` fails, it logs the failure and returns a state the planner can tell apart from "Not listed".
- Dependency: none.

## 3. Counts

61 entries in range.

| status | count | ids |
|---|---|---|
| DONE | 34 | 149, 150, 151, 152, 154, 156, 160, 162, 163, 164, 165, 168, 169, 170, 174, 178, 179, 181, 182, 183, 184, 186, 189, 190, 191, 192, 194, 195, 196, 197, 199, 201, 202, 206 |
| OBSOLETE | 2 | 153, 193 |
| OPEN | 13 | 157, 166, 167, 176, 185, 187, 188, 200, 203, 208, 209, 210, 211 |
| PARTIAL | 9 | 158, 159, 161, 171, 175, 177, 198, 204, 207 |
| UNCLEAR | 3 | 172, 173, 205 |

- OPEN or PARTIAL owned by a node: 6. They are 158 and 161 (N-0054), 185 (N-0063), 187 and 188 (N-0069), and 198 (N-0068).
- OPEN or PARTIAL owned by no node: 16. They are 157, 159, 166, 167, 171, 175, 176, 177, 200, 203, 204, 207, 208, 209, 210 and 211. Ten of them (159, 166, 167, 171, 175, 176, 177, 204, 207, 208) are EIF-repo or control-plane work, not CIP product work.
- needs_warren = yes: 2. They are 198 (confirm that the 2026-10-05 answer closes D-0023) and 204 D1 (`.eif/**` write scope).

## 4. Doc/code contradictions found

1. **149 and 150.** The N-0030 audit stamps say "no `/brief` route" and "no `/stock` container route". Both routes exist: `brief/page.tsx` mounts `OverviewHub`, and `stock/page.tsx` mounts `StockContainer`. "Superseded" is the wrong label; these were delivered under the domain IA.
2. **198.** The entry's status line (2026-10-05) says "Sellable grain five vs sixteen is still open". N-0040 (complete) settled the sellable BU grain as every `dim_product.product_line`. The same status line records Warren's answer to D-0023, yet BL-0006 is still open on N-0068.
3. **169, 170 and 174.** These still read "Parked" or "Accepted", but the installed engine now has `caveat.resolve`, `node.retroactive_complete` and debt-aware `health`.
4. **200.** It is HELD on "do not unify the pickers", but `7656f67` already unified them. The hold no longer has a reason.
