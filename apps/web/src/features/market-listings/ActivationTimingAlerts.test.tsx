import React from 'react';
import { render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ActivationTimingAlerts, type TimingAlert } from './ActivationTimingAlerts';

const apiState = vi.hoisted(() => ({
  mode: 'ok' as 'ok' | 'pending' | 'error' | 'empty' | 'unavailable' | 'fallback',
  alerts: null as TimingAlert[] | null,
}));

vi.mock('@/lib/api', () => ({
  apiGet: async () => {
    if (apiState.mode === 'pending') return new Promise(() => undefined);
    if (apiState.mode === 'error') throw new Error('down');
    if (apiState.mode === 'unavailable') return { timing_alerts: [], data_unavailable: true };
    if (apiState.mode === 'fallback') {
      return {
        activation_alert_days: 3,
        data_unavailable: false,
        items: [{ listing_id: 4, activation_status: 'not_activated', activation_timing: [] }],
        timing_alerts: [],
      };
    }
    if (apiState.mode === 'empty') return { activation_alert_days: 3, timing_alerts: [], data_unavailable: false };
    return {
      activation_alert_days: 3,
      data_unavailable: false,
      timing_alerts: apiState.alerts ?? [
        {
          kind: 'late_activation',
          listing_id: 4,
          customer_id: 11,
          product_id: 9,
          marketplace: 'shop-a',
          case_id: 7,
          case_code: 'CASE-7',
          window_start: '2026-11-01',
          window_end: '2026-11-30',
          alert_days: 3,
          not_at_price_on: '2026-11-04',
          at_price_from: '2026-11-06',
          days_late_at_least: 3,
        },
        {
          kind: 'early_deactivation',
          listing_id: 5,
          customer_id: 11,
          product_id: 10,
          marketplace: 'shop-a',
          case_id: 7,
          case_code: 'CASE-7',
          window_start: '2026-11-01',
          window_end: '2026-11-30',
          alert_days: 3,
          last_at_price_on: '2026-11-11',
          off_price_on: '2026-11-21',
          back_at_price_on: null,
          days_early_at_least: 9,
        },
      ],
    };
  },
}));

function renderAlerts() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ActivationTimingAlerts />
    </QueryClientProvider>,
  );
}

describe('ActivationTimingAlerts', () => {
  beforeEach(() => {
    apiState.mode = 'ok';
    apiState.alerts = null;
  });

  it('lists late and early alerts with what the checks show and the threshold', async () => {
    renderAlerts();
    const late = await screen.findByTestId('activation-timing-row-4-late_activation');
    expect(late).toHaveTextContent('Late activation');
    expect(late).toHaveTextContent('Still off price on 2026-11-04 (3+ days in); at price from 2026-11-06');
    const early = screen.getByTestId('activation-timing-row-5-early_deactivation');
    expect(early).toHaveTextContent('Off price on 2026-11-21 (9+ days before the end)');
    expect(screen.getByTestId('activation-timing-rule')).toHaveTextContent('3 or more days');
  });

  it('shows same-day activation, deactivation and recovery evidence from the API', async () => {
    apiState.alerts = [
      {
        kind: 'late_activation',
        listing_id: 4,
        customer_id: 11,
        product_id: 9,
        case_id: 7,
        case_code: 'CASE-7',
        window_start: '2026-11-01',
        window_end: '2026-11-30',
        alert_days: 3,
        not_at_price_on: '2026-11-04',
        at_price_from: '2026-11-04',
        days_late_at_least: 3,
      },
      {
        kind: 'early_deactivation',
        listing_id: 4,
        customer_id: 11,
        product_id: 9,
        case_id: 7,
        case_code: 'CASE-7',
        window_start: '2026-11-01',
        window_end: '2026-11-30',
        alert_days: 3,
        last_at_price_on: '2026-11-04',
        off_price_on: '2026-11-04',
        back_at_price_on: '2026-11-04',
        days_early_at_least: 26,
      },
    ];
    renderAlerts();
    expect(await screen.findByTestId('activation-timing-row-4-late_activation')).toHaveTextContent(
      'Still off price on 2026-11-04 (3+ days in); at price from 2026-11-04',
    );
    expect(screen.getByTestId('activation-timing-row-4-early_deactivation')).toHaveTextContent(
      'Off price on 2026-11-04 (26+ days before the end); back at price 2026-11-04',
    );
    expect(within(screen.getByTestId('activation-timing-table')).getAllByRole('row')).toHaveLength(3);
  });

  it('renders no promotion alerts when the API excludes fallback-only evidence', async () => {
    // Price-basis filtering belongs to the API; the UI must not infer alerts from other fields.
    apiState.mode = 'fallback';
    renderAlerts();
    expect(await screen.findByTestId('activation-timing-empty')).toHaveTextContent(
      'No late or early promotions in the stored checks.',
    );
    expect(screen.queryByTestId('activation-timing-table')).not.toBeInTheDocument();
  });

  it('shows unavailable evidence as an error instead of an empty promotion history', async () => {
    apiState.mode = 'unavailable';
    renderAlerts();
    expect(await screen.findByTestId('activation-timing-error')).toBeInTheDocument();
    expect(screen.queryByTestId('activation-timing-empty')).not.toBeInTheDocument();
  });

  it('is honest while loading and on error, and empty only after a read', async () => {
    apiState.mode = 'pending';
    const pending = renderAlerts();
    expect(await screen.findByTestId('activation-timing-loading')).toBeInTheDocument();
    expect(screen.queryByTestId('activation-timing-empty')).not.toBeInTheDocument();
    pending.unmount();

    apiState.mode = 'error';
    const failed = renderAlerts();
    expect(await screen.findByTestId('activation-timing-error')).toBeInTheDocument();
    expect(screen.queryByTestId('activation-timing-empty')).not.toBeInTheDocument();
    failed.unmount();

    apiState.mode = 'empty';
    renderAlerts();
    expect(await screen.findByTestId('activation-timing-empty')).toBeInTheDocument();
  });
});
