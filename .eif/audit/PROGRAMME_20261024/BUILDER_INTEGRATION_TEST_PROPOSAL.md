# N-0116 workspace/editor integration regression tests

Run: `RUN-20261024-N0116-VISUAL-PROPOSAL`. 2026-10-24. Implementation support, proposal only.
This artifact is the only write for this subtask. No source, services, ledger or databases changed.
Read the current DashboardWorkspace, BuilderEditorDialog, FilterBar, useDashboardRun, BuilderData,
Starters, builder API adapter, existing WidgetEditorDialog tests and Vitest/Playwright/Next config.
Source is concurrently changing under root ownership; preserve those changes when applying.

## Boundary and purpose

Use the **real** DashboardWorkspace, React Query, useDashboardRun, filter bar, v2 editor, starters and
builder API adapter together. Stub only browser geometry (`next/dynamic` DashboardGrid), widget
drawing (`DashboardWidgetCard` and V2WidgetBody), and HTTP (`@/lib/api`); keep provider/executor and
all orchestration real. The card boundary records **committed** props, so a switch test catches a
first paint/query with the previous dashboard's clicks even if an effect clears them a moment later.
This is component/contract coverage, not proof of chart rendering or physical drag interaction.
Root's adapter tests own legacy fallback HTTP bodies; this suite proves workspace-to-adapter wiring.

## Ready-to-apply `features/dashboards/DashboardWorkspace.integration.test.tsx`

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { builderCatalog } from '@/design-lab/fixtures/builder';
import { renderWithProviders } from '@/test-utils/renderWithProviders';
import { V2ExecutorProvider } from './builder/BuilderData';
import type { DashboardRunContext } from './builder/runContext';
import type { V2Request, V2Response } from './builder/types';
import { DashboardWorkspace } from './DashboardWorkspace';
import type { CatalogResponse, Dashboard, DashboardWidget } from './types';

const edge = vi.hoisted(() => ({
  apiGet: vi.fn(), apiPost: vi.fn(), apiPatch: vi.fn(), apiPut: vi.fn(), apiDelete: vi.fn(),
  commits: [] as Array<{ name: string; widget: number; filters: Record<string, unknown>; window: unknown; selected: string[]; required?: string[] }>,
}));
vi.mock('@/lib/api', () => ({
  apiGet: edge.apiGet, apiPost: edge.apiPost, apiPatch: edge.apiPatch,
  apiPut: edge.apiPut, apiDelete: edge.apiDelete,
  safeDisplayError: (e: unknown) => e instanceof Error ? e.message : String(e),
}));

// Dynamic grid owns geometry, not filter/editor state. Keep renderWidget and callback payload real.
vi.mock('next/dynamic', async () => {
  const { createElement: h, Fragment } = await import('react');
  return { default: () => (p: {
    widgets: DashboardWidget[];
    renderWidget: (w: DashboardWidget) => import('react').ReactNode;
    onLayoutPersist: (n: Array<{id:number;layout:{x:number;y:number;w:number;h:number}}>) => void;
  }) => h('div', { 'data-testid': 'workspace-grid-boundary' },
    h('button', { type: 'button', onClick: () => p.onLayoutPersist(p.widgets.map((w) =>
      ({ id: w.id, layout: { x: 2, y: 7, w: 6, h: 8 } }))) }, 'Commit moved layout'),
    ...p.widgets.map((w) => h(Fragment, { key: w.id }, p.renderWidget(w))),
  ) };
});

// Observe the real context that a card receives; capture commits, never aborted renders.
vi.mock('./DashboardWidgetCard', async () => {
  const { createElement: h, useLayoutEffect } = await import('react');
  return { DashboardWidgetCard: (p: {
    widget: DashboardWidget; ctx: DashboardRunContext; dashboardName: string; onEdit: () => void;
  }) => {
    const snap = { name: p.dashboardName, widget: p.widget.id,
      filters: p.ctx.filters, window: p.ctx.window, selected: p.ctx.selectedKeys, required:p.ctx.required };
    useLayoutEffect(() => { edge.commits.push(JSON.parse(JSON.stringify(snap))); });
    return h('section', { 'data-testid': `card-boundary-${p.widget.id}` },
      h('output', { 'data-testid': `context-${p.widget.id}` }, JSON.stringify(snap)),
      h('button', { type:'button', onClick: p.onEdit }, `Edit widget ${p.widget.id}`),
      h('button', { type:'button', onClick: () => p.ctx.onSelect?.(
        { breakdown:'channel', value:'Retail', label:'Retail' }, false) }, 'Select Retail from chart'),
      h('button', { type:'button', onClick: () => p.ctx.onSelect?.(
        { breakdown:'period', value:'2026-W40', label:'2026-W40',
          window:{from:'2026-09-28',to:'2026-10-04'} }, false) }, 'Select week from chart'),
    );
  } };
});

// Preview requests still execute through real useV2Query. SVG/AG Grid rendering has its own tests.
vi.mock('./builder/V2WidgetBody', async () => {
  const { createElement: h } = await import('react');
  return { V2WidgetBody: (p: { result?: V2Response; loading: boolean }) =>
    h('output', { 'data-testid':'editor-preview-answer' },
      p.loading ? 'loading' : p.result?.ok ? 'answer ready' : 'no answer') };
});

const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x));
const windowA = { from:'2026-07-01', to:'2026-07-31' };
const windowB = { from:'2026-08-01', to:'2026-08-31' };
const metricCatalog: CatalogResponse = { version:1, source_doc:'fixture', dimensions:[], metrics:[{
  id:'A3-05', key:'sellout_units', label:'Sell-out units', status:'implemented',
  formula:'Sum of distributor sell-out units', allowed_grains:[['customer'],['period']], calendar_period:true,
}] };

function widget(id: number, dashboardId: number): DashboardWidget {
  return { id, dashboard_id:dashboardId, title:`Widget ${id}`, visual:'hbar', metric_key:'sellout_units',
    grains:['customer'], filters:{}, period_grain:null, saved_report_id:null, sort_order:0,
    layout_json:{x:0,y:0,w:6,h:8}, definition_v2:{v:1,query:{measures:['dsi_sellout.units'],breakdowns:['customer']}} };
}
function dashboards(): Dashboard[] {
  return [
    { id:1,name:'Board A',description:null,visibility:'personal',shared_roles:[],widgets:[widget(11,1)],
      filters_json:{date:{preset:'custom',...windowA},compare:'none',customer:[101]} },
    { id:2,name:'Board B',description:null,visibility:'personal',shared_roles:[],widgets:[widget(21,2)],
      filters_json:{date:{preset:'custom',...windowB},compare:'none',customer:[202]} },
  ];
}
let store: Dashboard[];
let v2CatalogMissing: boolean;
let storageMissing: boolean;
const clients: QueryClient[] = [];

function response(req: V2Request): V2Response {
  const key = req.breakdowns?.[0] ?? 'customer';
  const columns: V2Response['columns'] = key === 'customer'
    ? [{id:'customer',kind:'breakdown',label:'Customer',fields:['customer_id','customer_name']}]
    : [{id:key,kind:'breakdown',label:key,fields:[key]}];
  const rows = key === 'customer'
    ? [{customer_id:101,customer_name:'Alpha Retail'},{customer_id:202,customer_name:'Beta Retail'},{customer_id:303,customer_name:'Gamma Retail'}]
    : [{[key]:'Retail'},{[key]:'Wholesale'}];
  return { ok:true,columns:[...columns,...req.measures.map((id) =>
    ({id,kind:'measure' as const,label:id,fields:[id],unit:'units'}))],
    rows:rows.map((r) => ({...r,...Object.fromEntries(req.measures.map((m) => [m,12]))})),
    totals:Object.fromEntries(req.measures.map((m) => [m,36])),truncated:false,refusals:[] };
}
const execute = vi.fn(async (req: V2Request) => response(req));

beforeEach(() => {
  vi.clearAllMocks(); edge.commits.length = 0;
  store = dashboards(); v2CatalogMissing = false; storageMissing = false;
  window.localStorage.removeItem('cip.dashboard.template-note.dismissed');
  edge.apiGet.mockImplementation(async (path: string) => {
    if (path === '/api/v1/dashboards') return {items:clone(store).map((d) => {
      if (storageMissing) { delete d.filters_json; delete d.template_key; }
      return d;
    })};
    if (path === '/api/v1/semantics/catalog') return clone(metricCatalog);
    if (path === '/api/v1/semantics/v2/catalog') {
      if (v2CatalogMissing) throw new Error('Not Found (404)');
      return clone(builderCatalog);
    }
    if (path === '/api/v1/dashboards/templates') return {count:1,items:[{
      key:'account_overview',title:'Account overview',description:'A copy you can edit',widget_count:1,
      required_filters:['customer'],left_out:[],
    }]};
    throw new Error(`Unexpected GET ${path}`);
  });
  edge.apiPost.mockImplementation(async (path: string, body: Record<string, unknown>) => {
    if (path === '/api/v1/query/execute') return {
      ok:true,status:'ok',metric_key:'sellout_units',grains:['customer'],validation:{ok:true,message:''},
      invariants_applied:[],data_vintage:null,value:36,rows:[],series:null,message:null,handler:'fixture',
    };
    if (path === '/api/v1/dashboards/from-template') {
      const d: Dashboard = {...dashboards()[0],id:3,name:'My account copy',description:'A copy you can edit',
        template_key:String(body.key),widgets:[widget(31,3)],
        filters_json:{date:{preset:'all_time',from:null,to:null},compare:'none',required:['customer']}};
      store.push(d); return clone(d);
    }
    const m = /^\/api\/v1\/dashboards\/(\d+)\/widgets$/.exec(path);
    if (m) {
      const d = store.find((d) => d.id === Number(m[1]))!;
      d.widgets.push({...widget(99,d.id),...clone(body)} as DashboardWidget);
      return clone(d);
    }
    throw new Error(`Unexpected POST ${path}`);
  });
  edge.apiPatch.mockImplementation(async (path: string, body: unknown) => {
    const m = /^\/api\/v1\/dashboards\/(\d+)(?:\/widgets\/(\d+)|\/(layout))?$/.exec(path);
    if (!m) throw new Error(`Unexpected PATCH ${path}`);
    const d = store.find((d) => d.id === Number(m[1]))!;
    if (m[2]) Object.assign(d.widgets.find((w) => w.id === Number(m[2]))!,clone(body));
    else if (m[3]) for (const l of body as Array<{id:number;x:number;y:number;w:number;h:number}>) {
      const {id,...layout} = l; d.widgets.find((w) => w.id === id)!.layout_json = layout;
    }
    else Object.assign(d,clone(body));
    return clone(d);
  });
  edge.apiPut.mockRejectedValue(new Error('Unexpected full widget replacement'));
  edge.apiDelete.mockRejectedValue(new Error('Unexpected DELETE'));
});
afterEach(() => { for (const q of clients.splice(0)) q.clear(); });

async function setup() {
  const qc = new QueryClient({defaultOptions:{queries:{retry:false,gcTime:0},mutations:{retry:false}}});
  clients.push(qc);
  renderWithProviders(<QueryClientProvider client={qc}>
    <V2ExecutorProvider execute={execute}><DashboardWorkspace hidePageHeader /></V2ExecutorProvider>
  </QueryClientProvider>);
  await screen.findByTestId('card-boundary-11');
  await waitFor(() => expect(screen.getByTestId('dashboard-add-widget')).toBeEnabled());
  return {qc,user:userEvent.setup()};
}
function context(id: number) {
  return JSON.parse(screen.getByTestId(`context-${id}`).textContent!) as {
    filters:Record<string,unknown>;window:{from:string;to:string}|null;selected:string[];required?:string[];
  };
}

describe('DashboardWorkspace orchestration', () => {
  it('switches A → B → A using each saved filter set and never commits old chart clicks to B', async () => {
    const {user} = await setup();
    await waitFor(() => expect(context(11).filters.customer).toEqual([101]));
    await user.click(screen.getByRole('button',{name:'Select Retail from chart'}));
    await user.click(screen.getByRole('button',{name:'Select week from chart'}));
    expect(context(11)).toMatchObject({filters:{customer:[101],channel:['Retail']},window:{from:'2026-09-28',to:'2026-10-04'}});
    expect(screen.getByTestId('dashboard-click-chip-period')).toBeInTheDocument();
    edge.commits.length = 0;
    await user.click(screen.getByTestId('dashboard-select-2'));
    await screen.findByTestId('card-boundary-21');
    expect(context(21)).toMatchObject({filters:{customer:[202]},window:windowB,selected:[]});
    expect(screen.queryByTestId('dashboard-click-chips')).not.toBeInTheDocument();
    const b = edge.commits.filter((c) => c.name === 'Board B');
    expect(b.length).toBeGreaterThan(0);
    for (const committed of b) {
      expect(committed.filters).toEqual({customer:[202]}); expect(committed.window).toEqual(windowB);
      expect(committed.selected).toEqual([]);
    }
    await user.click(screen.getByTestId('dashboard-select-1'));
    await screen.findByTestId('card-boundary-11');
    expect(context(11)).toMatchObject({filters:{customer:[101]},window:windowA,selected:[]});
  });

  it('retains an unsaved bar edit and chart selection through same-dashboard refetch with new object identities', async () => {
    const {user,qc} = await setup();
    fireEvent.change(screen.getByTestId('dashboard-filter-from'),{target:{value:'2026-07-05'}});
    await user.click(screen.getByRole('button',{name:'Select Retail from chart'}));
    expect(screen.getByTestId('dashboard-filter-save')).toBeEnabled();
    await act(async () => { await qc.invalidateQueries({queryKey:['dashboards']}); });
    expect(context(11)).toMatchObject({filters:{customer:[101],channel:['Retail']},window:{from:'2026-07-05',to:'2026-07-31'}});
    expect(screen.getByTestId('dashboard-filter-from')).toHaveValue('2026-07-05');
    expect(screen.getByTestId('dashboard-click-chip-channel')).toBeInTheDocument();
    await user.click(screen.getByTestId('dashboard-filter-save'));
    await waitFor(() => expect(edge.apiPatch).toHaveBeenCalledWith('/api/v1/dashboards/1',{
      filters_json:{date:{preset:'custom',from:'2026-07-05',to:'2026-07-31'},compare:'none',customer:[101]},
    }));
    // Transient chart clicks are not part of Save filters.
    expect(store[0].filters_json).not.toHaveProperty('channel');
  });

  it.each(['catalog absent','0048 storage absent'] as const)('keeps the v1 editor available when %s', async (mode) => {
    v2CatalogMissing = mode === 'catalog absent'; storageMissing = mode === '0048 storage absent';
    const {user} = await setup();
    expect(await screen.findByTestId('dashboard-v1-only-note')).toBeInTheDocument();
    expect(screen.queryByTestId('dashboard-filter-bar')).not.toBeInTheDocument();
    await user.click(screen.getByTestId('dashboard-add-widget'));
    expect(await screen.findByTestId('widget-editor')).toBeInTheDocument();
    expect(screen.queryByTestId('builder-editor')).not.toBeInTheDocument();
  });

  it('creates through the real v2 editor, reopens the saved widget, then PATCHes an edit', async () => {
    const {user} = await setup();
    await user.click(screen.getByTestId('dashboard-add-widget'));
    await screen.findByTestId('builder-editor');
    await user.click(screen.getByTestId('builder-editor-measure-dsi_sellout.units'));
    await user.type(screen.getByTestId('builder-editor-title'),'New units card');
    await user.click(screen.getByTestId('builder-editor-save'));
    await screen.findByTestId('card-boundary-99');
    const create = edge.apiPost.mock.calls.find(([path]) => path === '/api/v1/dashboards/1/widgets');
    expect(create?.[1]).toMatchObject({title:'New units card',visual:'kpi',
      definition_v2:{v:1,query:{measures:['dsi_sellout.units']}},layout_json:{x:0,y:8,w:6,h:8}});
    await user.click(screen.getByRole('button',{name:'Edit widget 99'}));
    await screen.findByTestId('builder-editor');
    expect(screen.getByTestId('builder-editor-title')).toHaveValue('New units card');
    expect(screen.getByTestId('builder-editor-measure-dsi_sellout.units')).toHaveAttribute('aria-pressed','true');
    await user.clear(screen.getByTestId('builder-editor-title'));
    await user.type(screen.getByTestId('builder-editor-title'),'Renamed units card');
    await user.click(screen.getByTestId('builder-editor-save'));
    await waitFor(() => expect(edge.apiPatch).toHaveBeenCalledWith('/api/v1/dashboards/1/widgets/99',
      expect.objectContaining({title:'Renamed units card',definition_v2:expect.objectContaining({v:1})})));
    await waitFor(() => expect(screen.queryByTestId('builder-editor')).not.toBeInTheDocument());
    expect(store[0].widgets.find((w) => w.id === 99)?.title).toBe('Renamed units card');
  });

  it('keeps the editor open with a recoverable error when the save fails', async () => {
    const {user} = await setup();
    await user.click(screen.getByRole('button',{name:'Edit widget 11'}));
    await screen.findByTestId('builder-editor');
    edge.apiPatch.mockRejectedValueOnce(new Error('The saved query is refused'));
    await user.click(screen.getByTestId('builder-editor-save'));
    expect(await screen.findByText('The saved query is refused')).toBeInTheDocument();
    expect(screen.getByTestId('builder-editor')).toBeInTheDocument();
    expect(screen.getByTestId('builder-editor-save')).toBeEnabled();
  });

  it('adapts the grid layout callback to layout-only PATCH and keeps definitions/filter state', async () => {
    const {user} = await setup();
    await user.click(screen.getByRole('button',{name:'Select Retail from chart'}));
    await user.click(screen.getByRole('button',{name:'Commit moved layout'}));
    await waitFor(() => expect(edge.apiPatch).toHaveBeenCalledWith('/api/v1/dashboards/1/layout',[
      {id:11,x:2,y:7,w:6,h:8},
    ]));
    expect(edge.apiPut).not.toHaveBeenCalled();
    await waitFor(() => expect(store[0].widgets[0].layout_json).toEqual({x:2,y:7,w:6,h:8}));
    expect(store[0].widgets[0].definition_v2?.query.measures).toEqual(['dsi_sellout.units']);
    expect(context(11).filters).toEqual({customer:[101],channel:['Retail']});
  });

  it('creates an editable starter copy and selects its own required-filter context', async () => {
    const {user} = await setup();
    await user.click(screen.getByRole('button',{name:'Select Retail from chart'}));
    await user.click(screen.getByTestId('dashboard-create'));
    await user.click(await screen.findByTestId('dashboard-create-starter-account_overview'));
    await screen.findByTestId('card-boundary-31');
    expect(edge.apiPost).toHaveBeenCalledWith('/api/v1/dashboards/from-template',{key:'account_overview'});
    expect(screen.getByTestId('dashboard-template-chip')).toBeInTheDocument();
    expect(screen.getByTestId('dashboard-template-note')).toHaveTextContent('A copy you can edit');
    expect(context(31)).toMatchObject({filters:{},window:null,selected:[],required:['customer']});
    await user.click(screen.getByRole('button',{name:'Edit widget 31'}));
    expect(await screen.findByTestId('builder-editor')).toBeInTheDocument();
    expect(screen.getByTestId('builder-editor-title')).toHaveValue('Widget 31');
  });
});
```

Application notes:

* All fixtures are fictional. No setup helper reads settings, account data or a database.
* Do not mock useDashboardRun/buildRunContext or normaliseFilters: the switching/retention tests
  exist to falsify their integration. Do not pre-populate the dashboards cache: that would miss the
  initial asynchronous active-dashboard/saved-filter transition.
* The same-dashboard test uses a **network refetch** returning cloned objects with unchanged saved
  filters. It does not simulate refetch merely by rerendering identical props. A content-changing
  server filter update should have a separate test if conflict policy changes.
* The successful-save HTTP mock preserves the old API fields and writes only request fields. This
  permits reopening by server-returned data, rather than proving the editor can read its own state.
* Refusal preview/save assertions should remain explicit. Avoid snapshots, fixed sleeps, fake timers
  around React Query and retry-until-pass loops. The editor's existing 300ms debounce is acceptable
  under `waitFor`; no extra arbitrary delay is needed.
* Root's adapter tests should retain missing-route fallback coverage (404/405 → PUT) and prove a 500
  does not fallback. This file intentionally only tests callback adaptation, not duplicate adapter logic.

## Isolated browser harness suggestion (root owns configuration)

Keep production :3000, live `.next`, API and worker untouched. `apps/web/next.config.ts` needs one
optional env-controlled `distDir` (validated under `.tmp/` by root):

```ts
distDir: process.env.CIP_NEXT_DIST_DIR ?? '.next',
```

Use `apps/web/playwright.builder.config.ts`:

```ts
import { defineConfig, devices } from '@playwright/test';
export default defineConfig({
  testDir:'./e2e/builder-fixtures',
  testMatch:'**/*.spec.ts',
  fullyParallel:false, workers:1, retries:0, forbidOnly:!!process.env.CI,
  outputDir:'./.tmp/builder-playwright-results',
  reporter:'list',
  use:{ baseURL:'http://127.0.0.1:3106', trace:'retain-on-failure' },
  projects:[{name:'chromium',use:{...devices['Desktop Chrome']}}],
  webServer:{
    command:'pnpm exec next dev --port 3106 --hostname 127.0.0.1',
    url:'http://127.0.0.1:3106/design-lab/builder',
    reuseExistingServer:false, timeout:120000,
    env:{ ...process.env, CIP_NEXT_DIST_DIR:'.tmp/builder-next', CIP_DISABLE_NEXT_API_PROXY:'true' },
  },
});
```

This is a suggested config, not an executed server command. For fixture specs use an allowlist:
only same-origin `/design-lab/builder`, `/_next/**`, asset/font/icon paths and explicit fixture API
responses. Reject `/api/v1/**` by default with 503 or abort; do not let unexpected requests escape
to the API proxy. For a full workspace browser scenario, use page.route fictional dashboard/catalog/
template responses and v2 execute responses (no authentication or database required). Keep all test
actions on fixture/local routes. The current lab builder route renders cards/filter bar/starters
but not DashboardWorkspace or the editor, so it cannot prove workspace switching or save/reopen;
the component tests above cover that. Root may add a fixture-only workspace lab panel if browser
proof of those journeys is required. Browser fixture data must have no real customer data.

Lowest useful validation order after applying: this component file, focused builder/API unit tests,
TypeScript/lint, then sparse browser tests for real charts, keyboard controls, narrow layout and PNG.
No tests from this proposal were executed and no rendered UI verification is claimed.
