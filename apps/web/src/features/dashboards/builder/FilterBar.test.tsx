import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { builderCatalog, fixtureResponse } from '@/design-lab/fixtures/builder';
import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { V2ExecutorProvider } from './BuilderData';
import { EMPTY_CLICKS } from './clickFilters';
import { DashboardFilterBar, DEFAULT_FILTERS, extraFilterKeys } from './FilterBar';

const catalog = {
  ...builderCatalog,
  breakdowns: [...builderCatalog.breakdowns,
    { id: 'category', label: 'Category', group: 'Product', kind: 'attribute' },
    { id: 'pending_attribute', label: 'Pending', group: 'Product', kind: 'attribute' }],
  models: builderCatalog.models.map((m) => m.id === 'dsi_sellout' ? { ...m, breakdowns: [...m.breakdowns, 'category'] } : m),
};

describe('additional dashboard attribute filters', () => {
  it('offers supported catalog attributes beyond the six primary controls', () => {
    expect(extraFilterKeys(catalog)).toEqual(['category']);
    expect(extraFilterKeys(null)).toEqual([]);
  });

  it('keeps a saved additional filter visible and exposes it in the phone drawer', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
    renderWithProviders(<QueryClientProvider client={qc}><V2ExecutorProvider execute={async (r) => fixtureResponse(r)}>
      <DashboardFilterBar catalog={catalog} value={{ ...DEFAULT_FILTERS, category: ['Notebook'] }} onChange={vi.fn()} models={['dsi_sellout']}
        clicks={EMPTY_CLICKS} onRemoveChip={vi.fn()} onClearPeriod={vi.fn()} onClearChips={vi.fn()} forcePhone />
    </V2ExecutorProvider></QueryClientProvider>);
    fireEvent.click(screen.getByTestId('dashboard-filters-open'));
    expect(await screen.findByTestId('dashboard-filter-category')).toBeInTheDocument();
    expect(screen.getByTestId('dashboard-more-filters')).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByTestId('dashboard-filters-open')).toHaveTextContent('Filters (1)');
    qc.clear();
  });
});
