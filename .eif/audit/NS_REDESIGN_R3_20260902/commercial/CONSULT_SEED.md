# CONSULT seed — Commercial capability architecture (N-0013 r3 amendment)

You are an independent reviewer. You have not seen the authoring session. Reason only from the evidence
below; mark anything that needs rendered or executable proof as UNVERIFIED. Do not edit files. Answer the
questions in order, rank options, and state the strongest counter-argument to your own recommendation.

## Context (accepted, do not re-open)

The product is CIP, a channel-intelligence platform (OEM → distributor → retailer → consumer). A design
direction (r3) proposes a domain-based primary navigation: Overview (business dashboard + attention +
reports) · Stock & Sell-through · Supply & Inbound · Planning (lineup cases) · Funding & Settlement ·
"Commercial inputs" · Data & Stewardship · Administration. Every domain has a composed overview page;
every number drills into an entity/case context panel; a command palette and a capability directory are
findability accelerators. The operator has said this broad direction is viable; the **Commercial** part
is the gap to fix. Nothing else is in question here.

Placement rule adopted in r3: *a workflow lives in the domain of its primary governed metric or entity.*

## Operator truths (constraints)

1. **Promotion Planner** is a plan-authoring workflow: CIP proposes a plan where supported; the user can
   also create one manually, edit proposed or existing plans, review the commercial evidence behind it,
   validate customer / product / period / pricing / support parameters, and **export the completed plan
   in the customer's external promotion-plan format**. Uploaded historical promotion workbooks are both
   historical data *and* examples of external plan structures; a new customer's template must be
   mappable once and then used for exports — not hard-coded.
2. **Website / listing intelligence** is a reusable evidence layer (monitored listings + URLs, price
   history, price-change detection, "is the planned promotion live at the planned price/time", late
   activation / early deactivation where evidence permits, SEO / listing-quality, product content
   evidence). It feeds Promotion Planner, analytics, dashboards, attention. It is **not** the planner.
3. **Product competition** = our SKU ↔ competing SKU(s). Mappings may be loaded, user-confirmed, or
   system-proposed where candidate scoring exists. Evidence is reusable by Planning, Promotion Planner,
   analytics, dashboards. Competitor products may have their own monitored listings.
4. Do **not** use "does not derive a metric today → hide the capability" as a general rule. Stored
   observations, monitored evidence, mappings, configuration and planning workflows are legitimate
   first-class capabilities before derived analytics exist. Unbuilt capability must still not be shown
   as if it worked.
5. No fabricated uplift, elasticity, causality, impact estimates or confidence figures.

## Source evidence (all paths under apps/api or apps/web; inspected by the authoring run)

### The promotion object
- `models/cpor.py` — `cpor_case` (case_code, customer_id, promotion_type, window_start/end, status,
  roe_snapshot, currency, channel, approval fields, superseded_by) and `cpor_case_line` (product_id,
  distributor_id, pod_quarter layer, srp, vat_rate, dealer_margin_pct, cost_basis + cost_source +
  cost_evidence_json, estimate_qty, cap_qty, computed dealer_price / support_unit / ttl_support /
  support_usd, result_qty, ttl_result). Spec `docs/SPEC_CPOR_V1_AND_LISTING_CAPTURE_V0.md` §2:
  *case = one customer × one promo window × one promotion type*; lifecycle
  `draft → proposed → approved | rejected → active → ended → settled | cancelled`.
- So the "promotion plan" and the "funding/settlement case" are the **same row** at different lifecycle
  stages. r3 placed the case book, claims, payments and settlement under *Funding & Settlement* and
  showed promotions as imported "promotion_plan lines" — which is wrong: `template_definitions.py`
  marks `promotion_plan` `enabled: False, hidden: True` ("Deprecated scaffold").

### Promotion Planner — implemented
- `endpoints/cpor_cases.py`: GET/POST `/cases`, PATCH case, POST lines, PATCH line, void, split-layers,
  recompute, cost-suggest, events, pivot, transition; `/intelligence/promo-plan-draft` (GET),
  `/recompute` (POST), `/create-case` (POST); norms, comparable-cases, support-bias, portfolio,
  incremental-unit-cost; promo-load-recon; settlement book/rollup; claim-evidence import.
- `services/cpor/promo_plan_builder.py` (B4, VERIFY PASS 2026-08-14 per `docs/ROADMAP.md`): draft
  seeded from a **prior case id** + period label → per-line history units, intake-weighted MAC (bucket
  A on-hand / bucket B intake, explain-only legs), cover weeks (session override), SRP, 13-week forecast
  volume, comparable cases count, budget check vs lineup-derived reservation (warn; hard-enforce env).
  Operator edits per cell (estimate_qty, cost_basis, srp, cover_weeks, distributor_id, pod_quarter);
  dirty cells survive refresh; Reset-to-suggested; Create writes a **draft** CPOR case.
- `app/(app)/promotions/PromoPlanBuilderPanel.tsx` — the shipped B4 grid (AG Grid, MAC bucket popover).
  Requires a numeric seed case id typed by hand; no "new plan from scratch" entry; product/distributor
  added by typing ids.
- Export: `endpoints/cpor_exports.py` POST `/cases/{id}/export`, GET exports, GET file (versioned).
  `services/cpor/export_xlsx.py` `RESELLER_HEADERS` — a **frozen 32-column tuple** in code (defect
  H-01 in `docs/design/PROMO_PLANNER_CAPABILITY.md`); import maps 39 fields; no round-trip (H-02/H-03).
- Historical import: `models/cpor_historical.py` `CporHistoricalMappingProfile` — **DB-stored tenant
  profile**: `profile_code, display_name, header_row_index, sheet_roles_json, column_map_json,
  value_maps_json, is_default`. Default profile `asus_consumer_cpor_tracking_v1`; 26,313 staged lines
  from the tenant tracking workbook (two sheets, Excel serial dates).
- Sibling pattern: lineup export uses a tenant-profile ordered `[{field, header}]` column map
  (`commercial_tenant_profile.lineup_export_columns`, D-056) — "column-mapped export … not OEM-branded
  app law". Legacy `promo_plan_export` model has `template_code` + versioned approval workflow (over
  the dead `dim_promotion`).
- The import-steward engine already has a generic mapping step (`CanonicalColumnMappingPanel`,
  `features/import-mapping`) used by DSI and shipments.
- Roadmap `docs/ROADMAP.md` B4: "author a new CPOR case — comparable historical cases (A2), volume (B1),
  budget check (B2), waterfall math, **export in tenant format**". P6: multi-tenant productisation.
  `PROMO_PLANNER_CAPABILITY.md` P3: "move H-06/H-07/H-14 into DB profiles — code ships generic engine
  only"; "round-trip acceptance test: export case → profile transform → re-import diff".
- Programme: node **N-0010 "NS-6 Actions container (was Response)"** is `blocked`, depends on
  N-0008/N-0009/N-0013, acceptance criteria still cite the rejected design language; it was conceived
  as a "ranked commercial actions" container, not as the planner described above.

### Listing intelligence — implemented / substrate
- `models/listing_capture.py`: `customer_listing` (customer_id, product_id nullable, url, marketplace,
  status active|out_of_stock|delisted|dead_link, source, external_id) and `listing_observation`
  (fetched_at, http_status, raw_snapshot bytes, parser_version, extracted_price, availability,
  promo_badge, parse_status, parse_flags JSONB).
- `models/cst_listing_seed.py`: marketplace ids seen in retailer sell-through feeds → proposals.
- `endpoints/listing_capture.py`: listings CRUD + CSV import, proposals confirm/reject/confirm-suggested,
  observations, `/poll`, `/reparse`, `/intelligence`. Services: `auto_finder.py` (Amazon / Takealot /
  Evetech URL suggestion), `takealot_fetch.py` (REST), `observation.py`, `cpor_activation.py`,
  `intelligence_v1.py`.
- `cpor_activation.py`: per observation, listing price vs covering CPOR **line** SRP (promo line first,
  sell-out bar only if no promo line) → `not_activated | price_consistent | no_case_detected |
  no_product_link | no_price`; persisted in `parse_flags.cpor_activation`. Explainable message.
- `intelligence_v1.py`: per listing — observation count, span days, ready (≥14 d), first/last price,
  drift %, latest activation status, `not_activated` worklist.
- Shipped page `/listing-capture`: tabs Registry · Feed proposals · Observations · Intelligence.
- Spec §8 non-goals v0 / §9 backlog: SEO/listing-content auditing, competitor listing monitoring
  (BACKLOG §9.9, trigger "first competitive-pricing decision needed"), price-drift alerts, promo-activation
  alerts to worklist (now partly shipped). Late activation / early deactivation is not computed but the
  observation timeline + line window make it derivable.

### Product competition — substrate with a thin UI
- `models/dimensions.py` `dim_competitor_brand`, `dim_competitor_product` (sku, name, category,
  specs_json). `models/facts.py` `fact_competitor_mapping` (product_id, competitor_product_id, score,
  explanation, approval_status pending|approved|rejected), `fact_competitor_price` (competitor_product_id,
  observed_at, price, channel, source_job_id).
- `endpoints/competition.py`: list mappings / prices, approve, reject, delete, clear-all. Page
  `/competition` "Competitor mapping": tabs Mappings · Competitor prices.
- `services/competition/matching.py` `score_competitor_candidate` — deterministic weighted blend
  (category 0.25, form factor 0.15, spec Jaccard 0.25, title tokens 0.25, price proximity 0.10) with
  factor breakdown and explanation string. **No caller** outside its package.
- Writers: `seed_demo.py` only. No import template for competitor prices (`market.py` placeholder claims
  `competitor_price_import: ready` — contradicted by `template_definitions.py`). `fact_competitor_price`
  0 rows on the dev DB per `PROMO_PLANNER_CAPABILITY.md`.
- Consumer: `services/planning/pricing.py` rule `comp_gap > 8% → consider_reduction` (feeds
  PricingRecommendation, which is seed-only).
- Note: `commercial_planner/lineup_po_competition.py` is unrelated (PO claim contention between lineup
  cases), despite the name.

### Cross-domain hooks already in code
- Planner draft reads: lineup reservation (Planning), forecast (Stock), intake/on-hand (Stock/Supply),
  comparable cases (Funding history), commercial terms (Data masters).
- Activation reads CPOR line SRP; recon reads retailer sell-through (Stock & Sell-through).
- Brief signal `settlement_blocked` exists; no signal yet for "promotion not activated" though the
  worklist is computed.

## Questions

**Q1 — Where does the Promotion Planner live, given one `cpor_case` spans plan → settle?**
Options (add your own):
- A. One domain owning the whole lifecycle (e.g. "Promotions & Funding": planner · case book · claims ·
  payments · settlement), replacing "Funding & Settlement".
- B. Keep "Funding & Settlement" for the money end; put Promotion Planner in a separate "Commercial"
  domain with market evidence. Same case appears in two domains at different stages.
- C. Put Promotion Planner under **Planning** beside Lineup planning (both are plan-authoring with
  tenant-format export; lineup reservation is the planner's budget check).
Evaluate against: the placement rule, information scent for an unfamiliar channel operator, workflow
efficiency (a KAM authoring a promo vs a finance user settling), and the roadmap.

**Q2 — Where do listing intelligence and product competition live?**
- A. Leaves inside the same domain as the planner ("market evidence" section).
- B. A dedicated evidence domain (e.g. "Market & Listings") separate from any planner.
- C. Split: registry/mapping stewardship (listings registry, competitor mapping approval) in Data &
  Stewardship; intelligence views in a commercial/market domain.
Consider that the evidence layer must be reusable by Planning, Stock, Overview widgets and attention.

**Q3 — Canonical → external template architecture for promotion plans.**
The repo has (i) a DB-stored *import* mapping profile (sheet roles, column map, value maps, header row),
(ii) a tenant-profile *export* column map for lineups, (iii) a frozen export header tuple for CPOR,
(iv) a generic mapping step in the import-steward engine. Options:
- A. Make the CPOR mapping profile **bidirectional**: one profile per customer/tenant template drives
  parse (import) and render (export); a new template is learned by uploading an example workbook
  through the standard mapping step and saving the profile.
- B. Keep separate import and export profiles (lineup pattern) and link them by profile code.
- C. Something else you consider stronger.
State what the UI should let a steward/planner do (map once, preview, export) and what must remain
canonical (the CPOR case/line model).

**Q4 — Honest status vocabulary.** r3 used a binary `populated: false → hidden`. Propose the smallest
status vocabulary that lets navigation and the directory distinguish implemented / partially
implemented / data substrate only / planned, and say which states belong in the rail vs only in the
directory, without pretending unbuilt capability works.

**Q5 — Programme.** N-0010 was chartered as an "Actions container (ranked commercial actions)". Given
the above, should it be re-scoped as the Promotion Planner unit, split, or retired in favour of new
nodes? What must its acceptance criteria say about template mapping and evidence reuse?

**Q6 — Name.** If a domain is created or renamed, propose 2–3 names an unfamiliar channel operator would
understand, and say which you would pick and why. "Commercial inputs" is on the table for removal.

Finish with a one-paragraph recommended architecture and the top three risks.
