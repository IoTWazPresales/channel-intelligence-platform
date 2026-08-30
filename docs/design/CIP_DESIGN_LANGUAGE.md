# CIP Design Language v1 — "Workbench"

**STATUS: FROZEN v1.1 — 2026-08-30. Governing for implementation. Changes via
SPEC_GAPS + adjudication only.**

Status: converged with Warren over R1→R3 of the Funding settlement desk
(`funding-settlement-r3.html` is the reference artifact). This document is the
governing design spec for all CIP surfaces. Implementers build against it;
Fable audits rendered output against it in batches. Deviations require a stated
reason in the PR/prompt, not silent drift.

---

## 1. Principles

1. **The system shows its read before the user digs.** Every primary surface
   opens with a computed one-sentence analysis (the Read) and a visual shape of
   the whole population. Columns are evidence; the Read is the analysis.
2. **One dominant element per screen.** The eye must know where to land: the
   money figure on a case, the shape strip on a book, the top signal on the
   landing page. Everything else is quieter than it.
3. **Severity in two channels, always.** Color plus weight, color plus marker,
   color plus position. Never color alone.
4. **Density through rhythm, not compression.** Realistic row counts, 31–36px
   row heights, honest pagination. No toy tables, no whitespace theatre.
5. **Acting shows progress.** Counts tick down, deltas show what moved, closed
   items visibly recede. The queue rewards being worked.
6. **Product voice.** Copy names what the operator controls in operator
   vocabulary. Buttons state what happens, with the amount when money moves
   ("Record settlement · R 1,616,231.52"). No meta-commentary, no
   implementation language, no verbs-as-nav.

## 2. Tokens

Colors (existing CIP DNA — do not restyle):

    --bg:#14161a  --elev:#1a1d23  --surf:#1e2229  --surf2:#252a33
    --line:rgba(120,160,190,.16)  --line2:rgba(120,160,190,.3)
    --tx:rgba(245,247,250,.96)  --t2:rgba(186,198,210,.75)  --t3:rgba(160,176,192,.5)
    --ac:#3db8e8 (+ --ac-dim rgba(61,184,232,.13))
    --ok:#3d9b6a  --wn:#d4a15a  --st:#c45c5c  (each with .13–.14 alpha dim)
    Light-on-dark state text: ok #9dceb4 · warn #e8d4a8 · stop #e8b4b4 · money-at-risk #e8c4b4

Color discipline: cyan = interactive + intelligence (Read tags, selection,
primary actions). ok/wn/st = state only, never decoration. No gradients as
identity, no glow, no glass, no neumorphic shadows.

Type: Inter (UI) + IBM Plex Mono (every numeral, code, ID, timestamp).
Scale (the hierarchy engine — do not flatten):

    34px mono 500   dominant money/quantity figure (one per screen max)
    21px 650        record title (case/customer/SKU heading)
    15px mono       secondary measures
    13px 500        nav, working UI
    12–12.5px       body, grid cells
    11px            provenance, footnotes
    9.5–10px caps   microlabels, letter-spacing .07–.1em

Numerals: `font-variant-numeric: tabular-nums lining-nums` everywhere.
Money right-aligned, decimals aligned, currency symbol dimmed (`--t3`) before
the figure. Radii 3–5px. Hairline borders from --line/--line2 only.

**Delta convention** *(folded from SPEC_GAPS, 2026-08-30)*: valence in color
(good = `--ok` / `#9dceb4`, bad = `--st` / `#e8b4b4`), direction in the glyph
(▲ rise · ▼ fall). Color and glyph are independent — a red ▲ means
rising-and-bad (e.g. pairs under 4w tick up). Neutral movement uses `--t3` and
`—`. Regime-strip and grid Δ captions use the form `▲ n this wk` / `▼ n this
wk` (unit suffix after the figure when needed: `0.4w`, `1.2 pt`, `R 213,410`).

## 3. Component inventory (reference: funding-settlement-r3.html)

- **Spine** (190px): wordmark + tenant/period stamp; primary nav with mono
  count per item (red count = attention); util nav (Reports, Admin) below a
  rule; session identity at bottom. No numbered markers (01/02) — counts carry
  information, numbering does not.
- **Top strip**: breadcrumb left; **regime numbers** right (2–4 headline
  figures for the surface, with weekly deltas where computable).
- **Filter bar** (sticky, structural — the shipped PvE interaction): From /
  To / BU + surface-specific selects, Apply (primary), Reset, and a
  **saved-view control** right-aligned. Identical placement on every grammar-1
  and grammar-2 surface; **grammar-3 Brief is exempt** *(folded from batch-1
  audit, 2026-08-30)* — period comes from the tenant stamp, not a filter bar.
  **Drill views are additive** *(folded from batch-1 audit, 2026-08-30)*:
  From / To / BU and saved view always remain; record-specific fields
  (Delivery, Distributor, Case, etc.) are added alongside — never replace
  the invariant trio.
- **Nav badge count** *(folded from batch-1 audit, 2026-08-30)*: equals the
  on-surface row count for that container (Brief signal rows, Stock under-4w
  pairs, Settlement open cases, etc.) — not a deduped theme count.
- **Read strip**: `READ` mono tag (cyan, bordered) + one computed sentence
  with bolded figures. Book-level Reads pair with a population shape.
- **Shape bars**: segmented population bar (e.g. settled/outstanding/blocked)
  with swatch key and amounts; blocked segments hatched. Row-level variant:
  5px settled-vs-outstanding bar; blocked rows show a broken (dashed) bar.
- **Concentration list**: top-N proportional bars with name + amount, first
  row emphasized. Use wherever "most of X sits in few Y" is decision-relevant.
- **Histogram instrument** *(folded from SPEC_GAPS GAP-001, 2026-08-30;
  built in `stock-cover.html`)*: WOC-bucket columns with state fills
  (`--ok` / `--wn` / `--st` — no gradient-as-identity); book **mean** as an
  11px provenance caption on the tail bucket; **selected range** as a 2px
  underline in the state color (color + position — two channels); **metric
  switcher** is the lens control on the instrument panel (see §5), not a
  second lens row. Class name (`.tabs`, `.switch`, etc.) is **not normative**
  *(folded from batch-1 audit, 2026-08-30)* — behavior and placement are.
- **Data grid**: sticky uppercase 9.5px headers; 36px rows; hover; selected
  row = --ac-dim fill + 2px inset cyan edge; settled/closed rows recede to
  --t3; badges inline after the name (blocked/flag/settled); Δ-week column
  where movement matters; footer states range, counts by state, and sort.
- **Case/record pane**: eyebrow (mono caps: ID · period · type · status) →
  21px title → kicker metadata → **anchor panel** (raised --surf card holding
  the dominant figure + its basis line) with a fixed-purpose micro-viz
  alongside → readiness row → Read → measures row (label/value/bullet/note) →
  tabs with counts → lines table with tfoot totals → provenance line →
  action bar (rule text left, actions right).
- **Readiness row**: pre-flight checks as chips (pass ✓ green / open n amber /
  fail 0 red) before any consequential action.
- **Suggested action**: small cyan `SUGGESTED` hint on the next-best action.
  Exactly one per surface, only when the system can genuinely rank it.
  **Rendered uppercase via CSS** on the `.hint` class *(folded from batch-2
  audit, 2026-08-30)* — markup casing (`Suggested` vs `SUGGESTED`) is not
  normative.
- **Buttons**: secondary = surf + hairline; primary = cyan-dim fill, amount
  included when money moves. Destructive/consequential actions always route
  through preview/confirm surfaces (existing safety culture made visible).

## 4. Surface grammars

Every CIP page is one of five grammars. New pages must declare which one they
use; if none fits, that is a design decision requiring review, not improv.

1. **Queue + case** (split 56/44, queue persists, case opens in place):
   Funding settlement book · steward worklists · assumptions · any
   work-through-a-list surface.
2. **Instrument + grid**: population instrument (histogram / trend panel with
   metric switcher / shape strip) above a dense filtered grid. Channel cover,
   sell-out, movements, execution, **shipping/inbound**. For shipping: regime =
   pipeline units / not-received / **Pipeline fill %**; instrument = inbound
   landing by week vs ETA; grid = delivery lines with state bands
   (shipped/short/over/unshipped) as badges; Δ column = landed this week;
   Read = e.g. "1,713 lines not received; 62% of open units sit with two
   distributors." **Lens-scoped metric names** *(folded from batch-1 audit,
   2026-08-30)*: **Fill vs plan** (Cover / Execution lenses) and **Pipeline
   fill %** (Inbound lens) — never bare "Fill %". **Not received** grain =
   open inbound lines with outstanding quantity; partial unit receipt does not
   reduce the line count (see `docs/design/PACKET_DATA.md`).
   **Lineup ownership affordances** *(folded from SPEC_GAPS GAP-013,
   2026-08-30)*: Lineup is plan origination on grammar 2 — pending rows carry
   **Approve / Reject** row actions; the **Planned** column shows an inline-edit
   cue (dashed underline + edit glyph on hover); a **plan action bar** below the
   grid states net requirement and offers **Calc · Export · Apply**. Decided rows
   keep approval badges only (no row actions). Reference: `lineup.html`,
   `lineup-pending.html`.
3. **Signal blotter** (landing page): ranked full-width signal rows — severity
   tick, one-line signal with figures, age/count, single next action. No KPI
   cards. Read at top ("what changed since yesterday"). **No filter bar**
   *(folded from batch-1 audit, 2026-08-30)* — period from tenant stamp only.
4. **Ranked actions + calculator** (Planner/Decide grammar): action list left
   (do-nothing is a first-class action), fixed-purpose calculator right,
   drafts clearly marked as drafts ("does not write a PO").
5. **Factory** (Imports): jobs grid with state, failure reasons in product
   voice, retry/archive actions, steward entry points. Same grid rules.

## 5. Intelligence signatures — rules of use

The signatures are: Read · shape bars · concentration list · Δ columns ·
readiness checks · suggested action · fixed-purpose micro-viz (sparkline,
bullet). Two hard rules:

- **A Read must be computable from data the surface already has.** Run-rate,
  concentration, attribution (evidence-vs-performance), staleness. If the
  sentence can be wrong or vague, omit it — a wrong Read is worse than none.
  **Brief Read is federated by design** *(folded from batch-1 audit,
  2026-08-30)*: every figure in the Brief Read must trace to a listed signal
  row or a documented book delta in `docs/design/PACKET_DATA.md`. **Concentration
  Reads** *(folded from batch-1 audit, 2026-08-30)*: state one basis (units,
  lines, or value) and the grid footer must restate the same basis — else omit.
- **Charts answer a decision question on that surface.** The instrument
  switcher is **one control** — the **lens control** on grammar-2 position
  surfaces. Switcher labels follow the confirmed nav vocabulary for Stock
  lenses: Sell-out · Fill vs plan · Cover · Inbound *(folded from SPEC_GAPS
  GAP-004, 2026-08-30)*. Visual form may change per lens when the decision
  question differs — **form follows the question, never decoration**
  *(folded from SPEC_GAPS GAP-002 option a, 2026-08-30)*: **Cover** uses a
  distribution histogram (mean-vs-tail); **Sell-out**, **Fill vs plan**, and
  **Inbound** share a weekly-trend form (landing or movement by week vs plan or
  ETA). Funding's visuals stay fixed-purpose. No chart exists to fill space.

Budget: no standalone commercial page. Ceiling context on Funding (tick on the
book shape + "Budget remaining" regime figure + Read mention); buy-budget
context on Planner; budget administration in Admin.

## 6. States (required per surface)

Loading (skeleton rows in-grid, never blank screens) · empty (directive copy:
what this means and what to do — "No decisions in this filter" register) ·
error (what failed, in product voice, with retry) · blocked (reason inline,
e.g. FX undeclared) · confirmation (preview-first dialog with printed
amounts/counts, warnings for irregular conditions such as zero evidence) ·
mid-workflow (partially settled, partially received — the shape bars carry
this). Every implemented surface ships all applicable states.

**State frames keep the full shell** *(folded from batch-2 audit,
2026-08-30)*: loading, empty, blocked, and filtered-cut states render the
complete app chrome — spine with all nav containers and counts, top strip,
util nav, session block — and vary **only the work area** (skeleton rows,
directive copy, blocked panel, filtered grid). Reference:
`lineup-pending.html`, `response-blocked.html`, `stock-cover-empty.html`.

**Book-level blocked / stale on grammar 2** *(folded from SPEC_GAPS GAP-003,
2026-08-30)*: when the whole book cut is untrusted (e.g. SOH reconciliation
not run, DSI vintage stale), render an inline `.badge.blocked` on the **Read**
line — same badge component as row-level blocked — and restate the condition in
the grid footer provenance. No dedicated recon column (would add a sixth
severity channel).

## 7. Anti-patterns (reject on sight)

Uniform KPI-card rows · equal-weight card grids · pill color as sole
hierarchy · numbered nav markers · decorative command bars · toy tables ·
teleport drill-down (context must persist) · verbs or implementation words as
nav labels · meta-commentary in UI copy · charts without a decision question ·
trend-styling as identity: **no** neumorphism, glassmorphism, claymorphism,
aurora gradients, Y2K/cyberpunk, brutalism, or light-theme minimalism. The
identity is this workbench language; micro-borrowings (subtle elevation,
slight sticky-header translucency) are permitted as craft, never as a
restyle.

## 8. Process

1. Implementer (Cursor/Grok) builds surfaces against this spec, declaring the
   grammar per surface and reusing the component inventory. Reference artifact
   for fidelity: funding-settlement-r3.html.
2. Fable audits **rendered batches of 3–4 surfaces** at grammar boundaries —
   not per-iteration. Audit output: conforms / deviations with reason /
   spec-gap (something the spec should say and doesn't).
3. Spec gaps found in audit are folded back into this document (add-only,
   versioned) so the spec converges instead of the conversation repeating.
4. Warren adjudicates only genuine domain calls: nav vocabulary, which Reads
   are trustworthy, metric priorities. Taste iterations happen against this
   spec, not from scratch.

Open items owed by Warren: confirmation of which Read sentences are
computable/trustworthy in production. Nav vocabulary confirmed 2026-08-30:
Brief · Lineup · Stock · Settlement · Response · Steward · Reports · Admin
(`docs/design/NAMING.md`).
