# Independent review ÔÇö Commercial capability architecture (N-0013 r3 amendment)

**Scope note / verification stance.** I reason only from the seed and its cited evidence. I have not rendered any page or executed any code in this session, so every claim about shipped behavior (B4 lacking a from-scratch entry, `fact_competitor_price` = 0 rows, `RESELLER_HEADERS` still frozen, `promotion_plan` deprecated, N-0010 ACs citing rejected language) is **UNVERIFIED here** and inherited from the authoring run's inspection. As a consult, I make no edits or ledger writes; programme changes below are FLAGs for the operator.

---

## Q1 ÔÇö Where the Promotion Planner lives

**Recommendation: Option A** ÔÇö one domain owns the whole `cpor_case` lifecycle, replacing "Funding & Settlement."

The decisive fact is that plan and settlement are **the same row** (`cpor_case`, `draftÔåÆproposedÔåÆapproved|rejectedÔåÆactiveÔåÆendedÔåÆsettled|cancelled`). The r3 placement rule ("a workflow lives in the domain of its primary governed entity") points at one entity ÔåÆ one home. Options B and C both split one row across two domains, which is the same category error r3 already made (case book under Funding & Settlement, promotions shown as deprecated `promotion_plan` lines ÔÇö `enabled:False, hidden:True`).

- **B (planner in a separate "Commercial" domain, settlement in Funding & Settlement):** rejected ÔÇö two homes for one entity; forces the operator to learn that a promo "moves" domains as it ages, which is poor scent.
- **C (planner under Planning beside Lineup):** tempting because both are plan-authoring with tenant-format export and lineup reservation is the budget check. But the case's *primary governed metric is promotional support/funding money*, not a lineup PO, and the case continues into settlement, which is plainly not "Planning." C re-splits the lifecycle (author in Planning, settle in Funding). The lineupÔåöplanner coupling is a **cross-domain read**, not a co-location argument.
- **A:** the composed overview ÔåÆ case book ÔåÆ a **case context panel whose tabs follow the lifecycle** (Author/Plan, Evidence, Claims, Payments, Settlement). The shipped B4 grid (`PromoPlanBuilderPanel`) becomes the *authoring surface of a draft case* ÔÇö and should gain a real "new plan from scratch" entry and entity pickers instead of hand-typed seed/product/distributor ids.

**Strongest counter to my own answer:** persona collision. A KAM authoring a promo and a finance user settling one have different mental models; one domain risks burying the everyday planner under finance machinery (or vice versa). Mitigate with role-aware default landing, a lifecycle-stage filter on the case book, and command-palette shortcuts ÔÇö but the tension is real (it reappears as Risk 1).

---

## Q2 ÔÇö Where listing intelligence and product competition live

**Recommendation: Option B** ÔÇö a dedicated **"Market & Listings"** evidence domain, *not* leaves under the planner.

Operator truths 2 and 3 make this reusable evidence with many consumers (planner, Planning, Stock, Overview widgets, attention, analytics). Burying it under the planner (A) couples a shared layer to one consumer and destroys scent for the others. The capability is also already cohesive and shipped as pages (`/listing-capture`: Registry ┬À Feed proposals ┬À Observations ┬À Intelligence; `/competition`: Mappings ┬À Competitor prices).

- **C (split stewardship into Data & Stewardship, intelligence into a market domain):** rejected as the primary shape ÔÇö registry, observations, and intelligence are tightly coupled (the activation/drift views *are* the timeline over the registry); splitting them harms findability for the person actually monitoring listings. Reserve Data & Stewardship for genuinely cross-cutting masters (products, customers, distributors, commercial terms, and the template profiles from Q3). The confirm/reject-proposal and approve-mapping curation here is **domain-intrinsic**, not generic master-data stewardship.

Consumers link *into* this domain's entity panels; Overview and attention read its computed signals (note: `settlement_blocked` exists but there is **no** "promotion not activated" brief signal yet, though the worklist is computed ÔÇö a cheap, honest win).

**Counter-argument:** competition today is substrate-only (`score_competitor_candidate` has no caller, `fact_competitor_price` 0 rows, `PricingRecommendation` seed-only), and `market.py` already lies (`competitor_price_import: ready`, contradicted by `template_definitions.py`). A whole domain risks overstating maturity and inflating the rail. Mitigate by starting it as a single composed page and enforcing the Q4 status vocabulary (Risk 3).

---

## Q3 ÔÇö Canonical Ôåö external template architecture

**Recommendation: Option A structurally, but as a *direction-aware* bidirectional profile** (a C-flavored A). One per-tenant template object learned once, driving both parse and render ÔÇö but internally carrying per-direction transforms, not a na├»ve symmetric map.

Truth 1 says the uploaded workbook is *both* historical data *and* an example of the external structure ÔÇö so the mapping that parses it should render exports back into it. The roadmap already wants this (P3 round-trip test; P6 productisation), and the frozen 32-column `RESELLER_HEADERS` tuple (defect H-01) is exactly what to kill.

Why not na├»ve-A or B:
- **Na├»ve symmetric map** can't express export-only/computed columns (`dealer_price`, `support_unit`), value-map *inversion ambiguity* (two external strings ÔåÆ one enum: which do you emit?), or output ordering/formatting (Excel serial dates, 32 vs 39 columns).
- **B (separate import + export profiles linked by code, the lineup pattern):** legitimate as a *first increment* (fast, matches `commercial_tenant_profile.lineup_export_columns`), but its failure mode is drift ÔÇö two profiles for one template diverge, which is precisely what "mappable once" forbids.

**Proposed object** (extend `CporHistoricalMappingProfile` ÔåÆ a superseding tenant template profile): `sheet_roles`, `header_row_index`, and a **column-binding table** `{canonical_field, external_header, import_transform, export_formatter, output_order, is_export_only|computed}`, plus `value_maps` that designate a canonicalÔåÆexternal **emit value** per enum, plus **versioning + approval** (reuse legacy `promo_plan_export`'s `template_code`/versioned-approval concept). Export reads headers/order/values/formats from the profile; `RESELLER_HEADERS` is deleted.

**UI (steward/planner):** (1) upload an example customer workbook; (2) map once via the existing generic `CanonicalColumnMappingPanel` (`features/import-mapping`, already used by DSI/shipments) with a parsed-row preview; (3) save as a named, versioned, per-customer default profile; (4) from any case, Export ÔåÆ pick profile ÔåÆ **preview the rendered workbook** ÔåÆ download versioned file; (5) run the round-trip check (export ÔåÆ re-import diff) to certify the profile.

**Must remain canonical:** the `cpor_case`/`cpor_case_line` model itself ÔÇö fields, the computed dealer_price/support waterfall, lifecycle, `roe_snapshot`. Tenant profiles are pure edge adapters; all truth and math live on the canonical model.

**Counter-argument:** import wants to be permissive (messy historical workbooks, extra sheets, partial columns) while export must be precise/complete; one object risks a lax export or a rejecting import. Mitigate with **direction-scoped required/optional flags** on each binding ÔÇö one object, two validators.

---

## Q4 ÔÇö Honest status vocabulary

Replace binary `populated:falseÔåÆhidden` with **four states**:

| State | Meaning | Rail? | Directory? |
|---|---|---|---|
| `live` | end-to-end usable on real data | Ô£à | Ô£à |
| `partial` | some flows work, others stubbed/seed-only (e.g. Promotion Planner: author/export work, round-trip H-02/H-03 missing; listing intelligence: page shipped, competitor monitoring not) | Ô£à (marked; non-working sub-areas unlinked) | Ô£à |
| `substrate` | models/endpoints exist, no working user-facing derived capability (e.g. product competition ÔÇö scorer, endpoints, but no caller, 0 rows, seed-only consumers) | ÔØî | Ô£à ("data only ÔÇö not a usable view"; curation entry may surface where genuinely possible) |
| `planned` | chartered, not built | ÔØî | Ô£à (clearly labelled) |

Rail = `live` + `partial` only. Directory = all four, each labelled ÔÇö this is what makes the directory an honest capability catalog (truth 4) rather than a menu of lies. Deprecated scaffold (`promotion_plan hidden:True`) is simply *not a capability* ÔÇö excluded entirely; no fifth state needed. This vocabulary's whole purpose is to stop the `market.py competitor_price_import: ready` class of misstatement ÔÇö **flag that as a `substrate` masquerading as `live`.**

---

## Q5 ÔÇö Programme (N-0010)

N-0010 ("NS-6 Actions container / ranked commercial actions", blocked, ACs citing rejected design language) is **not** the Promotion Planner ÔÇö different concept, and the planner (B4) is already largely shipped. **Do not silently repurpose N-0010 into the planner** (that is how ACs come to cite rejected language in the first place).

**Recommendation: retire N-0010's rejected framing and split into new nodes** hung off the accepted r3 direction:
1. **Promotions & Funding domain surface** ÔÇö overview ÔåÆ case book ÔåÆ lifecycle-tabbed case panel; builds on shipped B4; closes H-01 (kill frozen tuple) and the from-scratch/entity-picker gaps.
2. **Market & Listings evidence domain** ÔÇö surface listing intelligence + competition under honest status; add the "promotion not activated" brief signal.
3. **Bidirectional template profile** (Q3) ÔÇö separate because it is cross-cutting and has a concrete, testable acceptance.
4. If "ranked commercial actions" retains product value, keep a *slimmed, re-chartered* node with non-rejected language, decoupled from the planner, most likely `planned`.

**Acceptance criteria must state:**
- *Template:* a steward creates a tenant template by uploading an example workbook and mapping it once; the **same profile parses imports and renders exports**; export headers/order/values/date-formats come from the profile, not code (`RESELLER_HEADERS` removed); **round-trip test (export ÔåÆ re-import) diffs to zero on canonical fields.** No hard-coded template law.
- *Evidence reuse:* planner consumes listing-activation and competition evidence via the shared layer, not re-implemented; the same entities back Stock/Overview/attention; substrate-only capabilities are not shown as working analytics; **no fabricated uplift/elasticity/causality/impact/confidence** (truth 5).
- *Canonical invariant:* `cpor_case`/line is the single source; plan and settlement are lifecycle stages of one row in one domain.

(FLAG for operator ÔÇö I do not write the ledger.)

---

## Q6 ÔÇö Names

**Case-lifecycle domain (Q1-A):**
- **"Promotions & Funding"** Ô£à *(pick)* ÔÇö highest scent for the full authorÔåÆsettle lifecycle; an unfamiliar operator reads it correctly.
- "Trade Promotions" ÔÇö the real industry term (TPM); runner-up if you want vocabulary an experienced channel operator already knows.
- "Promotions" ÔÇö simplest but hides the settlement end; finance users may not find settlement.

**Evidence domain (Q2-B):**
- **"Market & Listings"** Ô£à *(pick)* ÔÇö recognizable, covers listings + competitor prices, room to grow, doesn't overclaim.
- "Listings & Competition" ÔÇö most literal.
- "Market Intelligence" ÔÇö avoid: "intelligence" overclaims given substrate status.

**"Commercial inputs" ÔÇö remove.** "Inputs" is internal jargon with poor scent. Its contents redistribute cleanly: planner/case ÔåÆ Promotions & Funding; evidence ÔåÆ Market & Listings; masters/profiles ÔåÆ Data & Stewardship. Nothing is left to justify the bucket.

---

## Recommended architecture (summary)

Treat `cpor_case` as one entity with a lifecycle and give it **one home ÔÇö "Promotions & Funding," replacing "Funding & Settlement"** ÔÇö with a composed overview ÔåÆ case book ÔåÆ a case context panel whose tabs follow the lifecycle (Author/Plan for KAMs in draftÔåÆproposed; Evidence, Claims, Payments, Settlement for finance in endedÔåÆsettled). The shipped B4 planner becomes the authoring surface of a draft case, gaining a from-scratch entry and entity pickers. Move the reusable evidence ÔÇö listing registry/observations/intelligence and competitor mapping/prices ÔÇö into a separate **"Market & Listings"** domain that the planner, Stock, Overview, and attention link *into*, never burying it under one consumer. Make the promotion-plan template **one per-tenant bidirectional (direction-aware) profile**, learned once through the existing import-mapping panel and used for both parse and render, killing the frozen `RESELLER_HEADERS` tuple while keeping the `cpor_case`/line model strictly canonical. Adopt a **four-state honest vocabulary** (live / partial / substrate / planned) with only live+partial in the rail and all four in the directory. In the programme, **retire N-0010's rejected framing** and charter new nodes for the case-lifecycle surface, the market-evidence surface, and the bidirectional template, with ACs mandating map-once templates, a round-trip test, evidence reuse, and no fabricated metrics.

## Top three risks

1. **Persona collision in one domain** ÔÇö bundling everyday KAM authoring with finance settlement risks burying one under the other (this is the strongest counter to Q1-A). *Mitigate:* role-aware default landing, lifecycle-stage filter on the case book, command-palette shortcuts.
2. **Bidirectional-template over-reach** ÔÇö one profile that must leniently parse messy historical workbooks *and* precisely render customer-exact exports can fail at one end (value-map inversion ambiguity, export-only computed columns, date/format fidelity). *Mitigate:* direction-scoped required/optional flags, a designated emit value per enum, and the round-trip test as a hard gate (ship B linked-by-code first only if you accept, and monitor, drift risk).
3. **Rail inflation / honest-status drift** ÔÇö standing up "Market & Listings" for a currently-thin capability (substrate-only competition, partial listings) can overstate maturity ÔÇö the exact `competitor_price_import: ready` lie. *Mitigate:* start it as a single composed page, enforce the four-state vocabulary in both rail and directory, and never link substrate/planned sub-areas from the rail.
