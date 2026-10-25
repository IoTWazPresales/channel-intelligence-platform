import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { builderCatalog as catalog, visualWidgets } from '@/design-lab/fixtures/builder';
import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { V2ExecutorProvider } from './BuilderData';
import { NO_FILTERS, type DashboardRunContext } from './runContext';
import type { V2Response } from './types';
import { V2WidgetCard } from './V2WidgetCard';
import type { WidgetAction } from './WidgetMenu';

// Keep the real query observer and card; replace chart geometry and menu presentation only.
vi.mock('./V2WidgetBody', () => ({ V2WidgetBody: () => <div>Chart</div> }));
vi.mock('./WidgetMenu', () => ({ WidgetMenu: ({ actions }: { actions: WidgetAction[] }) => <>
  {actions.filter((a) => a.id.startsWith('export-')).map((a) => <button key={a.id} disabled={Boolean(a.disabledReason)} onClick={a.onClick}>{a.label}</button>)}
</> }));

describe('widget export request identity', () => {
  it('waits for the matching previous answer before enabling comparison exports', async () => {
    const widget = visualWidgets.find((w) => w.visual === 'bar')!;
    const answer: V2Response = { ok: true, columns: [], rows: [], totals: {}, truncated: false, refusals: [] };
    let finish!: (r: V2Response) => void;
    const execute = vi.fn().mockResolvedValueOnce(answer).mockImplementationOnce(() => new Promise<V2Response>((resolve) => { finish = resolve; }));
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    renderWithProviders(<QueryClientProvider client={qc}><V2ExecutorProvider execute={execute}>
      <V2WidgetCard widget={widget} def={{ ...widget.definition_v2!, display: { compare: true } }} catalog={catalog} ctx={{ ...NO_FILTERS, window: { from: '2026-07-01', to: '2026-07-31' }, compare: { from: '2026-05-31', to: '2026-06-30' } }} dashboardName="Board" actions={{}} />
    </V2ExecutorProvider></QueryClientProvider>);
    await waitFor(() => expect(execute).toHaveBeenCalledTimes(2));
    expect(screen.getByRole('button', { name: 'Export CSV' })).toBeDisabled();
    await act(async () => { finish(answer); });
    await waitFor(() => expect(screen.getByRole('button', { name: 'Export CSV' })).toBeEnabled());
    qc.clear();
  });
  it('compares a fixed widget window against its own previous period, not the dashboard period', async () => {
    const widget = visualWidgets[0];
    const execute = vi.fn().mockResolvedValue({ ok: true, columns: [], rows: [], totals: {}, truncated: false, refusals: [] });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const def = { ...widget.definition_v2!, display: { kpi: { compare: true } }, dashboard: { fixed_window: { from: '2026-01-01', to: '2026-01-31' } } };
    renderWithProviders(<QueryClientProvider client={qc}><V2ExecutorProvider execute={execute}>
      <V2WidgetCard widget={widget} def={def} catalog={catalog} ctx={{ ...NO_FILTERS, window: { from: '2026-07-01', to: '2026-07-31' }, compare: { from: '2026-05-31', to: '2026-06-30' }, compareMode: 'previous_period' }} dashboardName="Board" actions={{}} />
    </V2ExecutorProvider></QueryClientProvider>);
    await waitFor(() => expect(execute).toHaveBeenCalledTimes(2));
    expect(execute.mock.calls.map(([req]) => req.period)).toEqual(expect.arrayContaining([
      { from: '2026-01-01', to: '2026-01-31' }, { from: '2025-12-01', to: '2025-12-31' },
    ]));
    qc.clear();
  });
  it('keeps the old drawing during refresh but disables exports until the current answer arrives, and clears blocked data', async () => {
    const widget = visualWidgets.find((w) => w.visual === 'bar')!;
    const answer: V2Response = { ok: true, columns: [], rows: [], totals: {}, truncated: false, refusals: [] };
    let finish!: (r: V2Response) => void;
    const execute = vi.fn().mockResolvedValueOnce(answer).mockImplementationOnce(() => new Promise<V2Response>((resolve) => { finish = resolve; }));
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const ui = (ctx: DashboardRunContext) => <QueryClientProvider client={qc}><V2ExecutorProvider execute={execute}>
      <V2WidgetCard widget={widget} def={widget.definition_v2!} catalog={catalog} ctx={ctx} dashboardName="Board" actions={{}} />
    </V2ExecutorProvider></QueryClientProvider>;
    const view = renderWithProviders(ui(NO_FILTERS));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Export CSV' })).toBeEnabled());
    view.rerender(ui({ ...NO_FILTERS, filters: { customer: [2] }, filterCaption: 'Customer 2' }));
    await waitFor(() => expect(execute).toHaveBeenCalledTimes(2));
    expect(screen.getByText('Chart')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Export CSV' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Export image (PNG)' })).toBeDisabled();
    await act(async () => { finish(answer); });
    await waitFor(() => expect(screen.getByRole('button', { name: 'Export CSV' })).toBeEnabled());
    view.rerender(ui({ ...NO_FILTERS, filters: { customer: [] } }));
    expect(screen.getByRole('button', { name: 'Export CSV' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Export image (PNG)' })).toBeDisabled();
    expect(screen.queryByText('Chart')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Export CSV' }));
    expect(execute).toHaveBeenCalledTimes(2);
    qc.clear();
  });
});
