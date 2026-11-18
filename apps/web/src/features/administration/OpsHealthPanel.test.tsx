import { ThemeProvider, createTheme } from '@mui/material/styles';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { OpsHealthPanel, healthColor, type OpsHealth } from './OpsHealthPanel';

const theme = createTheme();

const health: OpsHealth = {
  services: {
    state: 'flapping',
    detail: 'Restarting repeatedly: worker.',
    heartbeat_age_seconds: 12,
    flap_limit_30m: 5,
    components: [
      { name: 'api', state: 'healthy', launches: 2, launches_30m: 0, flapping: false, last_healthy: null, detail: null },
      { name: 'worker', state: 'starting', launches: 9, launches_30m: 6, flapping: true, last_healthy: null, detail: null },
    ],
  },
  backups: {
    state: 'stale',
    backup: { state: 'ok', detail: 'Verified backup 3 hours ago.' },
    restore: { state: 'stale', detail: 'The last restore test is 9 days old.' },
  },
  reports: {
    state: 'late',
    detail: '2 expected reports are late.',
    late: 2,
    missing: 0,
    expected_customers: 4,
    newest_received: '2026-11-16T09:00:00+00:00',
    days_since_newest: 2,
  },
};

describe('OpsHealthPanel', () => {
  it('shows each part with its state and detail', () => {
    render(
      <ThemeProvider theme={theme}>
        <OpsHealthPanel health={health} />
      </ThemeProvider>,
    );
    expect(screen.getByTestId('ops-health-services-state')).toHaveTextContent('flapping');
    expect(screen.getByText(/worker: starting · 6 launches in 30 min \(flapping\)/)).toBeInTheDocument();
    expect(screen.getByTestId('ops-health-backups-state')).toHaveTextContent('stale');
    expect(screen.getByText(/Restore test: The last restore test is 9 days old/)).toBeInTheDocument();
    expect(screen.getByTestId('ops-health-reports-state')).toHaveTextContent('late');
    expect(screen.getByText(/Customers expected to report: 4 · newest report 2 days ago/)).toBeInTheDocument();
  });

  it('shows pending (due) and untracked report states without calling them ok', () => {
    render(
      <ThemeProvider theme={theme}>
        <OpsHealthPanel
          health={{
            ...health,
            reports: {
              ...health.reports,
              state: 'untracked',
              detail: '1 customers expected to report have no tracking slot for the recent weeks.',
              late: 0,
              due: 2,
              untracked_customers: 1,
              newest_received: null,
              days_since_newest: null,
            },
          }}
        />
      </ThemeProvider>,
    );
    expect(screen.getByTestId('ops-health-reports-state')).toHaveTextContent('untracked');
    expect(screen.getByText(/Customers expected to report: 4 · 2 due · 1 untracked/)).toBeInTheDocument();
    expect(healthColor('untracked')).toBe('warning');
    expect(healthColor('pending')).toBe('default');
  });

  it('says so when the API does not report health', () => {
    render(
      <ThemeProvider theme={theme}>
        <OpsHealthPanel health={undefined} />
      </ThemeProvider>,
    );
    expect(screen.getByText('Not reported by this API version.')).toBeInTheDocument();
  });

  it('maps states to colours, unknown stays neutral', () => {
    expect(healthColor('ok')).toBe('success');
    expect(healthColor('missing')).toBe('error');
    expect(healthColor('stale')).toBe('warning');
    expect(healthColor('unknown')).toBe('default');
    expect(healthColor(null)).toBe('default');
  });
});