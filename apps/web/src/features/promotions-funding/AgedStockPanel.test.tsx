import React from 'react';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { AgedStockPanel } from './AgedStockPanel';

const apiGet = vi.fn(async (_url: string, _init?: unknown) => ({
  lines: [
    {
      customer_id: 3,
      customer_name: 'Northwind Stores',
      product_id: 9,
      product_name: 'Monitor',
      site_label: 'North',
      stock_on_hand: 12,
      suggestions: ['promote', 'move', 'return'],
      suggestion_executed: false,
      executed_actions: [],
    },
  ],
  truncated: false,
}));

const apiPost = vi.fn(async (url: string, _body?: unknown) => {
  if (url.endsWith('/auto-propose')) return { created: [{ case_id: 11 }], skipped: [{ product_id: 10 }] };
  return { created: true, case_id: 5 };
});

vi.mock('@/lib/api', () => ({
  apiGet: (url: string, init?: unknown) => apiGet(url, init),
  apiPost: (url: string, body?: unknown) => apiPost(url, body),
}));

describe('AgedStockPanel', () => {
  it('lists a slow line and sends promote without creating anything on view', async () => {
    const onOpen = vi.fn();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    renderWithProviders(
      <QueryClientProvider client={qc}>
        <AgedStockPanel onOpen={onOpen} />
      </QueryClientProvider>,
    );

    expect(await screen.findByText(/Monitor · North · 12 on hand/)).toBeInTheDocument();
    expect(apiPost).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId('aged-stock-promote-9'));
    await waitFor(() => {
      expect(apiPost).toHaveBeenCalledWith('/api/v1/cpor/intelligence/promo-plan-draft/aged-stock-action', {
        customer_id: 3,
        product_id: 9,
        action: 'promote',
        site_label: 'North',
      });
    });
    await waitFor(() => expect(onOpen).toHaveBeenCalledWith(5));
  });

  it('names the customer on each row so two customers are told apart', async () => {
    apiGet.mockResolvedValueOnce({
      lines: [
        {
          customer_id: 3,
          customer_name: 'Northwind Stores',
          product_id: 9,
          product_name: 'Monitor',
          site_label: 'Main',
          stock_on_hand: 12,
          suggestions: ['promote'],
          suggestion_executed: false,
          executed_actions: [],
        },
        {
          customer_id: 4,
          customer_name: 'Southgate Retail',
          product_id: 9,
          product_name: 'Monitor',
          site_label: 'Main',
          stock_on_hand: 12,
          suggestions: ['promote'],
          suggestion_executed: false,
          executed_actions: [],
        },
      ],
      truncated: false,
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    renderWithProviders(
      <QueryClientProvider client={qc}>
        <AgedStockPanel />
      </QueryClientProvider>,
    );
    // Same product, same site label, same stock: only the customer name tells the rows apart.
    expect(await screen.findByTestId('aged-stock-customer-3-9-Main')).toHaveTextContent('Northwind Stores');
    expect(screen.getByTestId('aged-stock-customer-4-9-Main')).toHaveTextContent('Southgate Retail');
  });

  it('raises drafts from the list', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    renderWithProviders(
      <QueryClientProvider client={qc}>
        <AgedStockPanel />
      </QueryClientProvider>,
    );
    await screen.findByText(/Monitor/);
    fireEvent.click(screen.getByTestId('aged-stock-raise'));
    await waitFor(() => {
      expect(apiPost).toHaveBeenCalledWith('/api/v1/cpor/intelligence/promo-plan-draft/auto-propose', {});
    });
    expect(await screen.findByTestId('aged-stock-raise-result')).toHaveTextContent('1 draft opened · 1 skipped');
  });
});
