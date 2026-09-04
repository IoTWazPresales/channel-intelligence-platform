import React from 'react';
import { screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { draftFromColumnMap, PlanTemplatesSurface } from './PlanTemplatesSurface';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/commercial-planner/cpor-cases/historical-import',
}));

vi.mock('@/features/import-mapping/CanonicalColumnMappingPanel', () => ({
  CanonicalColumnMappingPanel: () => <div data-testid="plan-template-mapping" />,
}));

const profiles = {
  profiles: [
    {
      id: 1,
      profile_code: 'asus_consumer_cpor_tracking_v1',
      display_name: 'ASUS Consumer CPOR Tracking Table',
      header_row_index: 1,
      column_map_json: {
        case_code: ['Case ID'],
        customer_token: ['Dealer/Retailer'],
        sales_model_token: ['Sales Model Name'],
        window_start: ['Start From'],
        promotion_type: ['Promotion Type'],
        srp: ['SRP'],
        estimate_qty: ['Estimate Qty'],
      },
      sheet_roles_json: { 'Disti Sell out': 'disti' },
      value_maps_json: { status: { approved: 'approved' } },
      is_default: true,
    },
  ],
};

vi.mock('@/lib/api', () => ({
  apiGet: vi.fn(async (url: string) => {
    if (String(url).includes('/historical-import/profiles')) return profiles;
    if (String(url).includes('/cpor/cases')) {
      return { items: [{ id: 1, origin: 'historical_import' }], total: 1, page: 1, page_size: 500 };
    }
    return {};
  }),
}));

describe('PlanTemplatesSurface', () => {
  it('inverts column_map_json into header → canonical draft', () => {
    expect(draftFromColumnMap({ case_code: ['Case ID'], srp: ['SRP', 'Promo RSP'] })).toEqual({
      'Case ID': 'case_code',
      SRP: 'srp',
      'Promo RSP': 'srp',
    });
  });

  it('lists stored profiles and keeps export as Planned honesty', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    renderWithProviders(
      <QueryClientProvider client={qc}>
        <PlanTemplatesSurface />
      </QueryClientProvider>,
    );
    expect(await screen.findByTestId('plan-templates')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByTestId('template-asus_consumer_cpor_tracking_v1')).toBeInTheDocument();
    });
    expect(screen.getByTestId('template-learn')).toBeInTheDocument();
    expect(screen.getAllByText(/template-driven export is not built/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByTestId('capability-status-planned')).toBeInTheDocument();
    expect(screen.getByTestId('capability-status-partial')).toBeInTheDocument();
  });
});
