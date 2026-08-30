# EIF work-unit declaration — CIP reference (docs only)

**Branch context:** written on `docs/eif-unit-declaration` (created from `origin/main`).  
**Session constraint:** documentation only — no programme declaration, no `PROGRAM.yaml` mutation, no unit start.

This document records **what is actually present in this repository** for declaring a material UI work unit with the `design_experience` facet and `target_artifact_class`. Where the EIF programme schema is absent, that absence is stated plainly — **no invented YAML**.

---

## 0. Sources read (and gaps)

| Path | Status in this workspace |
|------|---------------------------|
| `.eif/PROGRAM.md` | **Missing** (`Test-Path` → false) |
| `.eif/program/SCHEMA.md` | **Missing** |
| `.eif/program/facet_map.yaml` | **Missing** |
| `.eif/program/PROGRAM.yaml` | **Missing** (audit references a migrated file that is not on disk) |
| `tools/program.py` | **Missing** (referenced as the only lawful programme mutator) |
| `.eif/WORK_ITEM.md` | Present — task-mode work-item template |
| `.eif/DESIGN_EXPERIENCE_RECORD.md` | Present — per-node design-facet record template |
| `.eif/programme-brownfield.md` | Present — programme lifecycle guidance (prose, not YAML schema) |
| `.eif/JOURNEYS.yaml` | Present — journey schema for rendered evaluation |
| `.agents/skills/product-interaction-designer/references/contract.md` | Present — `target_artifact_class` acceptance-criterion syntax |
| `.agents/skills/ui-visual-design-specialist/references/contract.md` | Present — divergence / signatures / rendered comparison rules |
| `.agents/skills/premium-benchmark-reviewer/references/contract.md` | Present — CR-006 sameness challenge |
| `docs/design/CIP_DESIGN_LANGUAGE.md` | Present — **FROZEN v1.1 — 2026-08-30** |
| `docs/design/CIP_NAV_MAP.md` | Present — six job containers + utilities |
| `docs/AUTONOMOUS_BUILD_CHARTER.md` | Present — **v1.3** (amendments 1–7 applied) |
| `docs/design/CHARTER_AMENDMENTS.md` | Present — amendment 6 grammar + container rule |

**Implication:** NS-2 through NS-7 implementation can be governed by **charter contract rows + WORK_ITEM + DESIGN_EXPERIENCE_RECORD + frozen design docs** today. Full **programme-mode** node/facet YAML cannot be quoted from this repo until `program/SCHEMA.md`, `facet_map.yaml`, and `tools/program.py` exist upstream or are vendored.

---

## 1. Field names and syntax for a material UI unit

### 1.1 Two EIF modes (from repo evidence)

**Task mode** (no `.eif/program/` tree required — per `.cursor/rules/eif-core.mdc`):

> If `.eif/program/` exists, mutate state only via `python tools/program.py` … **if absent, task mode: one implicit node**, same quality/completion rules, no charter.

**Programme mode** (when `.eif/program/PROGRAM.yaml` + `tools/program.py` exist):

Brownfield guidance (`.eif/programme-brownfield.md`):

> 4. Facets on nodes that touch existing behaviour (auth, ui, …) so quality dimensions attach unrequested.

Executive orchestrator contract (GOV-001):

> In programme mode, draft workstreams, human/environment nodes, **facets**, dependencies and acceptance policy … Mutate programme state only through `python tools/program.py`.

**Observed migrated node columns** (North Star audit — the only node-field inventory in-repo):

| ID | Title | Class | Origin |
|---|---|---|---|
| N-0001 | Product/engineering outcomes | feature | markdown heading |
| N-0002 | Outcome 1 | feature | placeholder |
| N-0003 | Dependencies / decision deadlines | feature | markdown heading |

The audit does **not** document YAML keys for `facets`, `quality_dimensions`, or `target_artifact_class` on programme nodes. **`facet_map.yaml` is not in this repo** — do not invent `facets: [design_experience]` syntax here.

---

### 1.2 Task-mode work item — `.eif/WORK_ITEM.md` front matter

Quoted field names:

```yaml
---
eif: work-item
version: 0.3
status: proposed
last_updated:
owner:
review_after: work-close
project_id:
work_id:
authority:
risk_class:
mode: delivery # delivery | audit
autonomy_policy:
environment_policy:
---
```

Body sections (scope and acceptance):

- `## Objective`
- `## Business rule / product outcome`
- `## Observation scope`
- `## Implementation change scope` — use `NONE` for audit-only
- `## Artifact write scope`
- `## Acceptance criteria` — **attach `target_artifact_class` here** (see below)
- `## Required specialists`
- `## Review / verification specialists`

---

### 1.3 `target_artifact_class` — quoted syntax

From UX-002 (`.agents/skills/product-interaction-designer/references/contract.md`):

> The target is **structured per node** as an acceptance-criterion line:
>
> `target_artifact_class: ia_concept` | `interaction` | `high_fidelity`

From `.eif/DESIGN_EXPERIENCE_RECORD.md`:

> - `target_artifact_class:` ia_concept | interaction | high_fidelity
> - delivered `design_artifact_class:`

Audit envelope example (`.eif/audit/R20260830130000_FRESH_NS/DESIGN_EXPERIENCE_RECORD.md` front matter):

```yaml
---
eif: design-experience-record
version: 0.3
status: proposal
last_updated: 2026-08-30
owner: UX-003
review_after: 90d
provenance: design-direction
not_a_baseline: true
audit_id: R20260830130000_FRESH_NS
target_artifact_class: high_fidelity
implementation_change_scope: NONE
---
```

Material UI units for NS-2…NS-7 against frozen exemplars should declare:

```text
target_artifact_class: high_fidelity
```

in **both** the work-item acceptance criteria and the design-experience record front matter.

---

### 1.4 `design_experience` facet activation — quoted syntax

From `.eif/DESIGN_EXPERIENCE_RECORD.md`:

> Optional file — not a second ledger. **Programme quality dimensions on the node remain the gate.**

> ## Materiality
>
> - class: shell | redesign | module | explicit-request
> - activation: **design_experience facet** / Audit Mode material scope

There is **no** `facet_map.yaml` entry defining attachment mechanics. In practice:

1. Mark materiality `class: module` (or `redesign` for shell-scale work).
2. Set activation to `design_experience facet`.
3. Author `.eif/audit/<id>/DESIGN_EXPERIENCE_RECORD.md` (audit) or a programme-scoped record when programme tooling exists.
4. Ensure acceptance criteria name UX-002 / UX-003 / CR-006 review where `high_fidelity`.

---

### 1.5 Filled example — material UI unit (NS-3 Stock · Cover lens)

**Work-item acceptance criteria excerpt** (task mode — paste into `## Acceptance criteria`):

```markdown
- target_artifact_class: high_fidelity
- Container: Stock (CIP_NAV_MAP.md §3 — Channel position & execution)
- Grammar: 2 — Instrument + grid (CIP_DESIGN_LANGUAGE.md §4 item 2)
- Exemplars: docs/design/stock-cover.html, stock-cover-empty.html, stock-cover-loading.html
- Contract rows: [enumerate visible behaviours before build — charter v1.3]
- design_experience facet: DESIGN_EXPERIENCE_RECORD required before verify close
- Browser smoke: rendered Cover lens at operational density; Read + histogram + grid per frozen spec
- Deviations: stated in prompt/PR — no silent drift from FROZEN v1.1
```

**Design experience record — filled sections** (abbreviated; full template is `.eif/DESIGN_EXPERIENCE_RECORD.md`):

```markdown
---
eif: design-experience-record
version: 0.3
status: proposed
last_updated: 2026-08-30
owner: UX-003
review_after: 90d
provenance: design-direction
not_a_baseline: true
audit_id: <unit-id>
target_artifact_class: high_fidelity
implementation_change_scope: apps/web/...  # exact paths for delivery units
---

## Artifact class (per node)

- node id: NS-3-stock-cover
- target_artifact_class: high_fidelity
- delivered design_artifact_class: high_fidelity
- sequence note: conforms to FROZEN CIP_DESIGN_LANGUAGE v1.1 — no new divergent shell

## Materiality

- class: module
- activation: design_experience facet

## Divergence

| Direction | Philosophy / spatial / hierarchy difference | Status |
|---|---|---|
| Live CIP Channel Ops (AS-IS) | Equal KPI cards, toy density, generic grid chrome | rejected as execution target |
| FROZEN Workbench grammar 2 (selected) | Instrument + grid; histogram with mean marker; Read-first | **selected** — docs/design/stock-cover.html |
| Paper / second identity | New product look | not used |

Preservation rationale (if current direction retained):
FROZEN v1.1 Workbench language accepted 2026-08-30. UX-003 allows fewer than three
directions when there is an evidenced reason to preserve the established design language.

## Design signatures (2–4 when appropriate)

1. The average is not the position — histogram is the instrument; mean is a marker (CIP_DESIGN_LANGUAGE §5).
2. Severity in two channels — color plus weight/marker/position; never color alone (§1 principle 3).
3. Lens-scoped metrics — Fill vs plan / Cover / Inbound; never bare "Fill %" (§4 grammar 2).

## Identity tokens (high_fidelity)

- direction_name: Workbench v1.1 (frozen)
- type_pairing: Inter UI + IBM Plex Mono numerals (§2)
- numeral_treatment: tabular-nums; money right-aligned (§2)
- rule_weight: hairline --line/--line2 only (§2)
- accent_limit: #3db8e8 interactive; ok/wn/st semantic only (§2)

## State coverage

populated | loading | empty | error — exemplars: stock-cover.html, stock-cover-empty.html, stock-cover-loading.html

## Execution decisions (high_fidelity)

| Slot | Status | Rationale / evidence |
|---|---|---|
| responsive_decision | applicable | Desktop-primary ops; column picker ≤1280px per frozen exemplar pattern |
| visualisation_decision | applicable | WOC histogram — decision question on Cover lens (§4, §5) |
| consequential_action_decision | not_applicable | Cover lens is observational; consequential actions live on Settlement/Response |

## Rendered comparison (when practical)

artifact_class compared: high_fidelity implementation candidate vs docs/design/stock-cover.html

| Criterion | Frozen exemplar | Implementation candidate | Notes |
|---|---|---|---|
| task clarity | strong | | |
| operational density | strong | | |
| hierarchy | strong | | |
| distinctiveness | strong | | Workbench DNA without second identity |
| state handling | strong | | empty + loading variants exist |
| responsive behaviour | adequate | | desktop-primary explicit |

**Selected:** FROZEN exemplar conformance  
**Rejected:** Live KPI-card Channel Ops layout

## CR-006 sameness review

- structural / IA patterns challenged: retired equal-weight KPI row; instrument+grid retained
- visual-vocabulary challenge: reject generic card row / pill-only severity / toy table —
  justify Workbench grid rhythm (31–36px rows, Read strip, shape/histogram instruments)
- justified familiar patterns: sticky filter bar + spine — frozen §3 component inventory
```

---

## 2. Four `design_experience` quality dimensions

### 2.1 Names in this repo

The Fable north-star audit preserves these **framework dimension names** (prose vocabulary):

> materiality gating;  
> **design divergence**;  
> **design signatures**;  
> **rendered comparison**;  
> **design sameness review**;  
> journey evidence;

There are **zero** snake_case YAML keys `design_divergence`, `design_signatures`, `rendered_comparison`, or `design_sameness_review` in this repository. The authoritative **structured slots** are section headings in `.eif/DESIGN_EXPERIENCE_RECORD.md`:

| Framework name | Template section |
|---|---|
| design_divergence | `## Divergence` |
| design_signatures | `## Design signatures (2–4 when appropriate)` |
| rendered_comparison | `## Rendered comparison (when practical)` |
| design_sameness_review | `## CR-006 sameness review` |

Gate quote (template line 15):

> Programme quality dimensions on the node remain the gate.

---

### 2.2 Satisfying dimensions when conforming to FROZEN v1.1 (not inventing new concepts)

**Governing freeze** (`docs/design/CIP_DESIGN_LANGUAGE.md`):

> **STATUS: FROZEN v1.1 — 2026-08-30. Governing for implementation.** Changes via SPEC_GAPS + adjudication only.

NS-2 through NS-7 build against this document and audited exemplars under `docs/design/*.html` — **not** fresh divergent shell concepts.

#### design_divergence

UX-003 divergence table (`.agents/skills/ui-visual-design-specialist/references/contract.md`):

> | Major shell, new product, substantial experience redesign | ≥3 unless **evidenced reason to preserve the established design language** |

For frozen-language units:

- **Do not** fabricate three novel product directions.
- **Do** populate the Divergence table with: (a) live AS-IS or retired pattern **rejected**; (b) **FROZEN Workbench direction selected** with pointer to exemplar HTML; (c) optional discarded alternate (e.g. second identity) marked `not used`.
- **Do** fill **Preservation rationale (if current direction retained):** quoting the freeze date and charter acceptance.

This satisfies divergence ceremony as **convergence to an already-decided language**, not greenfield exploration.

#### design_signatures

Template:

> ## Design signatures (2–4 when appropriate)

For NS units: signatures should be **quoted or adapted from** `CIP_DESIGN_LANGUAGE.md` §1 principles and §5 intelligence signatures (Read, shape bars, concentration list, Δ columns, readiness checks, suggested action, fixed-purpose micro-viz) — instantiated for the container’s job (e.g. Cover: “the average is not the position”).

Blanket `na` on signatures is **not** valid for `high_fidelity`.

#### rendered_comparison

Template:

> ## Rendered comparison (when practical)
>
> Declare `artifact_class` of what was compared (ia_concept vs high_fidelity).

For frozen-language units, compare **implementation candidate vs frozen exemplar** (same `high_fidelity` class) — not two new conceptual directions. Criteria columns are quoted in the template (`task clarity`, `operational density`, `hierarchy`, `distinctiveness`, `state handling`, `responsive behaviour`).

If browser render is blocked, record `UNABLE_TO_RENDER` with methods tried — do not claim comparison from source/CSS alone (UX-003: “Do not accept source/CSS/JSX as visual evidence”).

#### design_sameness_review (CR-006)

Template:

> - **visual-vocabulary** challenge (required on `high_fidelity` even when IA already differs):

CR-006 (`.agents/skills/premium-benchmark-reviewer/references/contract.md`):

> Structural or information-architecture divergence does **not** satisfy this challenge. … For `high_fidelity` work, sameness review must include a **visual-vocabulary** challenge even when divergence ceremony is already structurally satisfied.

For frozen-language units:

- **Cannot** mark sameness `na` because the language is frozen.
- **Must** document which generic AI-dashboard patterns are **rejected** (KPI card row, pill-only status, toy tables, cyan body glow, etc.) and which **justified familiar patterns** are retained because the freeze explicitly prescribes them (spine, filter bar, data grid rules — §3 inventory).

Reference filled intent: `.eif/audit/R20260830130000_FRESH_NS/DESIGN_EXPERIENCE_RECORD.md` § CR-006 sameness.

---

### 2.3 `na` rules — quoted (schema does not use `na-with-rationale`)

The string **`na-with-rationale` does not appear** anywhere in this repository.

Authoritative `na` / not-applicable syntax:

**Execution slots** (`.eif/DESIGN_EXPERIENCE_RECORD.md`):

> Each slot: `applicable` with rationale/evidence, or **`not_applicable` with rationale**. **Not dummy `na`.**

**High-fidelity blanket ban** (same file):

> A `high_fidelity` record must not **blanket-`na`** those kinds.

**UX-002**:

> Record **`not_applicable` with rationale** when a slot genuinely does not apply.

| Situation | Legitimate marking |
|---|---|
| responsive_decision on desktop-only ops surface | `not_applicable` + rationale (desktop-primary job) |
| visualisation_decision on grammar-3 Brief blotter | `not_applicable` + rationale if no chart is causally required |
| consequential_action_decision on read-only lens | `not_applicable` + rationale |
| Divergence / signatures / CR-006 sameness on `high_fidelity` NS unit | **Not** `na` / `not_applicable` — frozen language still requires documented challenge and conformance |
| Entire DESIGN_EXPERIENCE_RECORD skipped | Only when `target_artifact_class: ia_concept` (UX-002) — **not** for NS-2…NS-7 product implementation |

---

## 3. Grammar and container in contract rows (charter v1.3, amendment 6)

**Amendment 6** (`docs/design/CHARTER_AMENDMENTS.md`):

> **New UI surfaces:** contract rows must cite the declared grammar
> from `CIP_DESIGN_LANGUAGE.md` §4 and the owning container from `CIP_NAV_MAP.md` in addition
> to any steward S-rows.

**Applied charter** (`docs/AUTONOMOUS_BUILD_CHARTER.md` § Scope lock / contract scoping):

> **New UI surfaces:** contract rows must cite the declared grammar
> from `CIP_DESIGN_LANGUAGE.md` §4 and the owning container from `CIP_NAV_MAP.md` in addition
> to any steward S-rows.

Charter module table shape:

> | Module | Contract rows | Exit criterion | Zone | Budget |

Grammar and container are **embedded in contract-row text** (not separate table columns). Example rows already in charter:

> | **P2-4 App shell + landing** | Navigation, IA, **Brief (grammar 3 signal blotter)**, spine per nav map | Brief **(grammar 3)** reachable; spine matches `CIP_NAV_MAP.md` | … |

> | **P3-3 Report builder** | **Grammar 6 Composer** (source/scope · artifact canvas · output panel); … | … per `reports-builder.html` | … |

### Contract-row pattern for NS UI units

Each row should be enumerable before implementation (charter failure mode #1):

> every module carries enumerated contract rows **written before implementation**.

**Recommended row shape** (convention synthesised from charter + amendment 6 — not a separate SCHEMA file):

```markdown
| Row ID | Contract row | Grammar (§4) | Container (nav map) | Exemplar | Notes |
|--------|--------------|--------------|---------------------|----------|-------|
| NS3-01 | Cover lens opens with computable Read + WOC histogram instrument | 2 — Instrument + grid | Stock — §3 Channel position & execution | docs/design/stock-cover.html | Lens control labels per §5 |
| NS3-02 | Empty and loading states match frozen variants | 2 | Stock §3 | stock-cover-empty.html, stock-cover-loading.html | Required states §6 |
```

**Grammar index** (quoted heading, `CIP_DESIGN_LANGUAGE.md` §4):

1. Queue + case  
2. Instrument + grid  
3. Signal blotter  
4. Ranked actions + calculator  
5. Factory (Imports)  
6. Composer  

**Container index** (`CIP_NAV_MAP.md` spine): Brief · Lineup · Stock · Settlement · Response · Steward · Reports · Admin.

---

## 4. Ready-to-paste block — NS-2 through NS-7 implementation prompts

Copy the block below into Cursor implementation prompts for north-star UI units. Adjust `## Implementation change scope` paths per unit.

```markdown
## EIF unit framing (do not skip)

- **Mode:** task-mode delivery unit (programme YAML/schema not in repo — do not mutate `.eif/program/`).
- **design_experience facet:** required — author DESIGN_EXPERIENCE_RECORD sections per `.eif/DESIGN_EXPERIENCE_RECORD.md`.
- **target_artifact_class:** high_fidelity (acceptance criteria + record front matter).
- **Design authority:** `docs/design/CIP_DESIGN_LANGUAGE.md` **FROZEN v1.1 — 2026-08-30** + `docs/design/CIP_NAV_MAP.md`.
- **Charter:** `docs/AUTONOMOUS_BUILD_CHARTER.md` v1.3 — contract rows cite grammar (§4) + container (nav map) per amendment 6.
- **Divergence:** preserve frozen Workbench — table AS-IS rejected vs frozen exemplar selected; use Preservation rationale (≥3 directions not required when language is frozen).
- **Sameness (CR-006):** visual-vocabulary challenge mandatory — cannot blanket-na; justify frozen patterns vs reject generic dashboard slop.
- **Execution slots:** only `applicable` or `not_applicable` with rationale — not dummy `na`.
- **Smoke:** browser automation on localhost:3000 — not API/curl proof (`.cursor/rules/smoke-via-browser.mdc`).
- **Do not:** declare EIF programme, start programme nodes, run migrations, or self-PASS VERIFY.

---

### NS-2 — Brief landing (replaces Control tower /dashboard)

| Field | Value |
|-------|--------|
| Container | Brief — `CIP_NAV_MAP.md` §1 Landing / attention blotter |
| Grammar | 3 — Signal blotter (`CIP_DESIGN_LANGUAGE.md` §4 item 3) |
| Exemplars | `docs/design/brief.html`, `brief-empty.html` |
| Packet data | `docs/design/PACKET_DATA.md` — eight signal rows |
| Retires | Dashboard KPI cards; Exceptions inbox as a place |
| VERIFY note | Until NS-2 PASS, gate A5/A6 may still target `/dashboard` (`docs/VERIFY_DEBT_RUNBOOK.md`) |

Contract rows must include: ranked signal rows (no KPI cards), Read traces to listed signals, no filter bar (period from tenant stamp), single next action per row, grammar 3 + container Brief on every row.

---

### NS-3 — Stock (Cover / Inbound / Movement / Execution lenses)

| Field | Value |
|-------|--------|
| Container | Stock — `CIP_NAV_MAP.md` §3 Channel position & execution |
| Grammar | 2 — Instrument + grid (§4 item 2) |
| Exemplars | `stock-cover.html`, `stock-cover-empty.html`, `stock-cover-loading.html`; inbound: `stock-inbound.html`, `stock-inbound-partial.html` |
| Lens labels | Sell-out · Fill vs plan · Cover · Inbound (§5) |
| VERIFY note | Inbound lens re-runs Unit 7 strip semantics when NS-3 PASS (`docs/VERIFY_DEBT_RUNBOOK.md`) |

Contract rows: sticky From/To/BU filter bar; Read + instrument + dense grid; lens-scoped metric names; histogram on Cover; operational row counts — not toy tables.

---

### NS-4 — Settlement

| Field | Value |
|-------|--------|
| Container | Settlement — `CIP_NAV_MAP.md` §4 Funding & settlement |
| Grammar | 1 — Queue + case (§4 item 1) |
| Exemplars | `docs/design/funding-settlement-r3.html`, `settlement-confirm.html` |
| Consequential actions | preview / confirm / readiness row required |

Contract rows: queue + case split; dual-currency columns; dominant money figure; settle flow with preview-confirm; grammar 1 + container Settlement on every row.

---

### NS-5 — Lineup

| Field | Value |
|-------|--------|
| Container | Lineup — `CIP_NAV_MAP.md` §2 LINEUP |
| Grammar | 2 — Instrument + grid (plan origination affordances §4 item 2) |
| Exemplars | `docs/design/lineup.html`, `lineup-pending.html` |
| Boundary | Owns plan; Stock/Response read — do not edit plan there |

Contract rows: pending Approve/Reject; Planned inline-edit cue; plan action bar Calc · Export · Apply; grammar 2 + container Lineup.

---

### NS-6 — Response (ranked commercial actions)

| Field | Value |
|-------|--------|
| Container | Response — `CIP_NAV_MAP.md` §5 Commercial response |
| Grammar | 4 — Ranked actions + calculator (§4 item 4) |
| Exemplars | `docs/design/response.html`, `response-blocked.html` |
| Retires | `/promotions` scaffold as standalone module |
| Capability audit | `docs/design/PROMO_PLANNER_CAPABILITY.md` |
| VERIFY note | B4 debt superseded only after NS-6 VERIFY includes B4 criteria re-run |

Contract rows: do-nothing as first-class action; calculator rail; drafts marked non-writing; grammar 4 + container Response.

---

### NS-7 — Steward

| Field | Value |
|-------|--------|
| Container | Steward — `CIP_NAV_MAP.md` §6 Ingest & steward |
| Grammar | 5 Factory grid + grammar 1 queue/case worklists |
| Exemplars | `docs/design/steward.html`, `steward-customer-worklist.html` |
| Import parity | `.cursor/rules/import-parity.mdc` + steward S-rows when importers touched |
| VERIFY note | Re-opens Unit 11 parity on steward container (`docs/VERIFY_DEBT_RUNBOOK.md`) |

Contract rows: Import Center grammar-5 grid; steward worklists grammar-1; enumerate S-rows per importer; grammar/container on UI rows + S-rows — not S-rows alone.

---

## Appendix — what to add when programme schema lands

When `.eif/program/SCHEMA.md` and `facet_map.yaml` appear in-repo, update this document with:

1. Exact YAML node keys for facet attachment (`design_experience`).
2. Whether `target_artifact_class` lives on the node, facet config, or acceptance-criterion mirror.
3. Machine-verifiable quality-dimension keys (if different from DESIGN_EXPERIENCE_RECORD section headings).
4. `python tools/program.py` commands for declaring a unit without hand-editing generated files.

Until then, **charter contract rows + WORK_ITEM + DESIGN_EXPERIENCE_RECORD** are the enforceable declaration path for NS-2…NS-7.
