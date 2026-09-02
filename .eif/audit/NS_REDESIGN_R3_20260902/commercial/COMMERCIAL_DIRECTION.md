# Commercial capability direction — N-0013 r3 amendment (r3.1), 2026-09-02

Amends `../DIRECTION.md` (D-0007, proposed) for the commercial capability only. The shell, Overview /
Business dashboard, Reports, Stock & Sell-through, Supply & Inbound, Planning, Data & Stewardship, entity
context panels, command palette and capability directory are **unchanged** by this amendment. Nothing here
is production implementation; the React evidence lives in the isolated `(design-lab)` route group.

Companion artifacts in this folder: `CAPABILITY_ACCOUNTING.md` (source evidence per capability, with the
four-state vocabulary), `CONSULT_SEED.md` / `CONSULT_RESPONSE.md` (neutral seed → other model, claude opus
CLI, separate process), `rendered-verification.md` + `renders/` (27 captures @1280×800 and @390×844).

## 1. What the source and roadmap actually say

| Question | Finding | Evidence |
|---|---|---|
| What is "the promotion plan"? | A **CPOR case** (`cpor_case`: customer × window × promotion type) with **lines** (`cpor_case_line`: product × distributor × POD-quarter layer). Lifecycle `draft → proposed → approved/rejected → active → ended → settled/cancelled`. The `promotion_plan` importer r3 built its fixtures on is `enabled: False, hidden: True` (deprecated scaffold). | `docs/SPEC_CPOR_V1_AND_LISTING_CAPTURE_V0.md` §2; `apps/api/app/api/v1/endpoints/cpor_cases.py`; `apps/api/app/services/imports/template_definitions.py` |
| Does a planner exist? | Yes, **partially**: B4 "Promotion plan builder" (ROADMAP VERIFY PASS 2026-08-14) — `GET /cpor/intelligence/promo-plan-draft` proposes lines (history units, intake-weighted MAC, cover, SRP, 13-wk forecast, comparables, budget check); `PromoPlanBuilderPanel.tsx` edits them cell-by-cell and creates a case. Gaps: needs a hand-typed seed case id, no entity pickers, evidence scattered, no listing / competitor evidence joined. | `apps/api/app/services/cpor/promo_plan_builder.py`; `apps/web/src/app/(app)/promotions/PromoPlanBuilderPanel.tsx`; `docs/design/PROMO_PLANNER_CAPABILITY.md` H-01…H-14 |
| Export in the customer's format? | **Partial**: `POST /cpor/cases/{id}/export` writes a versioned XLSX, but the layout is a **frozen 32-column tuple in code** (`RESELLER_HEADERS`) while import maps 39 fields (H-01/H-02/H-03); no round-trip. | `apps/api/app/services/cpor/export_xlsx.py`; `apps/api/app/api/v1/endpoints/cpor_exports.py` |
| Is there already a "map a customer's template once" object? | Import side yes: `CporHistoricalMappingProfile` (`header_row_index`, `sheet_roles_json`, `column_map_json`, `value_maps_json`, `is_default`) — the profile that parsed 26,313 historical lines. Export side: only the lineup pattern `lineup_export_columns [{field, header}]` (D-056) on the tenant profile. Generic mapping UI exists (`CanonicalColumnMappingPanel`, used by DSI + shipments). | `apps/api/app/models/cpor_historical.py`; `apps/api/app/services/commercial_tenant_profile.py`; `apps/web/src/features/import-mapping/CanonicalColumnMappingPanel.tsx`; roadmap P3 "round-trip", P6 "productisation" |
| Website / listing intelligence | **Implemented** registry (`customer_listing`, never deleted, status history), observations (`listing_observation`, raw snapshot retained), scheduled + manual poll, CST feed proposals, auto-finder, activation check against the covering **CPOR line SRP** (`cpor_activation.py`), intelligence roll-up with first→last drift and a `not_activated` worklist. **Not built:** per-change events / alerts, late-activation & early-deactivation (derivable, not computed), SEO / listing-quality (spec v0 non-goal; roadmap P5), competitor listings (BACKLOG §9.9). | `apps/api/app/models/listing_capture.py`; `apps/api/app/services/listing_capture/{intelligence_v1,cpor_activation}.py`; shipped page `/listing-capture` (4 tabs) |
| Product competition | Mapping **workflow implemented** (`fact_competitor_mapping`, approve / reject / delete, page `/competition`) but **rows are seed-only**; deterministic candidate scorer `score_competitor_candidate` exists with **no caller**; `fact_competitor_price` **0 rows** and no import template; `market.py` **falsely** reports `competitor_price_import: ready`. | `apps/api/app/api/v1/endpoints/competition.py`; `apps/api/app/services/competition/matching.py`; `apps/api/app/api/v1/endpoints/market.py` |
| N-0010 | Title "NS-6 Actions container (was Response)", `blocked` on N-0013, ACs cite `CIP_DESIGN_LANGUAGE.md FROZEN v1.1 … container Response` — rejected design language. It is a *ranked-actions container*, not the planner; the planner is B4 and is already partly shipped. | `.eif/program/PROGRAM.yaml` N-0010; `.eif/ROADMAP.md` |

Doc/code contradictions recorded (see `CAPABILITY_ACCOUNTING.md` §6): `market.py` readiness claim; the
shipped `/promotions` page that mixes a dead scaffold notice with the live B4 builder; N-0010 ACs; r3
`DIRECTION.md` §3 "promotion_plan lines / price_observations".

## 2. Precise D-0007 delta (→ D-0008, proposed)

D-0007 stands except for the following, which D-0008 states explicitly:

| # | D-0007 (r3) | D-0008 (r3.1) | Why |
|---|---|---|---|
| Δ1 | Domain **Funding & Settlement** owns `cpor_case` as a money record (case book, claims, payments, terms). | Domain renamed **Promotions & Funding**; it owns the **whole `cpor_case` lifecycle** — Promotion planner (author / propose), Case book, Claims evidence, Payments, **Plan templates**, Terms & assumptions, Budget ledger. | Plan and settlement are the **same row** at different lifecycle stages; one entity → one home (r3's own placement rule). CONSULT Q1 → Option A. |
| Δ2 | Domain **Commercial inputs** owns "promotion_plan lines" and "price_observations"; Competition / Roadmap / Budgets hidden as "computes nothing". | Domain **removed**. Contents redistribute: promotion object → Promotions & Funding; listing + competition evidence → new **Market & Listings**; Product roadmap → Planning (`substrate`); Budget ledger → Promotions & Funding (`substrate`). | "Inputs" is internal jargon; its two fixture tables do not exist. CONSULT Q6. |
| Δ3 | — | New evidence domain **Market & Listings**: Monitored listings · Price history · Promotion activation · Feed proposals · Competitor mappings (`partial`) · Competitor prices (`substrate`) · Competitor listings (`planned`) · Listing quality / SEO (`planned`). | Reusable evidence with many consumers must not sit under one consumer (the planner). CONSULT Q2 → Option B. |
| Δ4 | Leaf visibility rule: **data-gated** — "computes nothing yet → hidden in rail, shown as not-yet-populated in directory" (binary). | **Withdrawn.** Four-state vocabulary `live · partial · substrate · planned` (`labNav.ts` `LeafStatus`). Rail = live + partial (partial is marked, and its unbuilt sub-areas are labelled inside the surface). Directory = all four, each labelled with a legend. | Operator truth 4; CONSULT Q4. Stored observations, mappings and planning workflows are first-class before derived analytics. |
| Δ5 | Export = "download CPOR XLSX". | **Canonical model ↔ per-customer template profile**: one direction-aware profile per customer template, learned once from an example workbook via `CanonicalColumnMappingPanel`, used to parse historical plans *and* to render exports; `RESELLER_HEADERS` retired; round-trip (export → re-import diffs to zero) is the certification. | Operator truth 1; CONSULT Q3 (Option A as a direction-aware profile, not a naïve symmetric map). |
| Δ6 | Cross-domain links from the product context panel: none to commercial evidence. | Product panel (Stock) links to *Retail listings & shelf price* and *Competitor products* in Market & Listings; case panel (Promotions & Funding) shows the **LifecycleRail** and links to Stock cover, Planning reservation, Market activation, Data terms. | Makes the evidence graph visible instead of implied. |
| Δ7 | Attention signals: `settlement_blocked` only. | Adds **proposed** signals (not fabricated numbers, computable from shipped read models): `promo_not_activated` (from the activation worklist), `listing_price_change` (first→last drift), `competitor_mapping_pending`. Shown as *proposed* in the Market surface, not as live counts on the Overview. | `CAPABILITY_ACCOUNTING.md` §5. |

Not changed: Overview / Business dashboard, Reports builder, Stock & Sell-through, Supply & Inbound,
Planning (gains one `substrate` leaf), Data & Stewardship, Administration, shell, command palette
(now filters by `inRail` and appends "(partly built)"), entity-panel concept, D-0002 deferred status.

## 3. Revised commercial IA

```
Promotions & Funding            one cpor_case lifecycle: author → approve → live → settle
├─ Promotion planner   partial  propose (CIP) or author (manual) a plan; edit lines; evidence per line; budget check; export via template
├─ Case book           live     every case across the lifecycle; LifecycleRail counts; blocked reasons; ageing
├─ Claims evidence     live     imported claim rows matched to case lines
├─ Payments            live     payment evidence; delivery rate (result ÷ estimate, descriptive)
├─ Plan templates      partial  customer workbook layouts mapped once to the canonical model (import works; export-side + learn-from-example planned)
├─ Terms & assumptions live     customer margin / rebate defaults, SKU assumptions
└─ Budget ledger       substrate fact_budget_* exist, 0 rows; planner uses the lineup-derived reservation

Market & Listings               evidence from the shelf, reused by planner / planning / stock / overview / attention
├─ Monitored listings  live     registry per customer × product; manual, CSV, feed proposals, auto-finder
├─ Price history       live     observed price + availability over time, covering case SRP overlaid
├─ Promotion activation live    each observation vs covering case-line SRP → live at price / not at promo price / no promotion covering
├─ Feed proposals      live     CST listing ids proposed for the registry; steward confirms
├─ Competitor mappings partial  our SKU ↔ competitor SKU with score + factors + approval; rows seed-only; scorer not wired
├─ Competitor prices   substrate table + list endpoint; no import, 0 rows
├─ Competitor listings planned  BACKLOG §9.9
└─ Listing quality / SEO planned roadmap P5
```

Ownership boundaries kept honest:
- **Canonical truth** stays on `cpor_case` / `cpor_case_line` (fields, waterfall, lifecycle, `roe_snapshot`). Templates are edge adapters.
- **Data & Stewardship** keeps masters, commercial terms, the Import Center (historical CPOR import launches there and links back to the profile), and the steward queue. Feed-proposal confirmation and competitor-mapping approval are *domain-intrinsic curation* and stay in Market & Listings (CONSULT Q2-C rejected).
- **Judgement call vs CONSULT:** CONSULT placed template profiles under Data & Stewardship; this amendment places **Plan templates** in Promotions & Funding because the profile is specific to the promotion model and the person who maps it is the person who exports with it; the Import Center links to it. Either is defensible — flagged in §7 as a minor operator choice, not a blocker.

## 4. Canonical ↔ external template architecture (design, not implementation)

Object: **promotion-plan template profile** (supersedes `CporHistoricalMappingProfile` rather than adding
a second, export-only profile — avoids the drift failure mode of two profiles per template).

| Element | Content | Existing seam |
|---|---|---|
| Identity | `code`, `customer_id` (nullable = tenant default), `version`, `status: draft / active / retired`, approver | `promo_plan_export` versioned-approval concept (legacy, `dim_promotion`) |
| Workbook shape | `sheet_roles`, `header_row_index` | `CporHistoricalMappingProfile` |
| Column bindings | `{canonical_field, external_header, output_order, import_transform, export_formatter, required_on_import, required_on_export, export_only/computed}` | `column_map_json` today; `lineup_export_columns [{field, header}]` shows the export-side shape |
| Value maps | per enum: external strings → canonical, plus a designated **emit** value canonical → external | `value_maps_json` today (import-only) |
| Certification | round-trip: export a case through the profile → re-import → diff canonical fields = 0 | roadmap P3 |

Operator flow (proven in `PlanTemplatesSurface.tsx`): upload an example customer workbook → map once with
the **production** `CanonicalColumnMappingPanel` → save as a named, versioned, per-customer default →
from any case: Export → pick profile → preview → versioned file. The planner's export dialog reads
headers/order/values/formats from the profile; the export ledger stays per case (`cpor_exports.py`).

## 5. N-0010 — placement and scope

N-0010 ("Actions container") is **not** the Promotion Planner and must not be silently repurposed into it
(that is how its ACs came to cite rejected language). Proposed disposition, **for operator decision**
(recorded as D-0009 proposed; no nodes are chartered by this run):

1. Retire N-0010's rejected framing (title, ACs citing FROZEN v1.1 / container Response).
2. Charter, after D-0008 acceptance, three post-N-0013 nodes hung off the accepted direction:
   - **Promotions & Funding surface** — overview → case book → lifecycle-tabbed case panel; B4 becomes the authoring surface of a draft case; adds from-scratch entry and entity pickers; retires the `/promotions` scaffold notice.
   - **Market & Listings surface** — the shipped `/listing-capture` and `/competition` pages re-homed under honest status; wire `score_competitor_candidate` behind "Propose candidates"; add the `promo_not_activated` attention signal; fix `market.py` readiness claim.
   - **Promotion-plan template profile** (§4) — cross-cutting; acceptance = map-once, same profile parses and renders, `RESELLER_HEADERS` removed, round-trip diff = 0.
3. If "ranked commercial actions" retains product value, keep a slimmed re-chartered node with non-rejected language, `planned`, decoupled from the planner.

Acceptance criteria for those nodes must state: no hard-coded template law; planner consumes listing /
competition evidence via the shared layer; substrate-only capabilities never rendered as working analytics;
**no fabricated uplift / elasticity / causality / impact / confidence** (uplift is BACKLOG §9.8, trigger
"5–10 settled cases with claim evidence across ≥3 customers").

## 6. How the commercial capabilities connect (made visible in the prototype)

| From | To | What the operator sees | Evidence |
|---|---|---|---|
| Promotion planner line | Stock & Sell-through | "Stock cover per line" (cover weeks vs target) in *Where this plan draws from*; line evidence shows on-hand / intake buckets behind MAC | `d-pf-plan-workspace.png`, `d-pf-line-evidence.png` |
| Promotion planner | Planning | "Budget after this plan" figure = lineup-derived reservation check (117 % flagged, not blocked); "Lineup forecast & budget reservation" link | `d-pf-plan-workspace.png` |
| Promotion planner | Market & Listings | "On shelf today 3 of 4" figure; per-line activation status; *Listings for these SKUs* and *Competitor products* links; competitors shown as counts (mapped / priced), never impact | `d-pf-plan-workspace.png`, `d-pf-line-evidence.png` |
| Promotion planner | Promotions & Funding (history) | Comparable cases (same customer + family) with approved support/unit, est → result, delivery rate | `d-pf-plan-workspace.png` |
| Promotion planner | Data & Stewardship | Customer terms (margin, VAT, template) link; template registry | `d-pf-plan-workspace.png`, `d-pf-templates-mapped.png` |
| Case panel | whole lifecycle | LifecycleRail on the case book and the case panel; the same case appears in planner (draft/proposed) and settlement (ended/settled) | `d-pf-casebook.png`, `d-pf-case-panel-lifecycle.png` |
| Market activation | Promotions & Funding · Attention · Overview · Claims | *Where this feeds* panel: planner column, proposed Brief signal, dashboard widget metric, claim evidence | `d-market-activation.png` |
| Competitor mapping | Planner · Planning · Stock · Reports | *Where this feeds* panel; product context panel in Stock links to *Competitor products* | `d-market-competition.png`, `d-stock-panel-market-links.png` |
| Directory | all | Four-state legend; every commercial leaf labelled; `planned` dimmed | `d-directory-status.png` |
| Command palette | all | "promotion" lists planner, case book, activation, templates; partial leaves marked "(partly built)" | `d-palette-promotion.png` |

## 7. Genuine decisions still required from the operator

1. **Accept D-0008** (D-0007 + Δ1–Δ7) as the r3.1 design direction — or name the contradiction.
2. **N-0010 disposition** (D-0009): retire framing + charter the three nodes in §5, and whether "ranked commercial actions" survives as a slimmed node.
3. **Template-profile increment**: single direction-aware bidirectional profile (recommended, §4) vs the faster lineup-style pair of import + export profiles linked by code (accepts drift risk).
4. Minor: **Plan templates** home — Promotions & Funding (as prototyped) or Data & Stewardship (CONSULT's pick).
5. Unchanged from r3: **D-0002** (cross-job steward queue restore vs retire) remains deferred; the prototype keeps it reachable.

## 8. Instructions examined and not blindly followed

- "Re-evaluate the current Commercial inputs domain … do not assume it must change": source showed its two fixture tables do not exist and its object is the same row as Funding & Settlement's; it was removed rather than renamed (CONSULT agreed).
- The prompt's "map an uploaded template … produce exports in that structure" could be read as *one symmetric map*; source (export-only computed columns, value-map inversion) argues for a direction-aware profile — adopted (§4).
- Operator truth 2 lists SEO / listing-quality and spec evidence; spec v0 names SEO a non-goal and only price/availability/badge are parsed. Both are shown, labelled `planned` / `substrate`, never as working views.
- "Do not prescribe a number of leaves": none prescribed; leaves fall out of shipped pages and tables.

## 9. What this amendment did not do

No production route, API, schema or business-logic change. No Alembic. No writes to `cip`. Prototype uses
fixture data only (`apps/web/src/design-lab/fixtures/commercial.ts`). Independence of the rendered evidence
is **NONE** (author-rendered); see `rendered-verification.md`.
