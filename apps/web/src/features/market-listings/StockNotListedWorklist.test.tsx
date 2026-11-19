import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { apiGet } from '@/lib/api';

import { StockNotListedWorklist } from './StockNotListedWorklist';

const apiState = vi.hoisted(() => ({
  mode: 'ok' as 'ok' | 'pending' | 'error' | 'unavailable' | 'empty' | 'truncated',
  scopedMode: 'ok' as 'ok' | 'pending' | 'error' | 'unavailable' | 'empty',
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

const LATE_ACCOUNT = { id: 9, customer_code: 'c9', customer_name: 'Zulu & Co' };
const LATE_ROW = { ...ROW, customer_id: 9, customer_name: 'Zulu & Co', customer_code: 'c9', stock_on_hand: 99 };

vi.mock('@/lib/api', () => ({
  apiGet: vi.fn(async (url: string) => {
    const params = new URL(url, 'https://example.test').searchParams;
    if (url.startsWith('/api/v1/customers?')) {
      return {
        items: params.get('q')?.includes('Zulu')
          ? [LATE_ACCOUNT]
          : [{ id: 3, customer_code: 'c3', customer_name: 'Account Three' }],
      };
    }
    if (params.has('customer_id')) {
      if (apiState.scopedMode === 'pending') return new Promise(() => undefined);
      if (apiState.scopedMode === 'error') throw new Error('account read down');
      if (apiState.scopedMode === 'unavailable') return { data_unavailable: true, rows: [], total: 0 };
      if (apiState.scopedMode === 'empty') return { data_unavailable: false, rows: [], total: 0 };
      return { data_unavailable: false, rows: [LATE_ROW], total: 1, truncated: false };
    }
    if (apiState.mode === 'pending') return new Promise(() => undefined);
    if (apiState.mode === 'error') throw new Error('down');
    if (apiState.mode === 'unavailable') return { data_unavailable: true, rows: [], total: 0 };
    if (apiState.mode === 'empty') return { data_unavailable: false, rows: [], total: 0, truncated: false };
    if (apiState.mode === 'truncated') return { data_unavailable: false, rows: [ROW], total: 9, truncated: true };
    return { data_unavailable: false, rows: [ROW], total: 1, truncated: false };
  }),
}));

function renderList() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(
    <QueryClientProvider client={client}>
      <StockNotListedWorklist />
    </QueryClientProvider>,
  );
  return { ...view, client };
}

async function selectLateAccount(user: ReturnType<typeof userEvent.setup>) {
  const picker = screen.getByRole('combobox', { name: 'Account' });
  await user.click(picker);
  await user.type(picker, 'Zulu & Co');
  await user.click(await screen.findByRole('option', { name: 'Zulu & Co' }));
}

describe('StockNotListedWorklist', () => {
  beforeEach(() => {
    apiState.mode = 'ok';
    apiState.scopedMode = 'ok';
    vi.mocked(apiGet).mockClear();
  });

  it('shows each row with its coverage reason', async () => {
    renderList();
    const row = await screen.findByTestId('stock-not-listed-row-3-81');
    expect(row).toHaveTextContent('Account Three');
    expect(row).toHaveTextContent('SKU-81');
    expect(row).toHaveTextContent('Not searched');
    expect(row).toHaveTextContent('2026-11-09');
    expect(within(row).getByRole('cell', { name: '12' })).toBeInTheDocument();
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

  it('shows an honest empty result for the selected scope', async () => {
    apiState.mode = 'empty';
    renderList();
    expect(await screen.findByTestId('stock-not-listed-empty')).toHaveTextContent(
      'No stocked products without a watched listing in this scope.',
    );
  });

  it('says when rows were cut off', async () => {
    apiState.mode = 'truncated';
    renderList();
    const notice = await screen.findByTestId('stock-not-listed-truncated');
    expect(notice).toHaveTextContent('Showing 1 of 9');
    expect(notice).toHaveTextContent('ordered by customer name, then highest stock first');
    expect(notice).toHaveTextContent('Select an account');
  });

  it('searches beyond the truncated rows, scopes the request and cache, and clears back to all', async () => {
    apiState.mode = 'truncated';
    const user = userEvent.setup();
    const { client } = renderList();
    await screen.findByTestId('stock-not-listed-truncated');

    await selectLateAccount(user);
    await waitFor(() => expect(apiGet).toHaveBeenCalledWith(
      '/api/v1/customers?page=1&page_size=25&q=Zulu%20%26%20Co',
      { signal: expect.any(AbortSignal) },
    ));
    expect(apiGet).toHaveBeenCalledWith(
      '/api/v1/listing-capture/stock-not-listed?customer_id=9',
      { signal: expect.any(AbortSignal) },
    );
    const row = await screen.findByTestId('stock-not-listed-row-9-81');
    expect(row).toHaveTextContent('Zulu & Co');
    expect(within(row).getByRole('cell', { name: '99' })).toBeInTheDocument();
    expect(screen.queryByTestId('stock-not-listed-row-3-81')).not.toBeInTheDocument();
    expect(screen.queryByTestId('stock-not-listed-truncated')).not.toBeInTheDocument();
    expect(client.getQueryData(['listing-capture', 'stock-not-listed', 9])).toMatchObject({ rows: [LATE_ROW] });
    expect(client.getQueryData(['listing-capture', 'stock-not-listed', null])).toMatchObject({ rows: [ROW] });

    // MUI shows the clear indicator only on hover/focus; target it by its title.
    await user.click(screen.getByTitle('Clear'));
    expect(await screen.findByTestId('stock-not-listed-row-3-81')).toBeInTheDocument();
    expect(screen.queryByTestId('stock-not-listed-row-9-81')).not.toBeInTheDocument();
    expect(screen.getByTestId('stock-not-listed-truncated')).toBeInTheDocument();
  });

  it.each([
    ['pending', 'loading'],
    ['error', 'error'],
    ['unavailable', 'error'],
    ['empty', 'empty'],
  ] as const)('keeps the scoped %s state honest without showing another account', async (mode, state) => {
    const user = userEvent.setup();
    renderList();
    await screen.findByTestId('stock-not-listed-row-3-81');
    apiState.scopedMode = mode;

    await selectLateAccount(user);
    expect(await screen.findByTestId(`stock-not-listed-${state}`)).toBeInTheDocument();
    expect(screen.queryByTestId('stock-not-listed-row-3-81')).not.toBeInTheDocument();
    expect(screen.queryByTestId('stock-not-listed-table')).not.toBeInTheDocument();
    if (state !== 'empty') {
      expect(screen.queryByTestId('stock-not-listed-empty')).not.toBeInTheDocument();
    }
  });
});
