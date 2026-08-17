import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { SemanticCatalogOverlayPanel } from './SemanticCatalogOverlayPanel';

const apiGet = vi.fn();
const apiPut = vi.fn();

vi.mock('@/lib/api', () => ({
  apiGet: (...args: unknown[]) => apiGet(...args),
  apiPut: (...args: unknown[]) => apiPut(...args),
  safeDisplayError: (err: unknown) => String(err),
}));

const payload = {
  tenant_id: 'default',
  overlay: { metrics: {}, composed: {} },
  compose_ops: ['ratio', 'alias'],
  base_metrics: [
    {
      id: 'A1-01',
      key: 'fill_rate',
      label: 'Fill rate',
      allowed_grains: [['period'], ['period', 'bu']],
      fact_family: 'a1',
      handler_backed: true,
      locked: {
        formula: 'Σ min(shipped, planned) / Σ planned',
        source_facts: ['lineup_plan_qty'],
        owner_surface: 'plan-vs-executed',
      },
    },
    {
      id: 'A1-01b',
      key: 'line_hit_rate',
      label: 'Line-hit rate',
      allowed_grains: [['period'], ['period', 'bu']],
      fact_family: 'a1',
      handler_backed: true,
      locked: {
        formula: 'share of in-plan lines',
        source_facts: ['lineup_plan_qty'],
        owner_surface: 'plan-vs-executed',
      },
    },
  ],
};

function wrap(ui: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe('SemanticCatalogOverlayPanel', () => {
  beforeEach(() => {
    apiGet.mockReset();
    apiPut.mockReset();
    apiGet.mockResolvedValue(payload);
    apiPut.mockResolvedValue({ ...payload, overlay: { metrics: { fill_rate: { label: 'On-time fill' } } } });
  });

  it('renders the catalog editor and saves a relabel via PUT', async () => {
    const user = userEvent.setup();
    wrap(<SemanticCatalogOverlayPanel />);
    expect(await screen.findByTestId('semantic-overlay-heading')).toHaveTextContent('Semantic catalog');
    expect(screen.queryByText('weighted_sum')).not.toBeInTheDocument();
    const label = await screen.findByTestId('semantic-overlay-label-fill_rate');
    await user.clear(label);
    await user.type(label, 'On-time fill');
    await user.click(screen.getByTestId('semantic-overlay-save'));
    await waitFor(() => expect(apiPut).toHaveBeenCalled());
    const [, body] = apiPut.mock.calls[0] as [string, { metrics: { fill_rate: { label: string } } }];
    expect(apiPut.mock.calls[0][0]).toBe('/api/v1/semantics/overlay');
    expect(body.metrics.fill_rate.label).toBe('On-time fill');
    expect(body.metrics.fill_rate).not.toHaveProperty('formula');
  });

  it('composed op select offers only ratio and alias', async () => {
    const user = userEvent.setup();
    wrap(<SemanticCatalogOverlayPanel />);
    await screen.findByTestId('semantic-overlay-heading');
    await user.click(screen.getByTestId('semantic-overlay-add-composed'));
    await user.click(screen.getByLabelText('Op'));
    expect(await screen.findByRole('option', { name: 'ratio' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'alias' })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: /weighted/i })).not.toBeInTheDocument();
  });
});
