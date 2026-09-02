# N-0013 r3 — Operator summary (≈5 minutes)

Branch `feat/ns-2-brief-nav-collapse` · 2026-09-02 · Fable 5.1 in Cursor · run `NS_REDESIGN_R3_20260902`

## Look at this first

Run `pnpm dev:web` and open **http://localhost:3000/design-lab**. It is an interactive React prototype inside
the real `apps/web` (Next 15 · MUI 6 theme · AG Grid · Recharts), on fixture data, calling no API, isolated in
the `(design-lab)` route group. Production routes are untouched. If you cannot run it, the 34 screenshots in
`renders/proto/` (1280×800 and 390×844) are the same surfaces; `rendered-verification.md` maps each claim to
a file.

Walk: Overview → click a figure → Stock & Sell-through › Cover → click a row (context panel) → Funding ›
Case book → open a case → Approve → Data & Stewardship › Steward queue → open a token → Reports → switch metric →
Save & pin → ⌘K "cover" → footer "What CIP does". Then narrow the window to phone width and repeat Overview,
Funding and the bell.

## What changed structurally (not labels)

| Rejected | Proposed |
|---|---|
| Six process-stage containers (Brief · Plan · Position · Settlement · Actions · Imports) | **Capability domains the data layer actually owns:** Overview · Stock & Sell-through · Supply & Inbound · Planning · Funding & Settlement · Commercial inputs · Data & Stewardship · Administration (admin only) |
| Landing = Brief text rows, dashboard elsewhere | Landing = **composed Overview**: configurable **Business dashboard** (governed metrics, per-role seed, edit/add/publish) beside **Needs attention** (live signals with counts) and pinned reports — business view and operational work visibly distinct |
| Dashboards as a saved-report destination | Dashboards and Reports are **siblings**; a saved report pins as a widget; Reports is a governed builder (metric catalogue with not-runnable metrics disabled) |
| Routes as folders | Every domain page **composes** headline figures · its attention items · analysis · workflow links |
| No drill-down | **Entity/case context panel** on every figure and grid row; grid state preserved behind it |
| Findability by memorising the rail | **Command palette** (⌘K) + **capability directory** ("What CIP does": 8 areas · 47 workflows, one line each on what it computes) |
| Empty scaffolds given equal weight | **Data-gated leaves**: Competition / Roadmap / Budgets listed as "not yet populated", hidden from the rail |
| Generic "open on desktop" | Mobile: bottom nav + full drawer; **record cards** for decision/lookup grids (funding approvals, breaches, import jobs); attention-first via the bell; dense authoring grids keep a frozen first column |

The domain count (8) is an output of the capability audit, not a target. Nothing shown is a number CIP
cannot compute today — no uplift, elasticity, confidence % or financial impact appears (Commercial shows
observed prices and imported plan lines only; the uplift figure renders "—").

## Why r2 failed (evidence in `FAULT_FINDINGS.md`)

1. **Artifact class.** "High fidelity" became standalone HTML/CSS that re-drew the app; the verifier inspected
   those files, not the React product. The r1 mobile PASS and the `:focus-visible` claim were both possible
   only because nothing rendered the real stack.
2. **Design language v1.1** was read as a ceiling: single-accent, "figures not decoration", 9.5px strips and
   minimal panels combined into a sparse console. Shipped surfaces (steward engine, lineup) already exceed it.
   Recommendation: demote v1.1 to reference; author v2 from the prototype primitives.
3. **EIF independence was a string comparison.** The same script emitted implementation and "gov-008"
   verification events in one process; independence is only enforced at `complete`, so PASS was visible before
   any check; the decision model cannot say "rejected"; preservation checks nouns, not product quality; the
   framework was modified during the run it governed. Nine concrete remedies are in `EIF_REMEDIES_PROPOSAL.md`
   (EIF repo, separate session, **after** this evidence is committed). None applied here.
4. **The reconciliation inferred "no reusable UI" from "not in packages/ui".** False: `PageHeader` (45 uses),
   `EnterpriseDataGrid` (37), `ModuleDataSection` (28) and the 33-file steward engine are the reusable layer.
   That error made Phase B look like greenfield component work; it is consolidation of duplicates (4 scope
   bars, 3 regime strips, ad-hoc panels/charts) plus two genuinely new primitives (context panel, palette).

## Process

Discovery from source (`PRODUCT_CAPABILITY_AUDIT.md`, `COMPONENT_ECOSYSTEM_AUDIT.md`) → three materially
different concepts (`CONCEPTS.md`: capability domains · entity workbench · home/work/explore) → CONSULT with a
**different model in a separate process** (`claude -p --model opus`; neutral seed, no preferred answer) →
recommendation H (domains + composed overview + entity drill + palette) with explicit gates → prototype built
to those gates → rendered.

## Independence achieved (honest)

- IA choice: **other model, other process** (CONSULT). Real separation.
- Rendered claims: **author-rendered only.** Every row in `rendered-verification.md` is UNVERIFIED; the
  programme records `authored_unverified`, not PASS. A separate GOV-008 session (other model) is required to
  turn any of them into PASS.

## Programme state (rev 254, `verify` ok)

- D-0001, D-0003 superseded by operator rejections D-0004/D-0005; D-0002 deferred (D-0006); **D-0007 proposed**
  (this direction). N-0013 `blocked` on operator acceptance; N-0010/N-0011 blocked; Phase A not started.
- N-0004–N-0009, N-0012 untouched. N-0006 ledger hygiene untouched.

## Your decisions (only these)

1. **Accept D-0007 (direction H) as the N-0013 design package?** Yes → scope Phase A from `DIRECTION.md` §7
   dispositions. No → name the surfaces that fail and why.
2. **D-0002 — mapping/resolution.** Proposed shape: per-job stewarding stays *and* the cross-job Steward queue
   becomes a first-class leaf + Brief signal (both reachable). Accept that shape, or keep it deferred?
3. **Design language.** Demote `CIP_DESIGN_LANGUAGE.md v1.1` to reference and author v2 from the prototype, or
   keep v1.1 authoritative with amendments?
4. **Viewer role and Data & Stewardship.** Prototype shows the domain to viewers with read-only masters
   (Import Center / Steward queue / audit hidden). Keep, or hide the domain entirely for viewers?
5. **EIF remedies.** Authorise a separate EIF-repo session to apply R-1…R-9 (or a subset)?

Everything else in this run was resolved without you.

---

## r3.1 amendment — commercial capability (2026-09-02, later the same day)

Your correction: the Promotion Planner is a real plan-authoring workflow; website/listing evidence is broader
than a price table; competition is product ↔ product; and "computes nothing → hide" is not an architecture
rule. Full detail in `commercial/COMMERCIAL_DIRECTION.md`; source evidence in `commercial/CAPABILITY_ACCOUNTING.md`.

**What the source said.** The promotion plan *is* the CPOR case (`cpor_case` / `cpor_case_line`) — the same row
r3 filed under Funding & Settlement as a money record. The B4 planner is partly shipped (proposes lines, edits
them, exports a frozen 32-column XLSX). Listing capture is implemented (registry, scheduled observations,
activation check against the case-line SRP, drift, worklist). Competition has a working approve/reject workflow
over seed-only rows, a candidate scorer nobody calls, and an empty competitor-price table that `market.py`
claims is "ready". r3's "promotion_plan lines" and "price_observations" were fixture names for tables that do
not exist.

**What changed (D-0007 → D-0008, proposed).** Funding & Settlement becomes **Promotions & Funding** and owns the
whole lifecycle: Promotion planner · Case book · Claims · Payments · **Plan templates** · Terms · Budget ledger.
**Commercial inputs is removed.** A new evidence domain **Market & Listings** holds monitored listings, price
history, promotion activation, feed proposals, competitor mappings / prices / listings and listing quality —
each labelled **live / partly built / data only / planned** (the binary data-gating rule is withdrawn). Export
becomes a per-customer **template profile** learned once from an example workbook through the production
`CanonicalColumnMappingPanel` and used for both import and export (retiring the hard-coded tuple). CONSULT
(opus, separate process) agreed on placement, domain, template architecture, vocabulary and naming.

**Look at this.** `/design-lab/funding?lens=planner` → open **CPR-26-1204** → edit *Est. units* in the grid (the
waterfall figures recompute) → click the product cell (evidence panel: waterfall, cost tier ladder, quantity,
market) → **Export** (template-driven dialog) → *Plan templates* (real mapping panel; OfficeWorld shows a
blocking unmapped required field) → `/design-lab/market` (shelf price vs case SRP; activation; competitor
mappings with factor breakdown; "data only" and "planned" lenses that show nothing pretending). 27 new
screenshots in `commercial/renders/`, all author-rendered (UNVERIFIED).

**N-0010.** It is the "Actions container", not the planner; its ACs cite rejected design language. D-0009
(proposed) retires that framing and charters, after D-0008, three nodes: Promotions & Funding surface, Market &
Listings surface, promotion-plan template profile. Nothing was chartered by this run.

**Your additional decisions.**
6. Accept **D-0008** (D-0007 + commercial delta) in place of D-0007?
7. **N-0010 disposition (D-0009)** — retire and split as proposed? Does "ranked commercial actions" survive as a slim planned node?
8. **Template profile increment** — one direction-aware bidirectional profile (recommended) vs import + export profiles linked by code (faster, drift risk)?
9. Minor: **Plan templates** live in Promotions & Funding (as prototyped) or Data & Stewardship (CONSULT's pick)?
