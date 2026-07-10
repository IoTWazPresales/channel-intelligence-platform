import type { ReactElement } from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';

import { ShipmentEntityStewardPanelLegacy } from './ShipmentEntityStewardPanelLegacy';

vi.mock('@/lib/api', () => ({
  apiGet: vi.fn(async (path: string) => {
    if (path.includes('/import-jobs/9/mapping-candidates')) {
      return [
        {
          id: 101,
          import_job_id: 9,
          entity_type: 'shipment_distributor',
          normalized_key: 'acme',
          row_count: 2,
          total_units: 4,
          total_reported_value: 100,
          sample_raw_values: ['ACME Pty'],
          suggested_entity_id: null,
          suggested_distributor_code: null,
          suggested_distributor_name: null,
          suggested_customer_code: null,
          suggested_customer_name: null,
          suggested_action: 'create_provisional_distributor',
          match_reason: 'no_alias_or_exact_dim_match',
          confidence_score: 0.2,
          status: 'needs_review',
          context: { party: 'bill_to', line_ids: [1, 2], suggested_name: 'Acme Pty' },
        },
        {
          id: 102,
          import_job_id: 9,
          entity_type: 'shipment_customer_token',
          normalized_key: 'takealot',
          row_count: 1,
          total_units: 1,
          total_reported_value: 10,
          sample_raw_values: ['Q2 Takealot'],
          suggested_entity_id: null,
          suggested_distributor_code: null,
          suggested_distributor_name: null,
          suggested_customer_code: null,
          suggested_customer_name: null,
          suggested_action: 'create_provisional_customer',
          match_reason: 'no_alias_or_exact_dim_match',
          confidence_score: 0.2,
          status: 'needs_review',
          context: { line_ids: [3], suggested_name: 'Takealot' },
        },
      ];
    }
    return [];
  }),
  apiPost: vi.fn(),
}));

function wrap(ui: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe('ShipmentEntityStewardPanelLegacy', () => {
  it('renders distributor and channel partner rows', async () => {
    wrap(<ShipmentEntityStewardPanelLegacy importJobId={9} />);
    expect(await screen.findByText('ACME Pty')).toBeTruthy();
    expect(screen.getByTestId('shipment-entity-steward-panel')).toBeTruthy();
    expect(screen.getByText('Q2 Takealot')).toBeTruthy();
    expect(screen.getAllByText('Distributor').length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText('Channel partner').length).toBeGreaterThanOrEqual(2);
    const specialButtons = screen.getAllByRole('button', { name: /special category/i });
    expect(specialButtons.length).toBeGreaterThanOrEqual(2);
    const rejectButtons = screen.getAllByRole('button', { name: /^reject candidate$/i });
    expect(rejectButtons.length).toBeGreaterThanOrEqual(2);
  });

  it('bands confidence scores (0.2 -> Low) on candidate rows', async () => {
    wrap(<ShipmentEntityStewardPanelLegacy importJobId={9} />);
    await screen.findByText('ACME Pty');
    // Both seeded rows have confidence_score 0.2 -> Low band chip + raw score.
    expect(screen.getByTestId('shipment-confidence-band-101')).toHaveTextContent('Low');
    expect(screen.getByTestId('shipment-confidence-band-102')).toHaveTextContent('Low');
    expect(screen.getAllByText('score 0.20').length).toBeGreaterThanOrEqual(2);
  });

  it('filters candidate rows via chip strip without crashing', async () => {
    wrap(<ShipmentEntityStewardPanelLegacy importJobId={9} />);
    await screen.findByText('ACME Pty');
    const filters = screen.getByTestId('shipment-steward-candidate-filters');
    expect(within(filters).getByText('Showing 2 of 2')).toBeInTheDocument();
    fireEvent.click(within(filters).getByText('Distributor'));
    expect(screen.getByText('ACME Pty')).toBeInTheDocument();
    expect(screen.queryByText('Q2 Takealot')).not.toBeInTheDocument();
    expect(within(filters).getByText('Showing 1 of 2')).toBeInTheDocument();
    fireEvent.click(within(filters).getByText('Clear filters'));
    expect(await screen.findByText('Q2 Takealot')).toBeInTheDocument();
    expect(within(filters).getByText('Showing 2 of 2')).toBeInTheDocument();
  });
});
