import React from 'react';
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { PromoPlanBuilderPanel } from '@/app/(app)/promotions/PromoPlanBuilderPanel';

import { AgedStockPanel } from './AgedStockPanel';

// PR #122 round 2, B1: the two remaining case-creation flows on the planner page ("Raise promotion
// drafts" and the embedded "Create promotion plan") must refresh the calendar-clash summary and the
// exact case counts (`/cpor/cases/counts`) that the cards read, inside their freshness window.

vi.mock('@/components/EnterpriseDataGrid', () => ({ EnterpriseDataGrid: () => <div /> }));
vi.mock('@/features/commercial-planner/EntitySearchAutocomplete', () => ({
  EntitySearchAutocomplete: () => null,
}));

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock('@/lib/api', () => ({
  apiGet: mocks.get,
  apiPost: mocks.post,
  apiPostFormData: vi.fn(),
  apiPatch: vi.fn(),
  apiPut: vi.fn(),
  apiDelete: vi.fn(),
  apiDownloadBlob: vi.fn(),
}));

const TODAY = '2026-11-19';
let clashFetches = 0;
let countFetches = 0;

/** Stands in for the planner cards: same keys and the planner's freshness, counting fetches. */
function CardProbes() {
  const clash = useQuery({
    queryKey: ['customer-calendar', 'clash-summary', TODAY],
    queryFn: async () => {
      clashFetches += 1;
      return { clash_count: clashFetches };
    },
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });
  const counts = useQuery({
    queryKey: ['cpor', 'cases', 'counts', 'base'],
    queryFn: async () => {
      countFetches += 1;
      return { total_current: countFetches };
    },
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });
  return (
    <>
      <span data-testid="clash-probe">{clash.data?.clash_count ?? 'loading'}</span>
      <span data-testid="counts-probe">{counts.data?.total_current ?? 'loading'}</span>
    </>
  );
}

function retainedClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

async function probesLoaded() {
  await waitFor(() => expect(screen.getByTestId('clash-probe')).toHaveTextContent('1'));
  await waitFor(() => expect(screen.getByTestId('counts-probe')).toHaveTextContent('1'));
}

async function probesRefetched() {
  await waitFor(() => expect(screen.getByTestId('clash-probe')).toHaveTextContent('2'));
  await waitFor(() => expect(screen.getByTestId('counts-probe')).toHaveTextContent('2'));
  expect(clashFetches).toBe(2);
  expect(countFetches).toBe(2);
}

beforeEach(() => {
  vi.clearAllMocks();
  clashFetches = 0;
  countFetches = 0;
  mocks.get.mockImplementation(async (url: string) => {
    if (url.includes('/promo-plan-draft/aged-stock')) return { lines: [], truncated: false };
    if (url.startsWith('/api/v1/cpor/intelligence/promo-plan-draft?')) {
      return {
        lines: [{ row_key: 'r1', product_id: 9, product_name: 'Line one', suggested_estimate_qty: 4 }],
        budget_check: {},
        comparables: { count: 0 },
      };
    }
    return {};
  });
});

describe('case creation refreshes the clash summary and case counts (B1)', () => {
  it('"Raise promotion drafts" refetches both inside the freshness window', async () => {
    mocks.post.mockResolvedValue({ created: [{ case_id: 41 }], skipped: [] });
    const qc = retainedClient();
    render(
      <QueryClientProvider client={qc}>
        <CardProbes />
        <AgedStockPanel />
      </QueryClientProvider>,
    );
    await probesLoaded();
    fireEvent.click(screen.getByTestId('aged-stock-raise'));
    await waitFor(() =>
      expect(mocks.post).toHaveBeenCalledWith('/api/v1/cpor/intelligence/promo-plan-draft/auto-propose', {}),
    );
    await probesRefetched();
  });

  it('the embedded "Create promotion plan" refetches both inside the freshness window', async () => {
    mocks.post.mockResolvedValue({ case_id: 52, case_code: 'C-52', line_ids: [1], budget_status: 'ok' });
    const qc = retainedClient();
    render(
      <QueryClientProvider client={qc}>
        <CardProbes />
        <PromoPlanBuilderPanel />
      </QueryClientProvider>,
    );
    await probesLoaded();
    fireEvent.change(screen.getByTestId('b4-seed-case-id'), { target: { value: '5' } });
    fireEvent.click(screen.getByTestId('b4-build-draft'));
    await screen.findByTestId('b4-draft-summary');
    fireEvent.click(screen.getByTestId('b4-create-case'));
    await waitFor(() =>
      expect(mocks.post).toHaveBeenCalledWith(
        '/api/v1/cpor/intelligence/promo-plan-draft/create-case',
        expect.objectContaining({ seed_case_id: 5 }),
      ),
    );
    await screen.findByTestId('b4-create-result');
    await probesRefetched();
  });
});
