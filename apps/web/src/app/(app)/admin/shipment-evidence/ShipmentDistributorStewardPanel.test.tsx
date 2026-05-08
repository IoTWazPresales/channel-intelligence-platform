import type { ReactElement } from 'react';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';

import { ShipmentDistributorStewardPanel } from './ShipmentDistributorStewardPanel';

vi.mock('@/lib/api', () => ({
  apiGet: vi.fn(async (path: string) => {
    if (path.includes('distributor-stewardship/tokens')) {
      return {
        items: [
          {
            import_job_id: 9,
            party: 'bill_to',
            normalized_token: 'acme',
            representative_raw_token: 'ACME Pty',
            row_count: 2,
            total_quantity: 4,
            total_amount: 100,
            sample_line_ids: [1, 2],
            sample_source_row_numbers: [3, 4],
            import_job_file_name: 'x.xlsx',
          },
        ],
      };
    }
    return { items: [] };
  }),
  apiPost: vi.fn(),
}));

function wrap(ui: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe('ShipmentDistributorStewardPanel', () => {
  it('renders unresolved token row', async () => {
    wrap(<ShipmentDistributorStewardPanel importJobId={9} />);
    expect(await screen.findByText('ACME Pty')).toBeTruthy();
    expect(screen.getByTestId('shipment-distributor-steward-panel')).toBeTruthy();
  });
});
