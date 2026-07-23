import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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
      plan_class_counts: {
        product: {
          ready_to_map: 1,
          ambiguous_eligible: 1,
          no_match: 0,
          needs_review: 0,
        },
      },
      cases_ready: 3,
      cases_blocked: 1,
    })),
    fetchCporHistoricalCandidates: vi.fn(async () => ({
      candidates: [
        {
          entity: 'product',
          token: 'MODEL-A',
          row_count: 4,
          status: 'unresolved',
          confidence: 0.92,
          plan_class: 'ready_to_map',
          match_reason: 'prefix_match',
          suggestions: [
            { dim_id: 11, label: 'Model A Pro', score: 0.92, reason: 'prefix_match' },
          ],
        },
        {
          entity: 'product',
          token: 'MODEL-B',
          row_count: 1,
          status: 'unresolved',
          confidence: 1.0,
          plan_class: 'ambiguous_eligible',
          match_reason: 'exact_key_collision:sales_model_name',
          suggestions: [
            { dim_id: 21, label: 'Model B One', score: 1.0, reason: 'exact_key_collision:sales_model_name' },
            { dim_id: 22, label: 'Model B Two', score: 1.0, reason: 'exact_key_collision:sales_model_name' },
          ],
        },
      ],
      counts: { product: 2, customer: 1, distributor: 0 },
      plan_class_counts: {
        product: {
          ready_to_map: 1,
          ambiguous_eligible: 1,
          no_match: 0,
          needs_review: 0,
        },
      },
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

  it('shows confidence bands and top suggestions from Unit 1 payload', async () => {
    wrap(<CporHistoricalImportJobResolutionSection importJobId={42} />);
    expect(await screen.findByText('Model A Pro')).toBeInTheDocument();
    expect(screen.getAllByTestId('cpor-historical-confidence-band').length).toBeGreaterThan(0);
    expect(screen.getByTestId('dsi-filter-queue-ambiguous_eligible')).toBeInTheDocument();
    expect(screen.queryByTestId('dsi-filter-queue-provisional')).not.toBeInTheDocument();
    expect(screen.queryByTestId('dsi-filter-verify-name')).not.toBeInTheDocument();
  });

  it('opens suggestion-first drawer (not autocomplete-only)', async () => {
    const user = userEvent.setup();
    wrap(<CporHistoricalImportJobResolutionSection importJobId={42} />);
    await screen.findByText('Model A Pro');
    const mapButtons = await screen.findAllByRole('button', { name: 'Map…' });
    await user.click(mapButtons[0]!);
    expect(await screen.findByTestId('cpor-historical-drawer-intelligence')).toBeInTheDocument();
    expect(screen.getByTestId('cpor-historical-drawer-suggestions')).toBeInTheDocument();
    expect(screen.getByTestId('cpor-historical-suggestion-map-11')).toBeInTheDocument();
    expect(screen.getByTestId('cpor-historical-drawer-override-search')).toBeInTheDocument();
  });

  it('filters by plan_class ready_to_map', async () => {
    const user = userEvent.setup();
    wrap(<CporHistoricalImportJobResolutionSection importJobId={42} />);
    await screen.findByText('MODEL-A');
    expect(screen.getByText('MODEL-B')).toBeInTheDocument();
    await user.click(screen.getByTestId('dsi-filter-queue-ready_to_map'));
    expect(screen.getByText('MODEL-A')).toBeInTheDocument();
    expect(screen.queryByText('MODEL-B')).not.toBeInTheDocument();
  });

  it('shows prompt when jobId is null', () => {
    wrap(<CporHistoricalImportJobResolutionSection importJobId={null} />);
    expect(screen.getByTestId('cpor-historical-import-job-resolution-section')).toHaveTextContent(
      /Upload and validate/
    );
  });
});
