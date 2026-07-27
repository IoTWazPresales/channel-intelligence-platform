import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactElement } from 'react';

import { CstImportJobResolutionSection } from './CstImportJobResolutionSection';
import type { CstMappingCandidate } from './cstImportSteward.config';

const PRODUCT_CANDIDATES: CstMappingCandidate[] = [
  {
    id: 201,
    import_job_id: 7,
    entity_type: 'cst_product_token',
    normalized_key: 'widget-x',
    row_count: 3,
    total_units: 15,
    status: 'needs_review',
    match_reason: 'item_code',
    confidence_score: 1,
    sample_raw_values: ['WIDGET-X'],
    suggestions: [{ dim_id: 11, label: 'Widget X Pro', score: 1, reason: 'item_code' }],
  },
];

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return {
    ...actual,
    apiGet: vi.fn(),
    apiPost: vi.fn(),
  };
});

import { apiGet } from '@/lib/api';

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe('CstImportJobResolutionSection', () => {
  beforeEach(() => {
    vi.mocked(apiGet).mockImplementation(async (path: string) => {
      if (path.includes('cst-mapping-state')) {
        return { job_id: 7, customer_id: 42, blocking_errors: [] };
      }
      if (path.includes('entity=location')) {
        return { items: [], total: 0, skip: 0, limit: 1 };
      }
      if (path.includes('status=open') && path.includes('entity=product')) {
        return { items: [], total: 1, skip: 0, limit: 1 };
      }
      if (path.includes('status=all') && path.includes('entity=product')) {
        return { items: [], total: 1, skip: 0, limit: 1 };
      }
      if (path.includes('cst-candidates')) {
        return { items: PRODUCT_CANDIDATES, total: 1, skip: 0, limit: 100 };
      }
      return {};
    });
  });

  it('renders entity tabs and opens drawer with suggestion cards', async () => {
    const user = userEvent.setup();
    renderWithClient(<CstImportJobResolutionSection importJobId={7} />);

    expect(await screen.findByTestId('cst-import-job-resolution-section')).toBeInTheDocument();
    expect(await screen.findByTestId('cst-import-entity-tabs')).toBeInTheDocument();
    expect(await screen.findByText('widget-x')).toBeInTheDocument();

    await user.click(screen.getByTestId('cst-import-row-map-201'));

    expect(await screen.findByTestId('cst-import-candidate-steward-drawer')).toBeInTheDocument();
    expect(screen.getByTestId('cst-import-suggestion-cards')).toBeInTheDocument();
    expect(screen.getByTestId('cst-import-suggestion-cards-item-11')).toBeInTheDocument();
  });
});
