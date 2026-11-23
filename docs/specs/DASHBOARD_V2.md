# Dashboard V2 — design proposal

Status: design review only. No product implementation or migration is included.

Prepared: 2026-11-20.
Source branch: `docs/dashboard-v2-design-20261120`.
Inspected HEAD: `b4039a1dc6b9bafcd72bf544cf3dfcbd78b7ca35`.

Warren approves screenshots and the decisions below before implementation begins.
The coordinator writes these artifacts and captures the screenshots. No rendered
comparison, browser smoke, tests, database state or live performance is claimed here.

## 1. Outcome

An account manager should answer three questions within a few seconds:

1. How did my accounts perform against the targets I chose?
2. Where does the performance come from?
3. What should I work on next?

The Dashboard puts target progress first, explanatory charts second, attention
alongside them, and work shortcuts in a compact row.

A job-title default provides a useful starting point. Each user can change their
own tiles, layout and targets, then explicitly reset to the tenant's current
default for their job.

Job title determines the starting arrangement. Authorization continues to come
from the existing role, tenant, product-line access and account-scope rules.

## 2. Grounding in this tree

### Existing surfaces and paths

| UI / trigger | API route | Celery task | Writer / reader | Commit model |
|---|---|---|---|---|
| `/brief` | Dashboard list, semantic catalogues, `/brief/signals`, saved reports | None for dashboard rendering | `OverviewHub.tsx`; existing dashboard and Brief services | Reads |
| `/dashboard` | `/api/v1/dashboard/summary` | None | Legacy dashboard summary | Reads; retain compatibility |
| `/dashboards` editor | `/api/v1/dashboards` and widget routes | None | `endpoints/dashboards.py`; definition validation services | Existing request transactions |
| Drag / resize | `PATCH /api/v1/dashboards/{id}/layout` | None | Existing layout writer | One request for the changed layout |
| Model chart or KPI | `POST /api/v1/query/v2/execute` | None | `app/query/model/execute.py:run_v2` | Read on scoped request session |
| Catalogue | `GET /api/v1/semantics/v2/catalog` | None | Semantic model and catalogue | Reads |
| Start-work action | Existing destination route | Destination-specific | Existing domain workflow | Dashboard introduces no domain write |

The canonical direction is to extend the existing Overview hub, dashboard widgets,
grid and query engine. Do not build another metrics service or another dashboard
storage mechanism.

### Files inspected

- `apps/web/src/app/(app)/brief/page.tsx`
- `apps/web/src/app/(app)/dashboard/page.tsx`
- `apps/web/src/features/brief/BriefPageContent.tsx`
- `apps/web/src/features/brief/BriefSignalRow.tsx`
- `apps/web/src/features/overview/OverviewHub.tsx`
- `apps/web/src/features/overview/OverviewChrome.tsx`
- `apps/web/src/features/overview/StartWorkPanel.tsx`
- `apps/web/src/features/overview/startWork.ts`
- `apps/web/src/features/dashboards/DashboardGrid.tsx`
- `apps/web/src/features/dashboards/dashboardList.ts`
- `apps/web/src/features/dashboards/builder/types.ts`
- `apps/web/src/features/dashboards/builder/api.ts`
- `apps/web/src/features/dashboards/builder/catalog.ts`
- `apps/web/src/features/dashboards/builder/requestFor.ts`
- `apps/web/src/features/dashboards/builder/useDashboardRun.ts`
- `apps/web/src/features/dashboards/builder/dates.ts`
- `apps/web/src/theme/cipTokens.ts`
- `apps/web/src/theme/cipTheme.ts`
- `packages/ui/src/tokens.ts`
- `packages/ui/src/theme.ts`
- `apps/api/app/models/saved_reports.py`
- `apps/api/app/models/iam.py`
- `apps/api/app/core/user_job.py`
- `apps/api/app/api/v1/endpoints/dashboards.py`
- `apps/api/app/api/v1/endpoints/query.py`
- `apps/api/app/api/v1/endpoints/brief.py`
- `apps/api/app/services/dashboard_templates.py`
- `apps/api/app/services/brief_signals.py`
- `apps/api/app/services/tenant_settings.py`
- `apps/api/app/api/v1/endpoints/tenant_settings.py`
- `apps/api/app/query/model/execute.py`
- `apps/api/app/query/cache.py`
- `apps/api/app/semantics/models/default.yaml`
- `apps/api/alembic/versions/20261120_0064_tenant_setting.py`
- `.eif/DESIGN_EXPERIENCE_RECORD.md`

### Findings that affect the design

- `/brief` already hosts the Overview hub. `/dashboard` is explicitly legacy.
- Overview renders the first dashboard in its list. V2 needs an explicit personal
  home selection; list order must not choose somebody's starting workspace.
- The editor already uses `react-grid-layout`, including keyboard movement and
  resizing, a 12-column layout and stacking below a 720px container width.
- Widgets already support `definition_v2`, KPI comparison and sparkline options.
- Dashboard lists already have a shared tenant-and-user cache key. Preserve it.
- `app_user.job` already exists separately from `role`.
- Existing jobs are exactly `account_manager`, `product_manager`, `finance`,
  `country_manager`, `admin`, or no job. “Sales manager” is not a stored job.
  This proposal uses Account manager and does not change the job vocabulary.
- The tenant-setting registry and API already exist. Reuse them.
- The latest migration file in the inspected tree is `20261120_0064`, following
  `20261118_0063`. The newest memory note reports live `cip` at 0063; this design
  makes no claim that 0064 is applied.
- Brief signals expose rank, severity, action label and destination. They do not
  currently expose the owner and age fields shown in the mock-up.
- CST stock cover exists as `cst_sellthrough.stock_cover`. It uses four weeks
  ending on each customer's last reported day and is not a time series.
- Mixed weekly/monthly CST reporting must not be split into weekly or daily
  observations. Use a monthly trend and retain engine refusals.
- CST has no distributor attribution. Do not connect it through a customer's
  preferred distributor.
- Sales value, restock flags, CPOR open cases and generic CPOR value remain
  pending/refused in the inspected model. They are not default KPI candidates.
- The design-experience record is an unfilled template, not an approved visual
  baseline.
- `.cursor/rules/engineering-rules.mdc` is absent from this checkout. No substitute
  rules were invented.

## 3. Design artifacts

- `docs/design/dashboard-v2/index.html`
- `docs/design/dashboard-v2/targets-builder.html`

Both are standalone HTML files with inline CSS, SVG and JavaScript. They make no
network requests, load no external fonts and require no server.

Open each at a 1280×800 viewport. Dark is the deterministic initial theme.
The theme button switches `data-theme` to light. Narrow layouts stack naturally.

All figures, targets, owners, ages and preferred bands are illustrative. The
Dashboard screenshot represents a historical review as of 1 October 2026, rather
than presenting September data as current November data.

Prototype interactions:

- Theme switching works.
- Add tile opens the sibling target-builder file.
- Target inputs update the preview.
- Other dates or account scopes show unavailable illustrative data.
- Attention and work actions open explanatory preview dialogs.
- The job picker explores proposed defaults without changing the current layout,
  job or permissions.
- Reset has a confirmation dialog.
- Edit layout toggles the drag and resize affordances.
- Dragging, resizing, persistence and product navigation are visual proposals.
  Their runtime implementation is outside this design artifact.

### Visual direction: performance workbench

Artifact class: high-fidelity proposal.

Character: measured, operational and direct. Give the commercial result visual
weight while keeping the next useful action close.

Identity decisions:

| Decision | Proposal |
|---|---|
| Typography | Existing Inter / Segoe UI / system family; local fallback in the mock |
| Numerals | Tabular numerals, large actual values, smaller target and comparison |
| Backgrounds | Existing layered cool-grey surfaces |
| Accent | Existing blue for selection and actual series |
| Semantics | Existing green, amber and red; brighter companion text for contrast |
| Radius | Existing 12px cards and 10px controls |
| Rules | 1px borders, 3px semantic tile edge |
| Depth | Existing restrained surface shadows and blue background wash |

Dark tokens originate in `packages/ui/src/tokens.ts`; light tokens originate in
`apps/web/src/theme/cipTokens.ts`. The prototype copies these into CSS variables
because it must be self-contained. Product implementation reads the existing
theme rather than creating another token source.

Design signatures:

1. Large actual values paired with a narrow target-progress rail.
2. A broad trend and compact customer ranking, followed by a stock-cover strip.
3. A ranked attention rail with a distinct amber edge and explicit actions.
4. Small work cards that remain visible without dominating the page.

Alternatives considered:

| Direction | Treatment | Decision |
|---|---|---|
| Feed first | Attention list followed by charts | Retain as an attention-focused view; insufficient performance hierarchy for the default |
| Performance workbench | Targets above analysis with attention beside it | Proposed |
| All-chart canvas | Every element becomes a chart tile | Reject for the default; obscures ownership, age and work actions |

The design changes scale, composition, hierarchy and chart vocabulary. It does
not depend on adding pills or applying a new palette to the existing flat panels.

Familiar controls are retained where they reduce learning: select controls,
progress bars, ranked lists and existing grid handles.

Rendered comparison remains pending coordinator screenshots and Warren review.

## 4. Page composition and jobs to be done

### Header and scope

Job: understand whose workspace this is and what period the figures describe.

Show:

- Dashboard title.
- Current job default, with an option to explore other tenant-configured defaults.
- Account scope and reporting period.
- Add tile, Edit layout and Reset to my role default.
- Existing My accounts control where applicable.

“Role default” is familiar user-facing wording; storage and authorization use
the precise distinction between job and permission role.

Changing the explored default does not change `app_user.job`. Applying a different
default is a separate explicit layout action, if Warren approves that option.

Do not change D-0141 starting-screen routing or the existing rollout flag as part
of this redesign.

### Personal target tiles

Job: distinguish improving performance from meeting the target.

Each tile shows:

- Title and measure unit.
- Actual value.
- Target and period.
- Target attainment, where mathematically meaningful.
- Gap or headroom against target.
- Comparison with a previous period, if available.
- Tiny trend where the measure permits a period breakdown.
- On track / At risk / Behind wording.
- Data vintage and scope details through the existing figure-information pattern.
- Edit, drag handle and resize corner in edit mode.

A positive prior-period delta does not turn a missed target green. The example's
sell-through improves 12.3% while still missing its target.

The three example measures are:

| Tile | Exact measure | Illustrative actual | Illustrative target | Status |
|---|---|---:|---:|---|
| Sell-through units | `cst_sellthrough.units` | 24,860 | 30,000 | Behind |
| Units per week | `cst_sellthrough.units_per_week` | 1,891.52, displayed 1,892 | 1,800 | On track |
| Sites reporting | `cst_sellthrough.stores_reporting` | 46 | 50 | At risk |

The example period is 1 July–30 September 2026, inclusive: 92 days.
The previous same-length period is 31 March–30 June 2026, not calendar Q2.
Previous units are 22,140. Both weekly rates use 92/7 weeks.
Previous distinct reporting sites are 42.

“Sites reporting” retains the engine's distinct-site-label semantics. Do not
silently relabel it as a unique physical-store master count.

### Default charts

Job: explain the headline result and identify where to investigate.

| Chart | Query | Purpose |
|---|---|---|
| Monthly sell-through vs target | `cst_sellthrough.units`, breakdown `period`, grain `month` | Reveal direction and gap |
| Units by customer | `cst_sellthrough.units`, breakdown `customer` | Show contribution |
| Stock-cover strip | `cst_sellthrough.stock_cover`, breakdown `customer`, no period breakdown | Expose low and high cover |

The example monthly units are 7,200, 8,100 and 9,560, totalling 24,860.
The target overlay is an explicitly even allocation of the 30,000 quarterly
target: 10,000 per complete calendar month.

Only additive measures may receive this allocation. Distinct counts, rates,
ratios and snapshots must not be split or summed to invent monthly targets.

The example customer units are 8,720, 6,940, 5,400 and 3,800.
The stock-cover examples are 1.4, 4.8, 9.2 and 3.6 weeks.
The illustrated preferred band is 3–6 weeks.

That band is display configuration, not a new replenishment business rule.
No production default band is introduced without tenant configuration or approval.
Do not generate domain actions from this illustrative colour rule.

Cover is evaluated as of each customer's latest stock report on or before the
period end. `period.from` does not redefine its four-week lookback.
Missing stock or sales keeps the engine's unavailable semantics.

Names appear only in entity-labelled columns, chart label columns or entity
pickers. Store IDs internally; show names in Customer and Distributor columns.
Use explicit IDs for filters and joins. Never use fuzzy entity matching.

### Needs attention

Job: choose the next action with enough context to trust its priority.

Retain existing server ranking and action destinations. Show:

- Rank.
- Severity symbol and text.
- Plain-language issue.
- Owner, or Unassigned when unknown.
- Age with its basis: overdue, failed, first detected or observed.
- One action button using the existing `action_label` and `action_href`.

A click opens the existing work surface with its scope preserved. It does not
approve, settle, re-import or mutate the domain from the Dashboard.

Extend the existing Brief payload with optional:

- `owner_label`
- `owner_user_id`, only where permitted and sourced
- `age_at`, an ISO timestamp
- `age_basis`: `due_at`, `failed_at`, `first_detected_at`, or `observed_at`

For aggregate items, state “Oldest” only when the returned timestamp is the oldest
relevant underlying item. Do not use response-generation time as issue age.
Do not infer an owner from the issue type. Show Unassigned / Age unavailable
when the source does not supply the information.

The prototype's team owners and ages are illustrative. No new shadow attention
queue or issue-lifecycle table is proposed.

### Compact start-work row

Job: start a common task without searching navigation.

Reuse `START_VERBS`, destination routes and `startVerbsForRole`.
Show up to four permitted actions, with the remainder behind More work.
Reports can remain a separate existing navigation shortcut.

The example includes line-up review, promotion proposal, funding settlement and
reports. Production actions depend on the user's permission role.

Keep pinned reports accessible through a compact Pinned reports section or
expander below the first screen. Preserve pin/unpin behavior and the existing
report visibility checks.

## 5. Layout engine and libraries

Use the existing `react-grid-layout` installation and `DashboardGrid.tsx`.
It is a maintained drag/resizable grid with an MIT license.
[Upstream project](https://github.com/react-grid-layout/react-grid-layout).

Use its existing `react-resizable` integration. Do not add another resize engine
or use dnd-kit to implement a second dashboard grid.

Reuse Recharts for analytical charts.
[Upstream project and MIT license](https://github.com/recharts/recharts).
Keep the repo's installed version unless a separately justified change requires
an upgrade.

Reuse the existing AG Grid wrapper for detailed rows and accessible tabular
exploration. Preserve the project's existing AG Grid licensing arrangement.
Do not assume Enterprise features are permissively licensed or introduce a new
commercial dependency.

Use MUI for controls, menus, dialogs and theme integration; TanStack Query for
server state. No second chart library, date library or state library is needed.

### Placement behavior

- Preserve the existing 12-column grid and 36px base rows with 8px grid margins.
- Use existing `{x,y,w,h}` widget layouts.
- Desktop starts with three KPI tiles, then trend/customer charts and cover.
- Attention and work shortcuts are fixed page regions in the first build.
  They are not fake metric widgets.
- The mock's composition is illustrative; the implementation must fit the
  existing grid's discrete row heights rather than reproduce arbitrary pixels.
- Product minimum sizes: KPI 3 columns × 4 rows; standard chart 4 × 6;
  cover strip 6 × 4. Validate per visualization.
- Charts resize inside fixed-height containers. Retain the existing protection
  against recursive chart-driven container growth.
- Below 720px of canvas width, stack tiles using the existing derived layout.
  Do not persist that temporary stacked arrangement over the desktop layout.
- At tablet sizes, attention moves below the analytical canvas.
- On phones, show KPIs, a jump link to attention, charts, attention, then work.
- At 200% zoom, preserve reading order and access to actions without horizontal
  page scrolling.
- Edit mode exposes drag, resize and tile menus. Normal mode prioritizes reading.
- Retain keyboard arrows to move and Shift+arrows to resize.
- Persist one layout request after a completed interaction, using the existing
  debounce behavior. Cancel pending saves on unmount or identity change.
- Save errors retain the visible unsaved arrangement with Retry / Discard.
  Do not claim Saved before server acknowledgement.

## 6. Per-user target definition

Reuse `DashboardWidget.definition_v2` as the only query definition.

A target is an optional one-to-one extension of a personal KPI widget.
It references that widget rather than copying its measure and filters into a
second independent query document.

Logical aggregate returned to the builder:

```json
{
  "widget": {
    "title": "Sell-through units",
    "visual": "kpi",
    "definition_v2": {
      "v": 1,
      "query": {
        "measures": ["cst_sellthrough.units"],
        "breakdowns": [],
        "filters": {}
      },
      "display": {
        "kpi": {
          "compare": true,
          "sparkline": true
        }
      }
    }
  },
  "target": {
    "value": "30000",
    "direction": "at_least",
    "risk_margin": "3000",
    "period": {
      "kind": "fixed",
      "from": "2026-07-01",
      "to": "2026-09-30"
    },
    "comparison": {
      "mode": "previous_period"
    },
    "scope_mode": "current_access",
    "version": 1
  }
}
