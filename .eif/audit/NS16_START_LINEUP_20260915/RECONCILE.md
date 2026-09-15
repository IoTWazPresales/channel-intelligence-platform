# NODE B recon — Start work surface and Lineup cases

**Run:** `NS16_START_LINEUP_20260915`  
**Branch:** `feat/ns-2-brief-nav-collapse` @ `c87e40c` (git, this session)  
**This note is source recon.** The operator brief is observation, not acceptance.

Cites **D-0008** (accepted): Planning owns Lineup cases as a leaf under Planning chrome; Overview is a domain hub with Start work; Import Center cards are the Data start pattern. **N-0025** built Start work; **N-0026** added Create promotion plan. Do not revert those verbs. Do not remediate N-0025 GOV-008 leftovers (BACKLOG-182, viewer verbs).

---

## Start work verbs (VERIFIED from `startWork.ts`)

| id | Label | href | Where it lands | Job completes there? |
|---|---|---|---|---|
| `create-lineup` | Create a lineup | `/admin/imports?unified=1` | Import Center unified lineup dialog (dedicated, not generic wizard) | **Yes** — files become `commercial_lineup_case` via import apply |
| `open-lineup` | Open lineup cases | `/lineup/cases` | Planning chrome + LineupContainer | **Work on existing cases** — not create |
| `create-promo-plan` | Create promotion plan | `/promotions?propose=1` | Promotion Planner propose dialog (N-0026) | Compose GET; create draft is the write (not this node) |
| `import-sell-through` | Import sell-through | `/admin/imports?template=customer_sell_through` | Guided CST wizard | Yes |
| `import-shipping` | Import a shipping file | `/admin/imports?template=inbound_shipments` | Guided inbound wizard | Yes |
| `settle-case` | Settle a case | `/commercial-planner/cpor-cases` | Case book; settle on case desk | Completes on `/cpor-cases/<id>` (Node C) |
| `steward-queue` | Work the steward queue | `/admin/mappings` | N-0027 failure-type queue | Resolve in existing job engines |

Copy on `steward-queue` still says “Legacy mapping queue” — **stale after N-0027** (VERIFIED).

Viewer: `startVerbsForRole('viewer')` is empty (N-0025). Do not add viewer verbs here.

---

## Other entry points that claim to start a job (VERIFIED)

| Entry | Lands | Completes? |
|---|---|---|
| Import Center `START_CARDS` + “New import” | `/admin/imports?template=` or `?unified=1` | Yes — same wizard |
| Data chrome “New import” | `/admin/imports` | Yes |
| PO Management `unified=1` | Import Center unified dialog | Yes |
| Getting-started links | `/lineup/cases` and others | Navigate only |
| Command palette (Ctrl+K) | nav leaves | Navigate only |
| Cover lens “Plan lines for this product” | `/lineup/cases?product=` | **UNCOVERED** — lineup code does not read `product` |
| `POST /api/v1/commercial-planner/lineup-cases` from CurrentLineupSection | Empty `commercial_lineup_case` `source_context=commercial_planner` | Draft stub — **not** a creation workbench; not Start work |

## Lineup create workbench (VERIFIED)

There is **no** blank lineup authoring workbench. Cases are created by **unified import** (`?unified=1`) or by the planner POST of an empty draft. `/lineup/cases` is a plan-line grid on existing cases.

**Decision for this node:** keep href `/admin/imports?unified=1`. Rename the verb to **Import a lineup** so the label matches the job that completes there. Do not point Start work at the empty-draft POST.

---

## Start work chrome (VERIFIED)

`StartWorkPanel` wraps verbs in `Panel` + `PanelRow`. Import Center start uses outlined `Card` + `CardActionArea` in a grid (`ImportCenterOverview` `START_CARDS`). Those cards sit inside a Panel titled “Start an import”. Operator asked for the **card pattern** with **no wrapper card** around Start work — i.e. the outlined cards themselves, not a Panel/Card around the set.

---

## Lineup cases composition (VERIFIED)

Already under `PlanningChrome` (DomainHeader + LensTabs) from N-0020. Inner `LineupContainer` is still the N-0009 chrome: `#1a1d23`, IBM Plex Mono, hardcoded From/To/BU/Customer “26Q3” / “All”, `LineupTrendInstrument` with **hardcoded** Q1/Q2 bars (not live `plan-vs-executed`). Live numbers exist on `LineupRegimeStrip` (planned units, net requirement, approval %) and `LineupReadStrip` (pending count, fill rate when available). Grid is `EnterpriseDataGrid` via `LineupPlanGrid`.

Lab PlanningSurface is the **Planning hub**, not a cases-leaf mock. Production hub already matches (`PlanningOverview`). The leaf should use the same workbench primitives: `HeadlineStrip`, `ScopeBar`, `ModuleDataSection` — not a second DomainHeader (chrome already has it).

---

## Coherent subset (implement)

1. Start work: outlined Import Center cards, no Panel/Card wrapper; keep all seven verbs (N-0025 + N-0026).
2. Rename create-lineup → **Import a lineup**; href unchanged. Refresh steward-queue `what`.
3. Lineup cases inner: HeadlineStrip from live regime/read figures; ScopeBar for the **wired** approval filter only; keep grid + action bar. Remove hardcoded period chips, fake trend bars, duplicate “Lineup / …” crumb.

## Routed out

- Viewer Start work verbs (N-0025 GOV-008).
- `?product=` filter on lineup cases (Cover lens).
- Planner empty-draft POST as a Start work destination.
- LineupPlanGrid badge typography (Node C grid parity).
- Case book / settlement workspace (Node C).
- N-0025 Attention 431px, Payments same-URL (BACKLOG-182).
- Movement/Execution, D-0002, N-0006, N-0013, D-0010, BACKLOG-181.
