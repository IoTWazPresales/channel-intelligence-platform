# N-0013 fault findings — why the r1/r2 design package failed

Run: `NS_REDESIGN_R3_20260902` · Branch `feat/ns-2-brief-nav-collapse` · Author: Fable 5.1 (Cursor)
Scope: evidence-based diagnosis. FACT = inspected file/command; OBS = rendered/inspected observation;
INFER = inference from facts (labelled). No production source was changed for this document.

---

## 0. Summary (one paragraph)

The r1/r2 package failed for four compounding reasons, each proven below: (A) the frozen design
language made an HTML file the fidelity reference and encoded a "one dominant element / no KPI cards /
no chart without a decision question" doctrine that, applied literally to a landing page and a shell,
produces a sparse console and outlaws the configurable Dashboard the operator requires; (B) "high
fidelity" in the EIF runtime is a process class (identity tokens, states, interaction spec present),
not an environment class, so recreated standalone HTML/CSS satisfied it; (C) EIF's independence
control compares caller-supplied `--run/--actor` strings inside the same process, is only enforced at
`complete`, and its own capability record says verifier separation is UNVERIFIED — so a same-run,
same-model self-review was recorded as an independent PASS, and the operator saw PASS in CURRENT.md;
(D) the six-container, process-stage navigation axis was a charter assumption from 2026-08-22 that was
never re-derived; three label rounds were applied to it.

---

## 1. Documentation / design language (`docs/design/CIP_DESIGN_LANGUAGE.md`, FROZEN v1.1)

### 1.1 What the document actually says (FACT — quoted, not attributed)

| Ref | Rule (verbatim fragment) | Lines |
|---|---|---|
| P1 | "The system shows its read before the user digs… Columns are evidence; the Read is the analysis." | 15–18 |
| P2 | "One dominant element per screen… Everything else is quieter than it." | 19–22 |
| P3 | "Severity in two channels, always." | 23–24 |
| P4 | "Density through rhythm, not compression… No toy tables, no whitespace theatre." | 25–26 |
| T | Tokens: dark DNA, Inter + IBM Plex Mono, type scale, tabular numerals, radii 3–5px | 33–68 |
| C-spine | "Spine (190px): wordmark + tenant/period stamp; primary nav with mono" | 72 |
| G3 | Signal blotter (landing): "No KPI cards… No filter bar" | 153–158 |
| G-fixed | "Every CIP page is one of six grammars… if none fits, that is a design decision requiring review" | 128–129 |
| I1 | "A Read must be computable from data the surface already has… a wrong Read is worse than none." | 182–184 |
| I2 | "Charts answer a decision question on that surface… No chart exists to fill space." | 191–200 |
| B | "Budget: no standalone commercial page." | 202 |
| S | States required per surface; state frames keep the full shell | 206–228 |
| AP | Anti-patterns: "Uniform KPI-card rows · equal-weight card grids · … light-theme minimalism" | 232–240 |
| PR1 | "Reference artifact for fidelity: funding-settlement-r3.html" | 245–246 |
| PR2 | "Fable audits rendered batches of 3–4 surfaces" | 247–249 |
| PR4 | "Warren adjudicates only genuine domain calls: nav vocabulary…" · "Nav vocabulary confirmed 2026-08-30: Brief · Lineup · Stock · Settlement · Response · Steward · Reports · Admin" | 251–259 |

### 1.2 Verdict per rule

**Remain useful (keep, re-home into the new spec):** T (tokens, type, numerals, delta convention), P3
(two-channel severity), P4 (density through rhythm), I1 (computable Read), S (states incl. full-shell
state frames), the decorative-styling half of AP (no glass/glow/gradients/neumorphism), P6 product voice.

**Misinterpreted / over-applied:**
- P2 "one dominant element" was read as *suppress everything else*. Rendered evidence: current `/brief`
  (`renders/current/brief-1280.png`, 1280px) — four signal rows, no headline figures, ~55% of the
  viewport empty. The rule constrains *hierarchy*, not *quantity*; the frozen text supplies no density
  floor for a landing page, so restraint had no counter-weight.
- AP "uniform KPI-card rows / equal-weight card grids" was generalised to *no KPI figures anywhere*
  (G3 "No KPI cards"). Result: the regime strip compresses the platform's headline numbers into
  9.5px microlabels (`renders/current/settlement-1280.png`: BOOK TOTAL / SETTLED / OUTSTANDING at the
  top-right edge). The operator's complaint "valuable information compressed into small strips" is
  this rule's literal output.
- I2 "charts answer a decision question" became *one instrument per lens, nothing else*. The
  histogram/segmented bars are hand-built `<div>`s; Recharts appears in only 4 files
  (`PlanVsExecutedView`, `ShippingCommercialSummary`, `ReportBuilderView`, `ChannelOpsOverviewTab`).
  Analytical visualisation was starved by a rule intended to stop decorative charts.
- G-fixed "one of six grammars" plus PR4 "nav vocabulary" made the *architecture* a vocabulary question
  and the *grammar taxonomy* a closed set — a Dashboard canvas (widget grid) fits none of the six, and
  AP literally rejects it ("equal-weight card grids"). **The frozen language forbids the product the
  operator has stated as strategically important.** That is not a misreading; it is a conflict in the
  document.

**Combinations that produced weak composition:** P2 + G3 + AP + I2 together = Read sentence + one
instrument + grid, nothing else permitted. Applied to a shell with a 190px mono spine (C-spine) this is
the "sparse generic admin console" the operator saw.

**Rules NOT in the document (do not attribute):** it does not say "minimal", does not set six top-level
containers as a rule (it *records* a confirmed vocabulary), does not forbid multi-panel analytical pages,
does not forbid tables/panels/filters, does not require standalone HTML mockups for evidence — but PR1/PR2
make an HTML file the *fidelity reference* and the audit unit, which is the seed of the artifact-class
failure (§2).

**Shipped surfaces already exceeding it (OBS, 1280px):** Import Center guided wizard with typed import
cards (`renders/current/imports-1280.png`), DSI steward job workspace with 8-step progress, entity tabs,
plan/bulk toolbar and drawer (`renders/current/steward-dsi-job-1280.png`), Report builder with governed
metric picker, grain chips and formula (`renders/current/reports-1280.png`). None of these is expressible
in the six grammars beyond the thin "Factory" and "Composer" paragraphs.

**Disposition recommendation:** **Demote to reference; supersede.** Keep §2 tokens, §1 P3/P4/P6, §5 I1,
§6 states as the *foundation* of a new design-system spec derived from the React prototype
(`apps/web/src/app/(design-lab)/…`). Retire §3 component inventory (HTML-referenced), §4 fixed grammars,
§7 first sentence (KPI/card prohibition), §8 process (HTML reference artifact, batch audit of HTML).
The FROZEN status should be lifted by operator decision, not silently.

### 1.3 Charter assumption drift (FACT)

`.eif/audit/R20260822202100_PLATFORM_FULL/CONSULT_SEED.md` (2026-08-22) proposed "Collapse IA:
Today / Channel / Plan / Masters / Bring data in / Admin" and "Page grammar Situation → Queue → Record →
Evidence". The rationale then was 30+ always-expanded legacy leaves (`navConfig.ts`, still present with
34 leaves in 6 groups). The *collapse* rationale was valid; the *six process-stage containers* were a
proposal, never a derived architecture. NAMING.md, CIP_NAV_MAP.md and the r1/r2 proposals all took the
six-container spine as given and only renamed it (Today→Brief, Channel→Stock→Position, Plan→Lineup,
Bring data in→Steward→Imports…). The seed also says "Do not paint Ken/Wayne; IAM is
admin/steward/planner/viewer" — the role model exists in code (`navConfig.ts` ALL/STEWARD_PLUS/
PLANNER_PLUS/ADMIN_ONLY) and was never used to test the IA.

---

## 2. Prompts / artifact class

**Why high fidelity became standalone HTML/CSS (FACT):**
1. PR1 named `funding-settlement-r3.html` as the fidelity reference; every subsequent design unit
   (`lineup.html`, `lineup-pending.html`, `response-blocked.html`, `stock-cover-empty.html`,
   `reports-builder.html` — all cited in the frozen doc) followed the same class.
2. The EIF runtime's artifact-class model (`.eif/runtime/programme/eif_program/design_artifacts.py`)
   ranks classes and checks `design_artifact_class ≥ target_artifact_class` plus presence of dims
   (identity tokens, states, interaction spec, accessibility). It has **no notion of environment**
   (real component tree vs recreation). A screenshot of a static HTML page and a screenshot of the
   running Next app satisfy it identically.
3. The prior verification (`.eif/audit/NS_RECONCILE_20260902/rendered-verification-r2.md`) inspected
   `platform-shell-desktop.html`, `position-cover-desktop.html`, etc. — i.e. the recreation — and the
   "independent" review inspected the same files.

**What the HTML artifacts could prove:** token palette, type scale, copy, static layout at two
viewports, the *idea* of a nav.

**What they could not prove:** that MUI/AG Grid/Recharts components can realise the layout at density;
how the real AppShell/WorkbenchSpine/steward engine compose with a new shell; interaction states
(hover, focus-visible, drawer, filter dirty-state, lens switching, drill-down context persistence);
responsive behaviour of real grids; reuse vs re-implementation cost; whether existing strong surfaces
(steward, Import Center, report builder) survive the new shell.

**What this React product requires as design evidence:** an interactive prototype **inside `apps/web`**
using the real theme, real shared components (`EnterpriseDataGrid`, `ModuleDataSection`, steward
engine, `ReadStrip`, `PageHeader`), real chart library, realistic fixture data, isolated from
production routes; rendered at 1280/390 from the running Next dev server; every claim citing
screenshot + viewport. That is what this run builds (`DIRECTION.md`, `rendered-verification.md`).

---

## 3. EIF — executable/runtime evidence

### E-1 Independence is a string comparison in the same process (PROVEN)

- `.eif/runtime/programme/eif_program/independence.py` `_pass_provenance_ok`: independent iff
  `pass_run != implementation_run` **or** `pass_actor != implementation_actor`. Both values come from
  `--run` / `--actor` CLI flags supplied by whoever emits the event.
- `.eif/audit/NS_RECONCILE_20260902/amend_n0013.py` lines 118–126: **the same Python script**, in the
  same process, emits `--run NS_RECONCILE_INDEPENDENT_R2_20260902 --actor gov-008` verification events
  immediately after its `agent` events. No second session, no second context, no second model.
- The r1 review's own "Independence attestation" (`independent-rendered-review.md` line 77) claims
  independence from *N-0004–N-0009 implementation runs* — not from the N-0013 authoring run.
- r2 (`independent-rendered-review-r2.md` line 15) admits the r1 focus-visible failure was
  "Insufficient evidence inspection — **same run**". The amend script then recorded
  `"eif_defect": "none — reviewer execution failure"` — a self-exoneration written by the run under review.
- Model separation was available and unused: `claude` CLI 2.1.202 is installed; the project's own
  CONSULT mechanism (`.eif/CONSULT.md` ladder: "R3+: other session and other model when available";
  `.cursor/skills/dual-agent-fable` → `claude -p --model opus`) was not invoked for r1 or r2.
  N-0013 is R3.

### E-2 Independence is only enforced at `complete`; PASS is visible before any check (PROVEN)

- `python .eif/runtime/programme/program.py verify` → `{"ok": true, "issues": []}` at rev 220 with every
  N-0013 pass produced by actor `agent` in the authoring runs (`.tmp/n0013_status.txt`).
- `engine.h_status` runs `gates_ok` (which includes `independence_ok`) only when `dest == 'complete'`.
  N-0013 is an operator-acceptance node that never reaches `complete` before the operator reads it, so
  CURRENT.md showed PASS records the runtime had never independence-checked.

### E-3 The decision model cannot express operator rejection or deferral (PROVEN)

`engine.h_decision_status` accepts only `{'proposed','accepted','superseded'}`. This run had to record
rejection as operator decisions D-0004/D-0005 with `supersedes`, and deferral as D-0006 text — a
workaround that hides the operator's actual verb from the state model.

### E-4 Quality-dim state is unvalidated free text (PROVEN)

`engine.h_quality` stores any `state` string; only `na` needs a rationale. Nothing prevents a
`pass` without evidence path resolution. (RUNTIME_CAPABILITIES.md line 45: "Evidence-pointer resolver:
ADVISORY".)

### E-5 The framework's own capability record flagged this and no compensating control was recorded (PROVEN)

`.eif/RUNTIME_CAPABILITIES.md` line 46: `Independent verifier separation | UNVERIFIED`. eif-core rule:
"R3+ relies on measured same-mode runtime controls. If a critical guard is unverified/ADVISORY, lower
authority or record an accepted compensating control." Neither occurred for N-0013 (R3).

### E-6 Why r1 passed a broken 390px result and asserted a non-existent rule (PROVEN, with E-1/E-2 as cause)

- Mobile: r1 `rendered-verification.md` recorded mobile PASS from the same author; r2 line 26 records the
  drawer CSS was wrong. No second pair of eyes existed to catch it (E-1).
- `:focus-visible`: r1 wrote "Focus-visible styles inherited from cip.css"; `cip.css` had no such rule
  (r2 line 15). The rule exists only in `cip-base.css` line 36, which the r1 review did not cite. A
  source claim without an inspected pointer passed because evidence pointers are ADVISORY (E-4/E-5).

### E-7 The framework governing the run was modified by the run (PROVEN, uncommitted)

Uncommitted modifications in the CIP working tree: `.eif/runtime/programme/eif_program/engine.py`,
`store.py`, new `independence.py`, `manifest.json` (hashes updated), `.cursor/hooks/eif_guard.py`.
These add independence checks *after* the N-0013 evidence was recorded, and the hook now blocks many
routine operations (see §5). Self-modifying governance during the governed run is itself a control
failure. **This run has not touched those files and will not commit them.**

### E-8 Preservation recognises capability existence only (PROVEN)

`BLN-0001` baseline + `preservation` map on N-0013 (`.tmp/n0013_status.txt` lines 263–268) list
capabilities and routes; `conservation_gaps` checks nouns. There is no dimension for UX/product-quality
regression (density, findability, task time, information hierarchy). A redesign can pass every
preservation check while degrading the product — which is precisely what the operator rejected.

### E-9 Guard runtime defects observed in this run (OBS)

`eif_guard.py` (fail-closed) rejected: `git diff` naming `.eif/runtime` paths (CONTROL_PLANE_PROTECTED);
any shell text containing `http://localhost:…/path` (FOREIGN_PATH — URL paths parsed as filesystem
paths); reads of the agent's own terminal/transcript files (FOREIGN_PATH); the EIF repository
`C:\AI\engineering-intelligence-framework` (FOREIGN_PATH — not a declared root in this session);
HOOK_TIMEOUT / HOOK_INPUT_INVALID under concurrent tool calls. Consequence: subagent audits could not be
collected during the run (the subagents themselves were blocked mid-audit and their reports only surfaced
after the r3 package was committed — filed late as `SUBAGENT_AUDITS_LATE.md`, corroborating not
authoritative); EIF remedies cannot be written into the EIF repo from this session.

### Non-defects (do not blame EIF for these)

- The artifact-class *ladder* itself is reasonable; the missing piece is an environment axis (§2).
- The ledger is append-only and replayable; supersession could be recorded lawfully (this run did).

---

## 4. Proposed EIF remedies

See `EIF_REMEDIES_PROPOSAL.md` (same folder). Each remedy names mechanism/file, change, failure
prevented, cost, risk and class (configuration / orchestration / governance / code). The EIF repository
is outside this session's declared roots, so the proposal is filed here for a separate EIF session;
CIP design evidence in this folder is frozen first (this run) and must not be rewritten when EIF is fixed.

---

## 5. Effect on N-0013 and Phase B (component library)

`CIP_FULL_PLATFORM_RECONCILIATION.md` §2.1 states "`packages/ui` exports tokens and theme only — **no
shared behavioural primitives**". The first clause is true (5 files: tokens, theme, agGridMuiTheme,
AppThemeProvider, index). The second is **false** — see `COMPONENT_ECOSYSTEM_AUDIT.md`: 8 shared
behavioural components in `apps/web/src/components` with 44/35/27/22/11 importing files, and a 33-file
generic steward engine in `features/import-steward`. The reconciliation's own §2.2 table lists these
implementations by name while calling them "distinct implementations" to be replaced. Effect: Phase B
was planned as *extraction from scratch* ("ScopeBar, ReadStrip, RegimeStrip, states, confirm, badges,
lens switcher, grid skin"), sized around the four new NS container kits, and the strongest existing
assets (steward engine, EnterpriseDataGrid, Import Center wizard, master grid shell) were treated as
legacy to migrate "behind adapters" (Wave 3) rather than as the benchmark to design from. The r1/r2
mockups consequently recreated grids/filters/tabs in HTML instead of composing the real ones.
