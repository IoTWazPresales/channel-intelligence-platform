import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactElement } from 'react';

import { CporHistoricalImportJobResolutionSection } from './CporHistoricalImportJobResolutionSection';

vi.mock('./cporHistoricalImportApi', async () => {
  const actual = await vi.importActual<typeof import('./cporHistoricalImportApi')>(
    './cporHistoricalImportApi'
  );
  return {
    ...actual,
    fetchCporHistoricalSummary: vi.fn(async () => ({
      id: 42,
      stage: 'validated',
      status: 'completed',
      file_name: 'test.xlsx',
      staging_count: 10,
      unresolved_counts: { product: 2, customer: 1, distributor: 0 },
      cases_ready: 3,
      cases_blocked: 1,
    })),
    fetchCporHistoricalCandidates: vi.fn(async () => ({
      candidates: [
        { entity: 'product', token: 'MODEL-A', row_count: 4, status: 'unresolved' },
        { entity: 'product', token: 'MODEL-B', row_count: 1, status: 'unresolved' },
      ],
      counts: { product: 2, customer: 1, distributor: 0 },
    })),
  };
});

function wrap(ui: ReactElement) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe('CporHistoricalImportJobResolutionSection', () => {
  it('renders entity tabs when jobId is set', async () => {
    wrap(<CporHistoricalImportJobResolutionSection importJobId={42} />);
    expect(await screen.findByTestId('cpor-historical-entity-tabs')).toBeInTheDocument();
    expect(screen.getByTestId('cpor-historical-tab-product')).toBeInTheDocument();
    expect(screen.getByTestId('cpor-historical-tab-customer')).toBeInTheDocument();
    expect(screen.getByTestId('cpor-historical-tab-distributor')).toBeInTheDocument();
    expect(screen.getByTestId('cpor-historical-steward-workspace-viewport-shell')).toBeInTheDocument();
    expect(screen.getByTestId('dsi-steward-candidate-filters')).toBeInTheDocument();
  });

  it('shows prompt when jobId is null', () => {
    wrap(<CporHistoricalImportJobResolutionSection importJobId={null} />);
    expect(screen.getByTestId('cpor-historical-import-job-resolution-section')).toHaveTextContent(
      /Upload and validate/
    );
  });
});
