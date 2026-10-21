# Sweep D: capabilities the product says are not finished

**Run:** PROGRAMME_20261007 · **Date:** 2026-10-07 · **Lenses:** product-manager (PB-002), business-analyst (PB-003)
**Mode:** read-only discovery (L1). The only file written is this one. Programme CLI not run; `.cursor`/`.claude` not touched.
**Question:** what does CIP itself say is planned, partly built, data only, a stub or "not built", what does the code actually do, and which ledger node (from `.eif/ROADMAP.md`) covers it?

## Sources and coverage

| Source | What I read |
|---|---|
| In-app capability ledgers | `apps/web/src/features/market-listings/capabilities.ts`, `features/promotions-funding/capabilities.ts`, `features/shell/navConfig.ts` (every `status:` leaf), `CapabilityDirectory.tsx`, `CapabilityStatus.tsx`, `workbench-ui/CapabilityLedger.tsx` (renderer only, no items of its own) |
| Other in-app "not built" text | ripgrep over `apps/web/src` (design-lab excluded) for: coming soon, not built, not wired, not offered, not calculated, not derived, stub, not in this release, later phase, not connected, plus disabled buttons with tooltips. Empty-state messages that only describe a load failure or missing data (for example `AdminOverview.tsx:53`, `SupplyOverview.tsx:42`, `CoverLensView.tsx:309`) are **not** capability gaps and are left out. |
| Stub routes | `app/(app)/market/page.tsx`, `app/(app)/pricing/page.tsx`, plus their API endpoints |
| Import Center | `services/imports/template_definitions.py` (`pipeline_handler: "stub_noop"`), `api/v1/endpoints/imports.py:257` |
| Spec | `docs/SPEC_CPOR_V1_AND_LISTING_CAPTURE_V0.md` §1 (out of scope), §7 (scaffold retirement), §8–§11 |
| Plan | `docs/design/STAGED_WORK_PLAN.md` §0b, §1, §2 |
| Old roadmap | `docs/memory/ROADMAP.md` (last verified 2026-08-13; it says to prefer `docs/ROADMAP.md`). I cross-checked it against `.eif/audit/BACKLOG_AUDIT_20260921/BACKLOG_AUDIT.md`. |
| Ledger | `.eif/ROADMAP.md` (generated view, N-0001..N-0084) |

When I say something was not found, I am describing what my search covered. It does not prove the thing is absent.

---

## 1. Inventory table

Legend for **declared**: `partial` = Partly built, `substrate` = Data only, `planned` = Planned (the `navConfig.ts:15-27` vocabulary). `none` in the last column means no ledger node covers the item.

### 1a. In-app ledgers and nav leaves

| # | Container › screen | Capability | Declared | Actual (evidence) | covered_by |
|---|---|---|---|---|---|
| 1 | Market & Listings › Monitored listings / Promotion activation | Price-change detection and alerts | partial (`market-listings/capabilities.ts:22-26`) | Only first→last drift per listing (`services/listing_capture/intelligence_v1.py:34` `_drift`). No price-change event or alert anywhere in `apps/api/app` (searched for price_change_event / listing_alert). | N-0076 |
| 2 | Market & Listings › Promotion activation | Late activation / early deactivation | substrate (`capabilities.ts:27-31`) | Not computed. A search for late_activation / early_deactivation found nothing. The "not activated" worklist exists (`api/v1/endpoints/listing_capture.py:269-285`). | N-0076 |
| 3 | Market & Listings › Monitored listings | Product content and specification evidence | substrate (`capabilities.ts:32-36`) | The raw page snapshot is kept, but only price, availability and badge are extracted (`MarketSurface.tsx:1439` says the extraction and rules layer is the remaining work). | N-0078 (same extraction layer; N-0078 is blocked) |
| 4 | Market & Listings › Listing quality / SEO | SEO / listing-quality monitoring | planned (`capabilities.ts:37-41`, `navConfig.ts:284`) | A placeholder panel only (`MarketSurface.tsx:1435-1442`). | N-0078 |
| 5 | Market & Listings › Price history | "Checked on a schedule" | **live** (`capabilities.ts:13-16`) | **Contradiction.** The beat entry `celery_app.py:49-52` does nothing unless `CIP_LISTING_CAPTURE_SCHEDULE` **and** `CIP_LISTING_LIVE_FETCH` are set (`worker/tasks.py:819-835`, `listing_capture/registry.py:37-38`). Both default to off: they are commented out in `.env.example:69-70`. The N-0073 supervisor deliberately never sets them (`scripts/cip-supervisor.ps1:18`). Beat is also off on Windows by default (`celery_app.py:71-72`). The manual poll returns 503 when the fetch flag is off (`listing_capture.py:296-300`). | none for switching it on (N-0073 only records whether the flags are present) |
| 6 | Market & Listings › Competitor mappings | Suggested matches with factor breakdown | substrate in the ledger (`capabilities.ts:50-54`) / partial in the nav (`navConfig.ts:269-275`) | A scorer exists (`services/competition/matching.py:67` `score_competitor_candidate`), but nothing outside `services/competition/` calls it. | N-0077 |
| 7 | Market & Listings › Competitor prices | Competitor price observations | substrate (`capabilities.ts:55-59`, `navConfig.ts:276-282`) | The table and list exist with no writer. `template_definitions.py` has no competitor-price template. `market.py:11-19` honestly reports `substrate`. | N-0077 covers prices captured by CIP itself. A **file import** of competitor prices is not in N-0077's title, so that part is not covered. |
| 8 | Market & Listings › Competitor listings | Monitored competitor listings | planned (`capabilities.ts:60-64`, `navConfig.ts:283`) | Placeholder only (`MarketSurface.tsx:1426-1433`). | N-0077 |
| 9 | Market & Listings › Competitor mappings | Competitor impact on our sell-out or price | planned (`capabilities.ts:65-69`) | The headline shows "—" with "Not calculated" (`MarketSurface.tsx:1294-1299`). | N-0077 |
| 10 | Promotions & Funding › Promotion planner | Propose a plan from history, cover, forecast and MAC | partial (`promotions-funding/capabilities.ts:5-9`, `navConfig.ts:211-217`) | You can propose from customer and period (N-0026). **Suggested quantity is not derived.** "Use CIP quantities" is a disabled button whose tooltip says "Suggested quantity is not calculated yet — cover and forecast are not on the line" (`PlanWorkspace.tsx:536-540`). | none |
| 11 | Promotions & Funding › Promotion planner / Plan templates / Payments | Export in the customer's promotion-plan format; render an export in the profile's layout | partial + planned (`capabilities.ts:25-29`, `:53-57`; `navConfig.ts:237-242`) | Export is one fixed layout compiled in code. The same "not built" text appears in `PlanWorkspace.tsx:417,674,770`, `PromotionPlannerSurface.tsx:588`, `PlanTemplatesSurface.tsx:165,191,338`, `historical-import/page.tsx:204` and `payment-evidence-import/page.tsx:214`. | none (the design-lab note says it belonged to N-0010, and N-0010 was rejected) |
| 12 | Promotions & Funding › Plan templates | Learn a profile from an example workbook | partial (`capabilities.ts:48-52`) | Header detection runs through `historical-import?learn=1` (`PlanTemplatesSurface.tsx:253-256`). Suggesting a mapping from a file is not a separate step. | none |
| 13 | Promotions & Funding › Promotion planner | Uplift, elasticity, effectiveness | planned (`capabilities.ts:30-34`) | Waits on data: needs at least 5 settled cases with claim evidence. The 2026-09-21 audit measured `cpor_claim_evidence_line` at 0 rows against 211 settled cases. | N-0063 (deferred) + N-0084 |
| 14 | Promotions & Funding › Budget ledger | Allocation → commitment → actual | substrate (`navConfig.ts:249-255`) | The models exist (`models/facts.py:337-368`, FactBudgetAllocation/Commitment/Actual/Request) with no writer. The planner uses the lineup-derived reservation instead. | N-0079 |
| 15 | Planning › Product roadmap | Lifecycle phase and replacement candidates | substrate (`navConfig.ts:195-201`) | `fact_product_roadmap` has no writer except `seed_demo.py`. `api/v1/endpoints/roadmap.py` only lists and deletes. Its only reader is `demand_forecast/analogue_compute.py:113`. There is no planning view. | none |
| 16 | Planning › Plans & line economics (planner defaults) | True landed cost (logistics, duties, freight) | "handled in a later phase" (`PlannerDefaultsMaintenance.tsx:517-518`) | Only controlled cost exists. DAP is explicitly not used as cost. | N-0080 |
| 17 | Supply & Inbound › Receipts & POD | A receipt page per shipment | partial (`navConfig.ts:171-177`) | POD import and matching live at `/admin/shipment-evidence`. The only supply routes are `/supply` and `/supply/shipments`, so there is no receipt-per-shipment route. | none |
| 18 | Overview › Pinned reports | Pin a saved report onto Overview | "not built" (`overview/OverviewHub.tsx:191`) | The panel lists saved reports and has no pin action. | none |
| 19 | Administration › Audit log | Platform-wide audit trail beyond steward actions | planned (`navConfig.ts:330`) | Only `steward_audit_event` (`models/steward_audit.py:15`) and `sql_viewer_audit` (`models/sql_viewer_audit.py:14`) exist. The leaf's href `/admin/steward-audit` is the same as the live "Steward audit" leaf (`navConfig.ts:316`). | none |

### 1b. Stub and orphan routes, and Import Center stubs

| # | Container › screen | Capability | Declared | Actual (evidence) | covered_by |
|---|---|---|---|---|---|
| 20 | (no container) `/market` "External market context" | Syndicated panel, share, macro feeds | "static JSON stub… not connected yet" (`app/(app)/market/page.tsx:19-20`) | `api/v1/endpoints/market.py:6-22` returns empty arrays plus one honesty hook. No in-app link to `/market` was found (searched `apps/web/src`, design-lab excluded), so the route is orphaned. | none |
| 21 | (no container) `/pricing` › Rule-based recommendations | Pricing recommendations from stock, cost and competitor context | Implied live ("appear after planning has been run", `pricing/page.tsx:223-224,300`) | **No writer.** `PricingRecommendation(` is only constructed in `services/seed_demo.py:402`. The endpoints list, delete and clear only (`api/v1/endpoints/pricing.py:151-203`). The route is orphaned: it is not in `navConfig` and no link was found. | none |
| 22 | (no container) `/pricing` › Recorded prices | Record a list or net price per SKU | live, with the copy "Unknown SKUs create placeholder products" (`pricing/page.tsx:251`) | **Defect against the never-auto-create-masters rule.** `pricing.py:96,128` calls `get_or_create_product`, which inserts `DimProduct(sku, name="Imported — {sku}")` (`services/facts_upsert.py:11-22`). | none |
| 23 | Data & Stewardship › Import Center | Customer/channel mapping import | "Not ready to apply yet" (`template_definitions.py:403-411`, visible) | `stub_noop`. The file is stored and never applied (`imports.py:257`; `admin/imports/page.tsx:494-495`). | none |
| 24 | Data & Stewardship › Import Center | Customer inventory & sales import | "Not ready to apply yet" (`template_definitions.py:420-428`, hidden) | `stub_noop` | none |
| 25 | Data & Stewardship › Import Center | Pricing & support (MDF) import | "Not ready to apply yet" (`template_definitions.py:696-704`, hidden, admin) | `stub_noop` | none |
| 26 | Data & Stewardship › Import Center | `lineup_plan` and `cpor_claim_evidence` in the generic wizard | visible (`template_definitions.py:709-717`, `:735-743`) | Both are `stub_noop` in the generic wizard. The real paths are lineup import and the case-scoped `services/cpor/claim_evidence_apply.py`. A user who picks either one here gets "full apply… not available yet". This is a routing and honesty gap, not a missing engine. | none |

### 1c. Spec `SPEC_CPOR_V1_AND_LISTING_CAPTURE_V0.md` §7–§11

| # | Item | Declared | Actual (evidence) | covered_by |
|---|---|---|---|---|
| 27 | §9.1 Distributor channel + New-DAP price protection | BACKLOG at spec acceptance | Not built. The open questions are in `.eif/ESCALATION.md:36`. | N-0081 |
| 28 | §9.2 Customer approval link for settlement | BACKLOG; trigger met | Searched for approval_link / approval_token / customer_portal / signoff_token: nothing found | N-0082 |
| 29 | §9.3 Product cost / profit definition | BACKLOG | See #16 | N-0080 |
| 30 | §9.4 FX rate table / ROE governance | BACKLOG | `fx_daily_rate` model (`models/fx_rate.py:17`) and the daily fetch task (`celery_app.py:59-63`) exist. Governance, and drawing case ROE from the table, is the open part. | N-0083 |
| 31 | §9.6 Listing intelligence v1 | BACKLOG | Activation check and not-activated worklist are built. Per-change alerts and late/early detection are not (#1, #2). | N-0076 |
| 32 | §9.7 Budget ledger | BACKLOG | See #14 | N-0079 |
| 33 | §9.8 Price elasticity | BACKLOG, waits on data | See #13 | N-0084 |
| 34 | §9.9 Competitor listing monitoring | BACKLOG | See #6–#9 | N-0077 |
| 35 | §8 non-goal: competitor discovery | v0 non-goal | Not built. (Auto URL discovery for our own listings is built: `listing_capture/auto_finder.py`.) | N-0077 |
| 36 | §10 U4.5 expected-report tracker: "`missing` worklist **+ notification**" | Spec requirement | Slots and the worklist are built (`imports/cst_d1.py:298-423`, beat at `celery_app.py:44-47`, shown on `/admin/cst-steward`). The code itself says "Notification wiring is left to callers" (`cst_d1.py:307`). `services/brief_signals.py` contains no CST or report signal, so a missing customer report never reaches Attention. | none |
| 37 | §7 / U6 retirement of the legacy promo scaffold | "migrate ALL readers"; dropping the tables is "a separate later migration decision" (spec l.128) | Old readers remain: `api/v1/endpoints/promotions.py:9,46,63` (FactPromotionPlan), `promo_exports.py:65,88,141,267` (DimPromotion), `promo_export/cpor_xlsx.py:3-6,62-65` ("This path still reads empty… scaffold"). `product_rankings.py:158` has been re-pointed. The tables have not been dropped. | none |
| 38 | §11: is `distributor_id` on a case line mandatory? ("Warren call at U3") | open item | Nullable in code (`models/cpor.py:101`). I found no recorded decision. | none (record the decision) |
| 39 | §11: what happens to the readiness tab | open item | Overtaken by events: `/promotions` is now the Promotion planner (`navConfig.ts:211-217`, N-0014/N-0026) | closed (superseded) |

### 1d. `STAGED_WORK_PLAN.md` §1–§2

| # | Item | Declared | Actual | covered_by |
|---|---|---|---|---|
| 40 | Stage 2.9: design-lab as a fixture skin (BACKLOG-158/161) | proposed | Lab duplicates are still present (`design-lab/fixtures/commercial.ts` mirrors the production ledgers) | N-0054 (blocked) |
| 41 | Stage 4.6: open→shipped double-count policy (BACKLOG-062) | not decided | Diagnostic only | N-0071 |
| 42 | Stage 4.7: non-operational sheets in the ACZA workbook (BACKLOG-046) | not decided | No allowlist | N-0072 (blocked) |
| 43 | Stage 7.4: uplift from settled claims | waits on data | See #13 | N-0063 (deferred) |
| 44 | Stage 8: steward and import engine follow-ons, 20 items: BACKLOG-077 email auto-ingest, 078 DSI layout-coalesce follow-ons, 080 batch confirm for CST article aliases, 049 unresolved worklist reader, 051 reconciliation report after apply, 059 catalogue semantic mapping, 067 backfill file provenance, 106 PoAutoLink steward parity, 123 promote/merge onto ResolutionWorklist, 187 replay of unresolved facts, 188 steward-queue coverage for non-candidate failures, 004 import-wizard componentisation, 037 DSI orchestrator unification, 011 bulk upsert for catalog_product, 018 geo indexes, 006 slim mapping-candidates, 008 DSI region hints, 016 deferred items in DSI finalize, 019 deferred slices of historical lineup, 020 PM job revisit | each waits on its trigger | Unchanged by this sweep. BACKLOG headings are at `docs/BACKLOG.md:323-2702`. | N-0069 (umbrella, proposed) |
| 45 | Stage 10: multi-tenant productisation (P6) | proposed | n/a | N-0070 |
| 46 | BU entitlements (user → product lines) | blocked on semantics | n/a | N-0065 |
| 47 | Historical lineup backfill (before 2025 Q1) | blocked (D-0020) | n/a | N-0060 |
| 48 | Column sets per catalogue (BACKLOG-198) | blocked (D-0023) | n/a | N-0068 |
| 49 | D-d: archive untracked files | proposed | n/a | N-0045 (blocked) |
| 50 | External API layer: first consumer (§2) | "Done as spec; first consumer = Warren" | Spec docs only (`docs/EXTERNAL_API_OUTBOUND.md`, `_INBOUND.md`); no endpoint built | none |
| 51 | §2: identifier preference for shipment evidence | open for Warren | Left untouched on purpose by N-0053 (`.eif/audit/PROGRAMME_20260924/n0053/DESIGN.md:50`) | none |
| 52 | §2: migration of paid/closed status on `cpor_case` | open for Warren | Not found in the EIF views | none |
| 53 | §2: the "16 vs 14" product-line count | open for Warren | cip measured 14 named lines plus 10 NULL rows (`STAGED_WORK_PLAN.md:54`) | none |

### 1e. Open items in `docs/memory/ROADMAP.md` (stale, 2026-08-13)

| # | Item | Declared | Actual | covered_by |
|---|---|---|---|---|
| 54 | BACKLOG-031: admin data-health dashboard | Parked; the audit re-homed it to Stage 3.6 | Searching the API, web and docs for data-health found no route or page. N-0052 is complete without it. | none (in practice) |
| 55 | BACKLOG-032: VACUUM runbook after bulk deletes | Parked; the audit re-homed it to Stage 3.6 | No runbook found in `docs/*.md` | none (in practice) |
| 56 | BACKLOG-025 remainder: frontend progress panel and slot registration for CST apply | Partial (`docs/BACKLOG.md:1787`) | Not verified in the browser; it was not in the N-0030 audit table | none |
| 57 | BACKLOG-057-D4 / 058-D5: Plan D column cleanup | Open (the audit rates them helpful, gated on a soak) | `shipment_evidence_line` still has 50 columns (audit) | none |
| 58 | BACKLOG-021 remainder: durable recommendation store and router extraction | Parked; RBAC part folded into N-0038 | Same gap as #21 | none |
| 59 | BACKLOG-014 customer classification import; BACKLOG-017 duplicate detection by embeddings | Audit proposed DROP; Warren has to confirm | Not built | none (decision) |
| 60 | BACKLOG-009 PIM typed attributes; BACKLOG-010 drop of legacy PAV rows | Parked; re-homed to Stage 10 | n/a | N-0070 |
| 61 | `task_run` read path not unified with the activity feed; `db_transient_retry` not on every commit path | Partial (`docs/memory/ROADMAP.md:104-105`) | Not re-verified in this sweep | none |

---

## 2. Items with no covering node, grouped into proposed work packages

| WP | Plain-word name | Items | One-line outcome | Size |
|---|---|---|---|---|
| D-1 | **Promotion plan suggests quantities** | #10 | "Use CIP quantities" fills each line from cover, forecast and the customer's history, with the evidence shown. Flag only, never block. | M |
| D-2 | **Export a plan in the customer's own workbook** | #11, #12 | A mapped plan template is used both ways: import reads it, and export writes the plan back into that customer's layout. The template can be learned from an example file. | M |
| D-3 | **Pricing page: wire it up or retire it** | #21, #22, #58 | Either recommendations get a real writer and the page joins the nav, or the route is retired. Either way, recording a price for an unknown SKU stops creating products and goes to the steward queue instead. | S (retire + fix auto-create) / M (wire) |
| D-4 | **Remove or define the external market stub** | #20 | Delete `/market` and `/api/v1/market/placeholders`, or write down the contract for the syndicated feed. Stop shipping an orphan page that only shows JSON. | S |
| D-5 | **Import Center: honest stub templates** | #23, #24, #25, #26 | Each `stub_noop` template is hidden, sent to its real path (lineup import, case claim evidence), or built. The user never uploads a file that silently goes nowhere. | S (honesty) / M per template built |
| D-6 | **Switch on scheduled listing checks** | #5 | Warren decides whether live storefront polling is on. If it is, the supervisor environment sets both flags. If it is not, the Market ledger stops saying "Checked on a schedule". | S |
| D-7 | **Alert on missing customer sell-through reports** | #36 | Late and missing report slots appear as an Attention signal with a link to the CST steward worklist. | S |
| D-8 | **Retire the legacy promotion scaffold** | #37 | The `/promotions` plans API and the `promo_exports` DimPromotion path are removed or pointed at CPOR cases. Dropping the tables is put to Warren as a decision. | S–M |
| D-9 | **Product roadmap planning view** | #15 | A writer (import or edit) for lifecycle phase and replacement candidates, and a planning view that lineup and forecast can use. | M |
| D-10 | **Shipment receipt page** | #17 | One page per shipment showing its receipts, POD evidence and matched lines. Receipts & POD then counts as works today. | S–M |
| D-11 | **Pin reports to Overview** | #18 | A saved report can be pinned or unpinned on Overview, per user. | S |
| D-12 | **Platform audit log** | #19 | One audit trail for admin, user, settings and case-state actions, beyond steward and SQL-viewer events. The nav leaf gets its own route. | M |
| D-13 | **Ops visibility leftovers** | #54, #55, #56, #61 | A data-health page (table counts plus import evidence), a VACUUM runbook, a CST apply progress panel, and a check that every commit path uses transient retry. | M |
| D-14 | **Shipment evidence column cleanup** | #57 | Plan D steps D4 and D5 run after the soak: no duplicated observation payload and no redundant columns. | S (gated) |
| D-15 | **Decisions for Warren (no build)** | #38, #50, #51, #52, #53, #59 | Six answers recorded: whether case-line distributor is nullable, the first API consumer, the shipment identifier preference, paid/closed migration, 16 vs 14 lines, and confirming the DROP of 014/017. Each goes in as a ledger decision. | S |

Not a separate package: the file import of competitor prices (part of #7) should be added to N-0077's scope or dropped explicitly when N-0077 is chartered.

### Findings (contradictions and defects)

- **F1. The ledger claims more than the code does (#5).** `LISTING_CAPABILITIES[1]` says checks run "on a schedule", but by default scheduled capture is off at three gates: two environment flags and Windows beat. Whether Warren's environment sets the flags is UNKNOWN (only presence is logged, `cip-supervisor.ps1:358`).
- **F2. A standing rule is broken (#22).** `/pricing` creates `DimProduct` rows for unknown SKUs, and the page copy announces it.
- **F3. A nav leaf duplicates another (#19).** "Audit log" (planned) points at the same href as "Steward audit" (live).
- **F4. Re-homed but never delivered (#54, #55).** The N-0030 audit sent BACKLOG-031/032 to Stage 3.6, and N-0052 completed without them.
- **F5. Two orphan routes (#20, #21).** `/market` and `/pricing` are reachable only by typing the URL. They are absent from the capability directory, so the "honest four-state" promise does not reach them.
- **F6. Stale source.** `docs/memory/ROADMAP.md` was last verified 2026-08-13 and is superseded by `docs/ROADMAP.md` and the ledger. It should be marked historical or pruned.
- **F7 (minor).** `market-listings/capabilities.ts:3` redefines `CapabilityItem` instead of importing it from `workbench-ui/CapabilityLedger.tsx:10`. The two can drift apart.

---

## 3. Counts

| Measure | Count |
|---|---|
| Items inventoried | 61 |
| From in-app ledgers and nav leaves (1a) | 19 |
| From stub/orphan routes and Import Center stubs (1b) | 7 |
| From spec §7–§11 (1c) | 13 |
| From staged plan §1–§2 (1d) | 14 |
| From the old memory roadmap (1e) | 8 |
| Covered by a ledger node | 31 |
| … by the new nodes N-0073..N-0084 | 20 rows (N-0076 ×3, N-0077 ×6, N-0078 ×2, N-0079 ×2, N-0080 ×2, N-0081, N-0082, N-0083, N-0084 ×2; several rows map to two nodes) |
| Closed or superseded | 1 (#39) |
| **Covered by none** | **29** |
| Proposed work packages for the uncovered items | 15 (D-1..D-15): 6 S, 5 M, 4 S–M or S/M |
| Findings | 7 (F1–F7) |

New nodes with **no** in-app declaration (they come only from the spec or operations): N-0073 (always-on), N-0074 (stable address), N-0075 (invite email), N-0081 (disti New-DAP), N-0082 (approval link), N-0083 (FX/ROE). This is expected. The product has no UI surface for these yet, so they do not appear in the capability directory.
