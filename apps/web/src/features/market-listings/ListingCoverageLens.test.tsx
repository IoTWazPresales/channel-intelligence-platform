import React from 'react';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ListingCoverageLens } from './ListingCoverageLens';

const apiState = vi.hoisted(() => ({
  mode: 'ok' as 'ok' | 'pending' | 'error' | 'unavailable' | 'empty',
}));

vi.mock('@/lib/api', () => ({
  apiGet: async () => {
    if (apiState.mode === 'pending') return new Promise(() => undefined);
    if (apiState.mode === 'error') throw new Error('capture health down');
    if (apiState.mode === 'unavailable') {
      return { data_unavailable: false, coverage: { data_unavailable: true, customers: [] } };
    }
    if (apiState.mode === 'empty') return { data_unavailable: false, coverage: { data_unavailable: false, customers: [] } };
    return {
      data_unavailable: false,
      coverage: {
        data_unavailable: false,
        customers: [
          {
            customer_id: 7,
            customer_code: 'c7',
            customer_name: 'Counter Seven',
            reported: 2,
            watched: 1,
            awaiting_steward: 0,
            failing: 1,
            not_found: 0,
            not_searched: 0,
          },
        ],
      },
    };
  },
}));

function renderLens() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ListingCoverageLens />
    </QueryClientProvider>,
  );
}

describe('ListingCoverageLens states', () => {
  beforeEach(() => {
    apiState.mode = 'ok';
  });

  it('says it is loading, not that there are no products, while the read is pending', async () => {
    apiState.mode = 'pending';
    renderLens();
    expect(await screen.findByTestId('listing-coverage-loading')).toBeInTheDocument();
    expect(screen.queryByTestId('listing-coverage-empty')).not.toBeInTheDocument();
  });

  it('shows only the warning when the read fails', async () => {
    apiState.mode = 'error';
    renderLens();
    expect(await screen.findByTestId('listing-coverage-error')).toBeInTheDocument();
    expect(screen.queryByTestId('listing-coverage-empty')).not.toBeInTheDocument();
    expect(screen.queryByTestId('listing-coverage-loading')).not.toBeInTheDocument();
  });

  it('shows only the warning when coverage is unavailable and empty', async () => {
    apiState.mode = 'unavailable';
    renderLens();
    expect(await screen.findByTestId('listing-coverage-error')).toBeInTheDocument();
    expect(screen.queryByTestId('listing-coverage-empty')).not.toBeInTheDocument();
  });

  it('says no reported products only after a complete empty read', async () => {
    apiState.mode = 'empty';
    renderLens();
    expect(await screen.findByTestId('listing-coverage-empty')).toBeInTheDocument();
    expect(screen.queryByTestId('listing-coverage-error')).not.toBeInTheDocument();
  });

  it('renders rows after a good read', async () => {
    renderLens();
    expect(await screen.findByTestId('listing-coverage-row-7')).toBeInTheDocument();
    expect(screen.queryByTestId('listing-coverage-loading')).not.toBeInTheDocument();
  });
});
