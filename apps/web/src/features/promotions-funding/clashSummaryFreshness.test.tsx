import React from 'react';
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { clashSummaryKey } from './calendarClashKeys';
import { PlanWorkspace } from './PlanWorkspace';
import { CalendarUploadPanel } from './timeline/CalendarUploadPanel';

// PR #122 round 1, B2: the planner's calendar-clash summary (staleTime 60 s, no focus refetch) must
// refetch after a write that can change a clash: a case status change, or a calendar upload.

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/promotions',
}));
vi.mock('@/components/EnterpriseDataGrid', () => ({ EnterpriseDataGrid: () => <div /> }));
vi.mock('@/features/commercial-planner/EntitySearchAutocomplete', () => ({
  EntitySearchAutocomplete: () => null,
}));
vi.mock('@/app/(app)/commercial-planner/cpor-cases/[id]/CporComparableCasesPanel', () => ({
  CporComparableCasesPanel: () => null,
}));

const profile = {
  id: 1, profile_code: 'generic', display_name: 'Generic calendar', header_row_index: 1,
  sheet_name: null, column_map_json: { name: ['Name'], start_date: ['Start'] },
  value_maps_json: { kind: {} }, is_default: true, notes: null,
};
const preview = {
  ok: true, filename: 'calendar.csv', profile_code: 'generic', upload_id: 'calendar.csv',
  file_sha256: 'hash', headers: ['Name', 'Start'], mapped_columns: { name: 'Name', start_date: 'Start' },
  blocking_errors: [], row_errors: [], parsed_rows: 1, will_insert: 1, will_replace: 0,
  customers: [], unresolved_customers: [],
  events: [{ row_number: 2, customer_id: 17, customer_name: 'Selected account', name: 'New campaign',
    kind: 'campaign', start_date: '2026-03-01', end_date: '2026-03-05' }], events_truncated: false,
};
const draftCase = {
  id: 77, case_code: 'C26P00077', case_name: null, customer_name: 'Customer A', customer_code: 'CUST-A',
  promotion_type: 'Sell out PP', window_start: '2026-10-01', window_end: '2026-10-31', status: 'draft',
  workflow_status: 'draft', currency_code: 'ZAR', roe_snapshot: null, fx_mode: 'booked', fx_proposed_rate: 18,
  missing_roe: false, allowed_next: ['proposed', 'cancelled'], lines: [], flags: [], ttl_support_zar: 0,
  ttl_support_usd: null, needs_reapproval: false,
};

const mocks = vi.hoisted(() => ({ get: vi.fn(), form: vi.fn(), post: vi.fn() }));
vi.mock('@/lib/api', () => ({
  apiGet: mocks.get,
  apiPostFormData: mocks.form,
  apiPost: mocks.post,
  apiPatch: vi.fn(async () => ({})),
  apiPut: vi.fn(),
  apiDelete: vi.fn(),
  apiDownloadBlob: vi.fn(),
}));

const TODAY = '2026-11-19';
let clashFetches = 0;

/** Stands in for the planner card: same key and the planner's 60 s freshness, counting fetches. */
function ClashProbe() {
  const q = useQuery({
    queryKey: ['customer-calendar', 'clash-summary', TODAY],
    queryFn: async () => {
      clashFetches += 1;
      return { clash_count: clashFetches };
    },
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });
  return <span data-testid="clash-probe">{q.data?.clash_count ?? 'loading'}</span>;
}

function retainedClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

beforeEach(() => {
  vi.clearAllMocks();
  clashFetches = 0;
  mocks.get.mockImplementation(async (url: string) => {
    if (url === '/api/v1/cpor/cases/77') return draftCase;
    if (url.endsWith('/profiles')) return { profiles: [profile] };
    return {};
  });
  mocks.post.mockResolvedValue({});
  mocks.form.mockImplementation((path: string) =>
    Promise.resolve(path.endsWith('preview') ? preview : { inserted: 1, replaced: 0 }),
  );
});

describe('clash summary freshness (B2)', () => {
  it('the planner key is the one the probe (and the invalidation prefix) uses', () => {
    expect([...clashSummaryKey(TODAY)]).toEqual(['customer-calendar', 'clash-summary', TODAY]);
  });

  it('refetches the summary after a case is cancelled, inside the freshness window', async () => {
    const qc = retainedClient();
    renderWithProviders(
      <QueryClientProvider client={qc}>
        <ClashProbe />
        <PlanWorkspace caseId={77} onBack={() => undefined} />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getByTestId('clash-probe')).toHaveTextContent('1'));
    fireEvent.click(await screen.findByTestId('plan-cancel'));
    await waitFor(() =>
      expect(mocks.post).toHaveBeenCalledWith('/api/v1/cpor/cases/77/transition', { action: 'cancel' }),
    );
    await waitFor(() => expect(screen.getByTestId('clash-probe')).toHaveTextContent('2'));
    expect(clashFetches).toBe(2);
  });

  it('refetches the summary after a calendar upload is applied, inside the freshness window', async () => {
    const qc = retainedClient();
    const { container } = render(
      <QueryClientProvider client={qc}>
        <ClashProbe />
        <CalendarUploadPanel customerId={17} onApplied={() => undefined} />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getByTestId('clash-probe')).toHaveTextContent('1'));
    await screen.findByText('Generic calendar');
    fireEvent.change(container.querySelector('input[type=file]')!, {
      target: { files: [new File(['Name,Start\nEvent,2026-03-01'], 'calendar.csv')] },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Preview calendar' }));
    await screen.findByText('New campaign');
    fireEvent.click(screen.getByRole('button', { name: 'Apply calendar' }));
    await waitFor(() => expect(screen.getByTestId('clash-probe')).toHaveTextContent('2'));
    expect(clashFetches).toBe(2);
  });
});
