import { ThemeProvider, createTheme } from '@mui/material/styles';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ExecutionLensView } from './ExecutionLensView';

const theme = createTheme();

function renderLens() {
  return render(
    <ThemeProvider theme={theme}>
      <ExecutionLensView />
    </ThemeProvider>,
  );
}

vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/stock',
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));

vi.mock('@/features/plan-vs-executed/PlanVsExecutedView', () => ({
  PlanVsExecutedView: () => <div data-testid="relocated-pve">relocated workspace</div>,
}));

vi.mock('@/features/workbench-ui/charts', () => ({
  PairedBars: () => <div data-testid="paired-bars" />,
}));

vi.mock('@tanstack/react-query', () => ({
  useQuery: () => ({
    isLoading: false,
    isError: false,
    data: {
      default_period: '26Q2',
      period_range: { from: '26Q2', to: '26Q2' },
      scorecard: { planned_units: 100, shipped_units_in_plan: 62, shipped_units_total: 70 },
      drill_rows: [
        { customer_label: 'Acme', planned_units: 80, shipped_units: 40 },
        { customer_label: 'Beta', planned_units: 20, shipped_units: 22 },
      ],
    },
  }),
}));

describe('ExecutionLensView', () => {
  it('renders lab headlines and relocates the existing workspace', () => {
    renderLens();
    expect(screen.getByText('Plan units 26Q2')).toBeInTheDocument();
    expect(screen.getByText('Shipped to date')).toBeInTheDocument();
    expect(screen.getByText('62% of plan (in-plan shipped)')).toBeInTheDocument();
    expect(screen.getByText('Customers under 70% of plan')).toBeInTheDocument();
    expect(screen.getByTestId('paired-bars')).toBeInTheDocument();
    expect(screen.getByTestId('relocated-pve')).toBeInTheDocument();
    expect(screen.getByTestId('stock-execution-relocated-workspace')).toBeInTheDocument();
  });
});
