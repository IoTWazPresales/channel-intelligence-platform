import React from 'react';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { StockNotListedWorklist } from './StockNotListedWorklist';

const apiState = vi.hoisted(() => ({
  mode: 'ok' as 'ok' | 'pending' | 'error' | 'unavailable' | 'empty' | 'truncated',
}));

const ROW = {
  customer_id: 3,
  customer_code: 'c3',
  customer_name: 'Account Three',
  product_id: 81,
  sku: 'SKU-81',
  product_name: 'Item 81',
  stock_on_hand: 12,
  stock_as_of: '2026-11-09',
  coverage: 'not_searched',
  next_step: 'No listing, proposal or search yet; add a listing or let discovery run.',
};

vi.mock('@/lib/api', () => ({
  apiGet: async () => {
    if (apiState.mode === 'pending') return new Promise(() => undefined);
    if (apiState.mode === 'error') throw new Error('down');
    if (apiState.mode === 'unavailable') return { data_unavailable: true, rows: [], total: 0 };
    if (apiState.mode === 'empty') return { data_unavailable: false, rows: [], total: 0, truncated: false };
    if (apiState.mode === 'truncated') return { data_unavailable: false, rows: [ROW], total: 9, truncated: true };
    return { data_unavailable: false, rows: [ROW], total: 1, truncated: false };
  },
}));

function renderList() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <StockNotListedWorklist />
    </QueryClientProvider>,
  );
}

describe('StockNotListedWorklist', () => {
  beforeEach(() => {
    apiState.mode = 'ok';
  });

  it('shows each row with its coverage reason', async () => {
    renderList();
    const row = await screen.findByTestId('stock-not-listed-row-3-81');
    expect(row).toHaveTextContent('Account Three');
    expect(row).toHaveTextContent('SKU-81');
    expect(row).toHaveTextContent('Not searched');
    expect(row).toHaveTextContent('2026-11-09');
  });

  it('is honest while loading, on error and when unavailable', async () => {
    apiState.mode = 'pending';
    const pending = renderList();
    expect(await screen.findByTestId('stock-not-listed-loading')).toBeInTheDocument();
    expect(screen.queryByTestId('stock-not-listed-empty')).not.toBeInTheDocument();
    pending.unmount();

    apiState.mode = 'error';
    const failed = renderList();
    expect(await screen.findByTestId('stock-not-listed-error')).toBeInTheDocument();
    expect(screen.queryByTestId('stock-not-listed-empty')).not.toBeInTheDocument();
    failed.unmount();

    apiState.mode = 'unavailable';
    renderList();
    expect(await screen.findByTestId('stock-not-listed-error')).toBeInTheDocument();
    expect(screen.queryByTestId('stock-not-listed-empty')).not.toBeInTheDocument();
  });

  it('says every stocked product is watched only after a complete empty read', async () => {
    apiState.mode = 'empty';
    renderList();
    expect(await screen.findByTestId('stock-not-listed-empty')).toBeInTheDocument();
  });

  it('says when rows were cut off', async () => {
    apiState.mode = 'truncated';
    renderList();
    expect(await screen.findByTestId('stock-not-listed-truncated')).toHaveTextContent('Showing 1 of 9');
  });
});
