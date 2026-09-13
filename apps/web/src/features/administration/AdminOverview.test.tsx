import { ThemeProvider, createTheme } from '@mui/material/styles';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AdminOverview } from './AdminOverview';
import type { AdministrationOverview as Payload } from './types';

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

vi.mock('@tanstack/react-query', () => ({
  useQuery: () => ({
    isLoading: queryState.isLoading,
    isError: queryState.isError,
    data: queryState.data,
  }),
}));

const populated: Payload = {
  database: 'cip',
  tenant_id: 'default',
  data_unavailable: false,
  users: 2,
  users_by_role: { admin: 1, steward: 0, planner: 0, viewer: 1 },
  jobs_running: 0,
  jobs_pending: 64,
  failed_24h: 0,
  failed_open: 44,
  sql_queries_7d: 0,
  sql_queries_all: 8,
  operations: [
    {
      id: 12,
      template_slug: 'dsi',
      status: 'pending',
      stage: 'uploaded',
      file_name: 'x.xlsx',
      error_summary: null,
    },
  ],
  labels: {
    users: 'Users',
    jobs_running: 'Background jobs running',
    failed_24h: 'Failed jobs (24h)',
    sql_queries_7d: 'Audited SQL queries (7d)',
  },
  captions: {
    users: '1 admin · 0 steward · 0 planner · 1 viewer',
    jobs_running: "import_job.status='running'",
    failed_24h: 'failed in last 24h',
    sql_queries_7d: 'sql_viewer_audit last 7 days',
  },
};

function renderOverview() {
  return render(
    <ThemeProvider theme={theme}>
      <AdminOverview />
    </ThemeProvider>,
  );
}

describe('AdminOverview', () => {
  beforeEach(() => {
    queryState.isLoading = false;
    queryState.isError = false;
    queryState.data = populated;
  });

  it('renders lab headlines, operations rows, attention, and remapped workflows', () => {
    renderOverview();
    expect(screen.getByTestId('domain-admin')).toBeInTheDocument();
    expect(screen.getByText('Users')).toBeInTheDocument();
    expect(screen.getByText('Background jobs running')).toBeInTheDocument();
    expect(screen.getByText('Failed jobs (24h)')).toBeInTheDocument();
    expect(screen.getByText('Audited SQL queries (7d)')).toBeInTheDocument();
    expect(screen.getByText('1 admin · 0 steward · 0 planner · 1 viewer')).toBeInTheDocument();
    expect(screen.getByText(/dsi · job 12/)).toBeInTheDocument();
    expect(screen.getByText('44 failed import jobs still open')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Users & roles/ })).toHaveAttribute('href', '/admin/users/list');
    expect(screen.getByText(/Audit log \(planned\)/)).toBeInTheDocument();
  });
});
