import { ThemeProvider, createTheme } from '@mui/material/styles';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { PlanningOverview } from './PlanningOverview';
import type { PlanningOverview as Payload } from './types';

const theme = createTheme();

const queryState = vi.hoisted(() => ({
  isLoading: false,
  isError: false,
  data: null as Payload | null,
}));

vi.mock('./useClientReady', () => ({
  useClientReady: () => true,
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

vi.mock('@/features/workbench-ui/charts', () => ({
  PairedBars: () => <div data-testid="paired-bars" />,
  ProportionBar: () => <div data-testid="proportion-bar" />,
}));

vi.mock('@tanstack/react-query', () => ({
  useQuery: () => ({
    isLoading: queryState.isLoading,
    isError: queryState.isError,
    data: queryState.data,
  }),
}));

const populated: Payload = {
  database: 'cip',
  tenant_id: 't1',
  data_unavailable: false,
  cases: 12,
  lines: 400,
  plan_units: 88000,
  period_labels: ['26Q2'],
  readiness_missing: 40,
  readiness_ok: 360,
  readiness: {
    sku_assumptions_ok: 380,
    customer_terms_ok: 390,
    distributor_attribution_ok: 370,
    cost_basis_ok: 360,
    sku_assumptions_ratio: 0.95,
    customer_terms_ratio: 0.975,
    distributor_attribution_ratio: 0.925,
    cost_basis_ratio: 0.9,
  },
  economics_flagged: 11,
  economics_ok: 89,
  plan_lines: 100,
  fill_rate: 0.42,
  fill_rate_pct: 42,
  execution_period: '26Q2',
  execution_unavailable: false,
  shipped_units_in_plan: 1000,
  planned_units_execution: 2000,
  by_customer: [{ customer: 'Acme', customer_id: 1, plan: 100, shipped: 40 }],
  labels: {
    cases: 'Lineup cases',
    plan_units: 'Plan units',
    shipped_vs_plan: 'Shipped vs plan',
    readiness_missing: 'Lines not ready',
    economics_flagged: 'Economics flagged',
  },
  captions: {
    cases: '400 commercial_lineup_line on active commercial_lineup_case',
    plan_units: 'sum(commercial_lineup_line.quantity_units)',
    shipped_vs_plan: 'Fill rate min(shipped, planned)/planned',
    readiness_missing: 'missing assumptions / terms',
    economics_flagged: '89 ok · flags explain why',
  },
};

function renderOverview() {
  return render(
    <ThemeProvider theme={theme}>
      <PlanningOverview />
    </ThemeProvider>,
  );
}

describe('PlanningOverview', () => {
  beforeEach(() => {
    queryState.isLoading = false;
    queryState.isError = false;
    queryState.data = populated;
  });

  it('renders lab headlines, paired bars, readiness, attention, and workflows', () => {
    renderOverview();
    expect(screen.getByTestId('domain-planning')).toBeInTheDocument();
    expect(screen.getAllByText('Lineup cases').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('Plan units')).toBeInTheDocument();
    expect(screen.getByText('Shipped vs plan')).toBeInTheDocument();
    expect(screen.getByText('Lines not ready')).toBeInTheDocument();
    expect(screen.getByText('Economics flagged')).toBeInTheDocument();
    expect(screen.getByText('400 commercial_lineup_line on active commercial_lineup_case')).toBeInTheDocument();
    expect(screen.getByTestId('paired-bars')).toBeInTheDocument();
    expect(screen.getAllByTestId('proportion-bar').length).toBeGreaterThanOrEqual(4);
    expect(screen.getByText('40 Lineup lines missing SKU assumptions, terms or cost basis')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Lineup cases/ })).toHaveAttribute('href', '/lineup/cases');
    expect(screen.getByRole('link', { name: /Plans & line economics/ })).toHaveAttribute('href', '/commercial-planner');
    expect(screen.getByText(/Product roadmap \(data only\)/)).toBeInTheDocument();
  });

  it('shows loading copy while the overview query is in flight', () => {
    queryState.isLoading = true;
    queryState.data = null;
    renderOverview();
    expect(screen.getByTestId('planning-overview-loading')).toBeInTheDocument();
    expect(screen.queryByText('Plan units')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Lineup cases/ })).toBeInTheDocument();
  });

  it('shows an empty state when lineup facts are unavailable and keeps workflows', () => {
    queryState.data = { ...populated, data_unavailable: true };
    renderOverview();
    expect(screen.getByTestId('planning-overview-empty')).toBeInTheDocument();
    expect(screen.queryByText('Plan units')).not.toBeInTheDocument();
    expect(screen.queryByTestId('paired-bars')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Lineup cases/ })).toHaveAttribute('href', '/lineup/cases');
  });
});
