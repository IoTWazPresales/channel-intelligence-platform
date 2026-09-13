import React from 'react';
import { screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import PlanningPage from './page';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/lineup',
}));

vi.mock('@/features/workbench-ui/charts', () => ({
  PairedBars: () => <div data-testid="paired-bars" />,
  ProportionBar: () => <div data-testid="proportion-bar" />,
}));

const apiGetMock = vi.fn(async (url: string) => {
  if (url.includes('/planning/overview')) {
    return {
      database: 'cip',
      tenant_id: 'default',
      data_unavailable: false,
      cases: 2,
      lines: 10,
      plan_units: 100,
      period_labels: ['26Q2'],
      readiness_missing: 1,
      readiness_ok: 9,
      readiness: {
        sku_assumptions_ok: 9,
        customer_terms_ok: 9,
        distributor_attribution_ok: 9,
        cost_basis_ok: 9,
        sku_assumptions_ratio: 0.9,
        customer_terms_ratio: 0.9,
        distributor_attribution_ratio: 0.9,
        cost_basis_ratio: 0.9,
      },
      economics_flagged: 0,
      economics_ok: 3,
      plan_lines: 3,
      fill_rate: 0.5,
      fill_rate_pct: 50,
      execution_period: '26Q2',
      execution_unavailable: false,
      shipped_units_in_plan: 50,
      planned_units_execution: 100,
      by_customer: [],
      labels: {
        cases: 'Lineup cases',
        plan_units: 'Plan units',
        shipped_vs_plan: 'Shipped vs plan',
        readiness_missing: 'Lines not ready',
        economics_flagged: 'Economics flagged',
      },
      captions: {
        cases: '10 lines',
        plan_units: 'line qty',
        shipped_vs_plan: 'fill rate',
        readiness_missing: 'missing',
        economics_flagged: '0 flagged',
      },
    };
  }
  return {};
});
vi.mock('@/lib/api', () => ({
  apiGet: (url: string) => apiGetMock(url),
  apiDelete: vi.fn(),
  apiPatch: vi.fn(),
  apiPost: vi.fn(),
}));

describe('Planning hub at /lineup', () => {
  beforeEach(() => {
    apiGetMock.mockClear();
  });

  it('mounts the lab Planning composition instead of LineupContainer', async () => {
    const qc = new QueryClient();
    renderWithProviders(
      <QueryClientProvider client={qc}>
        <PlanningPage />
      </QueryClientProvider>,
    );
    expect(await screen.findByTestId('domain-planning')).toBeInTheDocument();
    expect(screen.queryByTestId('lineup-container')).not.toBeInTheDocument();
    expect(await screen.findByText('Plan units')).toBeInTheDocument();
  });
});
