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
    widget: DashboardWidget; ctx: DashboardRunContext; dashboardName: string; onEdit: () => void; onPromote: () => void;
  }) => {
    const snap = { name: p.dashboardName, widget: p.widget.id,
      filters: p.ctx.filters, window: p.ctx.window, selected: p.ctx.selectedKeys, required:p.ctx.required };
    useLayoutEffect(() => { edge.commits.push(JSON.parse(JSON.stringify(snap))); });
    return h('section', { 'data-testid': `card-boundary-${p.widget.id}` },
      h('output', { 'data-testid': `context-${p.widget.id}` }, JSON.stringify(snap)),
      h('button', { type:'button', onClick: p.onEdit }, `Edit widget ${p.widget.id}`),
      h('button', { type:'button', onClick: p.onPromote }, `Promote widget ${p.widget.id}`),
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
    if (/\/widgets\/\d+\/promote$/.test(path)) return { saved_report_id: 77 };
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
  it('promotes the effective unsaved bar and chart question with own-filter intersection, sort and limit', async () => {
    Object.assign(store[0].widgets[0].definition_v2!.query, {
      filters: { customer: [101, 303], channel: ['Retail', 'Wholesale'] },
      period: { grain: 'week' }, sort: { by: 'dsi_sellout.units', dir: 'asc' }, limit: 1,
    });
    const { user } = await setup();
    fireEvent.change(screen.getByTestId('dashboard-filter-from'), { target: { value: '2026-07-05' } });
    await user.click(screen.getByRole('button', { name: 'Select Retail from chart' }));
    await user.click(screen.getByRole('button', { name: 'Promote widget 11' }));
    await waitFor(() => expect(edge.apiPost).toHaveBeenCalledWith('/api/v1/dashboards/1/widgets/11/promote', {
      execution: { measures: ['dsi_sellout.units'], breakdowns: ['customer'],
        filters: { customer: [101], channel: ['Retail'] },
        period: { grain: 'week', from: '2026-07-05', to: '2026-07-31' },
        sort: { by: 'dsi_sellout.units', dir: 'asc' }, limit: 1 },
    }));
    expect(await screen.findByTestId('dashboard-promote-result')).toHaveTextContent(/fixed dates.*2026-07-05.*2026-07-31/i);
    expect(edge.apiPatch).not.toHaveBeenCalled();
  });

  it('promotes chart-selected dates and honours widget fixed dates and ignored filters', async () => {
    store[0].widgets.push(widget(12, 1));
    store[0].widgets[1].definition_v2!.dashboard = {
      ignore_filters: ['customer', 'channel'], fixed_window: { from: '2026-01-01', to: '2026-01-31' },
    };
    const { user } = await setup();
    await user.click(screen.getAllByRole('button', { name: 'Select Retail from chart' })[0]);
    await user.click(screen.getAllByRole('button', { name: 'Select week from chart' })[0]);
    await user.click(screen.getByRole('button', { name: 'Promote widget 11' }));
    await waitFor(() => expect(edge.apiPost).toHaveBeenCalledWith('/api/v1/dashboards/1/widgets/11/promote', {
      execution: { measures: ['dsi_sellout.units'], breakdowns: ['customer'],
        filters: { customer: [101], channel: ['Retail'] }, period: { from: '2026-09-28', to: '2026-10-04' } },
    }));
    await user.click(screen.getByRole('button', { name: 'Promote widget 12' }));
    await waitFor(() => expect(edge.apiPost).toHaveBeenCalledWith('/api/v1/dashboards/1/widgets/12/promote', {
      execution: { measures: ['dsi_sellout.units'], breakdowns: ['customer'], period: { from: '2026-01-01', to: '2026-01-31' } },
    }));
  });

  it.each(['required', 'empty intersection', 'catalog unavailable'] as const)('refuses promotion with %s rather than saving a different question', async (mode) => {
    if (mode === 'required') store[0].filters_json = { ...store[0].filters_json!, customer: [], required: ['customer'] };
    if (mode === 'empty intersection') store[0].widgets[0].definition_v2!.query.filters = { customer: [303] };
    if (mode === 'catalog unavailable') v2CatalogMissing = true;
    const { user } = await setup();
    await user.click(screen.getByRole('button', { name: 'Promote widget 11' }));
    expect(await screen.findByTestId('dashboard-promote-error')).toBeInTheDocument();
    expect(edge.apiPost.mock.calls.filter(([path]) => path.endsWith('/promote'))).toHaveLength(0);
  });

  it('keeps legacy widget promotion body-free and shows server refusals', async () => {
    delete store[0].widgets[0].definition_v2;
    const { user } = await setup();
    edge.apiPost.mockRejectedValueOnce(new Error('Choose dates before saving this report'));
    await user.click(screen.getByRole('button', { name: 'Promote widget 11' }));
    await waitFor(() => expect(edge.apiPost).toHaveBeenCalledWith('/api/v1/dashboards/1/widgets/11/promote'));
    expect(await screen.findByTestId('dashboard-promote-error')).toHaveTextContent('Choose dates before saving this report');
  });

  it('clears hidden own filters when changing to another data model', async () => {
    store[0].widgets[0].definition_v2!.query.filters = { distributor: [12] };
    const { user } = await setup();
    await user.click(screen.getByRole('button', { name: 'Edit widget 11' }));
    await screen.findByTestId('builder-editor');
    await user.click(screen.getByTestId('builder-editor-measure-dsi_sellout.units'));
    await user.click(screen.getByTestId('builder-editor-measure-cst_sellthrough.units'));
    await waitFor(() => expect(screen.queryByTestId('builder-editor-filter-distributor')).not.toBeInTheDocument());
    await user.click(screen.getByTestId('builder-editor-save'));
    await waitFor(() => expect(edge.apiPatch).toHaveBeenCalledWith('/api/v1/dashboards/1/widgets/11', expect.objectContaining({
      definition_v2: expect.objectContaining({ query: expect.objectContaining({ measures: ['cst_sellthrough.units'] }) }),
    })));
    const saved = edge.apiPatch.mock.calls.find(([p]) => p === '/api/v1/dashboards/1/widgets/11')?.[1];
    expect(saved.definition_v2.query.filters).toBeUndefined();
  });
  it('switches A â†’ B â†’ A using each saved filter set and never commits old chart clicks to B', async () => {
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
    fireEvent.change(screen.getByTestId('builder-editor-title'), { target: { value: 'New units card' } });
    await user.click(screen.getByTestId('builder-editor-save'));
    await screen.findByTestId('card-boundary-99');
    await waitFor(() => expect(screen.queryByTestId('builder-editor')).not.toBeInTheDocument());
    const create = edge.apiPost.mock.calls.find(([path]) => path === '/api/v1/dashboards/1/widgets');
    expect(create?.[1]).toMatchObject({title:'New units card',visual:'kpi',
      definition_v2:{v:1,query:{measures:['dsi_sellout.units']}},layout_json:{x:0,y:8,w:6,h:8}});
    await user.click(screen.getByRole('button',{name:'Edit widget 99'}));
    await screen.findByTestId('builder-editor');
    expect(screen.getByTestId('builder-editor-title')).toHaveValue('New units card');
    expect(screen.getByTestId('builder-editor-measure-dsi_sellout.units')).toHaveAttribute('aria-pressed','true');
    fireEvent.change(screen.getByTestId('builder-editor-title'), { target: { value: 'Renamed units card' } });
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

  it('saves and reopens explicit widget filter exceptions and fixed dates through the real editor', async () => {
    const {user} = await setup();
    await user.click(screen.getByRole('button', { name: 'Edit widget 11' }));
    await screen.findByTestId('builder-editor');
    await user.click(screen.getByText('Dashboard filter exceptions'));
    await user.click(screen.getByRole('checkbox', { name: 'Ignore dashboard customer' }));
    await user.click(screen.getByRole('checkbox', { name: 'Use fixed dates for this widget' }));
    fireEvent.change(screen.getByTestId('builder-editor-fixed-from'), { target: { value: '2026-01-01' } });
    fireEvent.change(screen.getByTestId('builder-editor-fixed-to'), { target: { value: '2026-01-31' } });
    await user.click(screen.getByTestId('builder-editor-save'));
    await waitFor(() => expect(screen.queryByTestId('builder-editor')).not.toBeInTheDocument());
    expect(store[0].widgets[0].definition_v2?.dashboard).toEqual({ ignore_filters: ['customer'], fixed_window: { from: '2026-01-01', to: '2026-01-31' } });
    await user.click(screen.getByRole('button', { name: 'Edit widget 11' }));
    await screen.findByTestId('builder-editor');
    await user.click(screen.getByText('Dashboard filter exceptions'));
    expect(screen.getByRole('checkbox', { name: 'Ignore dashboard customer' })).toBeChecked();
    expect(screen.getByTestId('builder-editor-fixed-from')).toHaveValue('2026-01-01');
    expect(screen.getByTestId('builder-editor-fixed-to')).toHaveValue('2026-01-31');
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
