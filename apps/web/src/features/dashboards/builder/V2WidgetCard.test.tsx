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
