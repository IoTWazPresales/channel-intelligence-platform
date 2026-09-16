# N-0028 correction recon — Start work action cards

**Run:** `NS18_START_WORK_CARDS_20260916`  
**Branch:** `feat/ns-2-brief-nav-collapse`  
**This note is source recon.** Operator brief is observation, not a licence to restore the previous MUI outlined tiles.

Cites **D-0008** (accepted). **N-0025** Start work verbs retained. **N-0026** Create promotion plan retained. **N-0027** queue click stays on Steward workspace — not in this node. Do not touch D-0002. Do not run GOV-008.

---

## Start work verbs (VERIFIED from `startWork.ts`)

| id | Label | href | Roles | Group | Completes there? |
|---|---|---|---|---|---|
| `create-lineup` | Import a lineup | `/admin/imports?unified=1` | admin, steward | Plan | Yes — unified import apply |
| `open-lineup` | Open lineup cases | `/lineup/cases` | admin, planner | Plan | Work on existing cases |
| `create-promo-plan` | Create promotion plan | `/promotions?propose=1` | admin, planner | Plan | Propose dialog (N-0026) |
| `import-sell-through` | Import sell-through | `/admin/imports?template=customer_sell_through` | admin, steward | Data | CST wizard |
| `import-shipping` | Import a shipping file | `/admin/imports?template=inbound_shipments` | admin, steward | Data | Inbound wizard |
| `settle-case` | Settle a case | `/commercial-planner/cpor-cases` | admin, planner | Funding | Completes on case desk |
| `steward-queue` | Work the steward queue | `/admin/mappings` | admin, steward | Data | Resolve in existing job steward (N-0027 workspace) |

Viewer: `startVerbsForRole('viewer')` is empty (N-0025). Do not add viewer verbs.

Steward-queue href stays `/admin/mappings` (queue leaf). Do not bounce to Import Center `?job=`. N-0027 product behaviour unchanged.

---

## Visual diagnosis (VERIFIED rendered `/brief` as Local Admin, 2026-09-16)

### Current Panel / PanelRow (production)

Start work is the same `Panel` + `PanelRow` grammar as Needs attention and Pinned reports: raised paper, title/subtitle, flush rows, left hairline. Neutral rows use `divider` as the left bar — the same channel Attention uses for severity. Copy `noWrap`-clips. The set reads as a settings/menu list, not as distinct jobs.

**Primary failure:** treatment + container. Start work is visually a blotter, not a launch.

### Previous outlined cards (commit `a969d63`, restored-from HEAD before `4d9079b`)

MUI `Card variant="outlined"` + `CardActionArea` + `CardContent` in a 2/3/4 grid, copied from Import Center `START_CARDS`. Import Center tiles are type-pickers (label + technical slug) inside a Panel titled “Start an import”. On Overview they became equal-weight generic boxes: long `what` text stuffed into a picker tile, no job-vs-exception distinction, no grouping, no go-affordance beyond the whole card. Operator: they looked poor. Restoring that file is not the design.

**Primary failure:** card treatment (Import Center picker cloned onto Overview).

### Wider Overview composition

N-0019 lab: dashboard left (`1fr`) + attention right (`312px`). Intelligence is prime.

N-0025 production: Start work left + attention right, dashboard **below**. Start work prime is still required. Seven list rows occupy the intelligence column, so the dashboard is unnecessarily below the fold even when Start work could be a compact strip.

**Secondary failure:** page composition. Layout must change if action cards are to stay compact and intelligence is to stay in the first viewport.

---

## Design-lab / primitives (VERIFIED)

| Primitive | Path | Use for Start work? |
|---|---|---|
| `Panel` / `PanelRow` | `workbench-ui/Panel.tsx` | No — exception blotter / list |
| Outlined MUI `Card` | Import Center / DataSurface | No — type picker, not Overview jobs |
| `HeadlineFigure` | workbench-ui | No — KPI numerals |
| `DomainHeader` | workbench-ui | Overview chrome, already mounted |
| `ActionCard` | **new** workbench-ui primitive | Yes — hairline job tile |

Lab `OverviewSurface` has **no Start work** today. N-0028’s “lab composition” was Import Center, which is the wrong referent.

---

## Surrounding Overview sections (constraints)

- DomainHeader (title Overview / lab greeting)
- Start work (this node) — must stay prime (N-0025)
- Needs attention — exceptions only; PanelRow is correct here
- Pinned reports — list of saved reports; PanelRow is correct
- Business dashboard — live widgets or honest empty; must not invent fixture KPIs

N-0025: Start work still shows on a clean week and at 390 above Attention. Viewer empty copy remains.

---

## Coherent subset (this correction)

1. Govern Start work as **action cards** on lab Overview, then port.
2. Prefer a full-width launch strip so dashboard ∥ attention can return (N-0019 body).
3. Keep all seven verbs, role gating, destinations, N-0027 queue href.
4. Amend N-0028 AC only to drop “Import Center outlined Card” as the pattern name; do **not** permit PanelRow.

## Untouched

D-0002, N-0006, N-0013, D-0010, BACKLOG-181, Movement/Execution, N-0025 leftovers, N-0027 product, Lineup cases HeadlineStrip (already on the leaf), viewer verbs.
