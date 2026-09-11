import { ThemeProvider, createTheme } from '@mui/material/styles';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { SupplyOverview } from './SupplyOverview';
import type { SupplyOverview as Payload } from './types';

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
  CategoryBars: () => <div data-testid="lifecycle-bars" />,
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
  open_lines: 1964,
  open_units: 1,
  eta_past_no_pod_lines: 770,
  oldest_eta_past: '2026-05-07',
  oldest_days_past_eta: 123,
  landed_pod_iso_week: 0,
  pipeline_lines: 10,
  pipeline_units: 118024,
  shipped_lines: 5,
  shipped_units: 1,
  landed_lines: 2,
  landed_units: 1,
  overdue_commercial_lines: 546,
  po_observed: 2308,
  po_linked: 322,
  po_coverage_ratio: 322 / 2308,
  po_data_unavailable: false,
  lifecycle: [
    { state: 'Pipeline (open order)', count: 10, units: 1 },
    { state: 'Shipped, not landed', count: 5, units: 1 },
    { state: 'Landed (POD)', count: 2, units: 1 },
  ],
  po_by_distributor: [{ distributor: 'Highveld', observed_pos: 10, linked_pos: 4, covered: 0.4 }],
  labels: {
    open_lines: 'Open shipments',
    eta_past_no_pod_lines: 'Unreceived past ETA',
    landed_pod_iso_week: 'Received this week',
    po_coverage: 'PO coverage',
    pipeline_units: 'Backlog units',
  },
  captions: {
    open_lines: 'status ≠ received',
    eta_past_no_pod_lines: 'oldest 123 days',
    landed_pod_iso_week: 'POD date this ISO week',
    po_coverage: '322 of 2308 observed POs linked — not plan units covered',
    pipeline_units: 'open_order units',
  },
};

function renderOverview() {
  return render(
    <ThemeProvider theme={theme}>
      <SupplyOverview />
    </ThemeProvider>,
  );
}

describe('SupplyOverview', () => {
  beforeEach(() => {
    queryState.isLoading = false;
    queryState.isError = false;
    queryState.data = populated;
  });

  it('renders lab headlines, lifecycle, PO bars, attention, and workflows', () => {
    renderOverview();
    expect(screen.getByTestId('domain-supply')).toBeInTheDocument();
    expect(screen.getByText('Open shipments')).toBeInTheDocument();
    expect(screen.getByText('Unreceived past ETA')).toBeInTheDocument();
    expect(screen.getByText('Received this week')).toBeInTheDocument();
    expect(screen.getByText('Backlog units')).toBeInTheDocument();
    expect(screen.getAllByText('PO coverage').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('322 of 2308 observed POs linked — not plan units covered')).toBeInTheDocument();
    expect(screen.getByTestId('lifecycle-bars')).toBeInTheDocument();
    expect(screen.getByTestId('proportion-bar')).toBeInTheDocument();
    expect(screen.getByText('770 Inbound shipments unreceived past ETA')).toBeInTheDocument();
    expect(screen.getByText('Shipments')).toBeInTheDocument();
    expect(screen.getByText('Receipts & POD')).toBeInTheDocument();
    expect(screen.getByTestId('capability-status-partial')).toBeInTheDocument();
  });

  it('shows loading copy while the overview query is in flight', () => {
    queryState.isLoading = true;
    queryState.data = null;
    renderOverview();
    expect(screen.getByTestId('supply-overview-loading')).toBeInTheDocument();
    expect(screen.queryByText('Open shipments')).not.toBeInTheDocument();
    expect(screen.getByText('Shipments')).toBeInTheDocument();
  });

  it('shows an empty state when inbound facts are unavailable and keeps workflows', () => {
    queryState.data = { ...populated, data_unavailable: true };
    renderOverview();
    expect(screen.getByTestId('supply-overview-empty')).toBeInTheDocument();
    expect(screen.queryByText('Open shipments')).not.toBeInTheDocument();
    expect(screen.queryByTestId('lifecycle-bars')).not.toBeInTheDocument();
    expect(screen.getByText('Shipments')).toBeInTheDocument();
    expect(screen.getByTestId('capability-status-partial')).toBeInTheDocument();
  });
});
