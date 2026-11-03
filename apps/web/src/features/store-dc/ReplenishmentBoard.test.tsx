import { fireEvent, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { ReplenishmentView } from './ReplenishmentView';
import type { ReplenishmentViewData, SiteCandidateRow } from './types';

const apiPost = vi.fn();

vi.mock('@/lib/api', () => ({
  apiGet: vi.fn(),
  apiPost: (...args: unknown[]) => apiPost(...args),
  safeDisplayError: (error: unknown) => String(error),
}));

function leg(over: Partial<ReplenishmentViewData['lead_times'][number]['inbound']> = {}) {
  return {
    leg: 'inbound',
    title: 'Ship confirm to proof of delivery',
    history: 'no history',
    sample_count: 0,
    min_days: null,
    p25_days: null,
    median_days: null,
    p75_days: null,
    max_days: null,
    histogram: [
      { bucket: '0-7', count: 0 },
      { bucket: '8-14', count: 0 },
      { bucket: '15-28', count: 0 },
      { bucket: '29-56', count: 0 },
      { bucket: '57+', count: 0 },
    ],
    lead_time_label: 'lead time: no history',
    ...over,
  };
}

function view(over: Partial<ReplenishmentViewData> = {}): ReplenishmentViewData {
  return {
    customer_id: 1,
    customer_name: 'SDC-C1',
    customer_code: 'SDC-C1',
    grain: 'account',
    cover: { min_weeks: 4, target_weeks: 6, source: 'fallback' },
    dc_sections: [],
    sites: [],
    account: {
      site_label: null,
      customer_id: 1,
      customer_name: 'SDC-C1',
      supply: 'distributor',
      stock_on_hand: 20,
      need_units: 40,
      lead_time_label: 'lead time: no history',
      lines: [
        {
          product_id: 3,
          sku: 'SDC-SKU',
          product_name: 'SDC-SKU',
          stock_on_hand: 20,
          weekly_rate: 10,
          weeks_of_cover: 2,
          need_units: 40,
          need_reason: 'cover',
          lead_time_label: 'lead time: no history',
          slow: true,
          unsold: false,
          suggestions: ['promote', 'move', 'return'],
          suggestion_executed: false,
        },
      ],
    },
    collapsed_grain: null,
    lead_times: [
      {
        distributor_id: 7,
        distributor_name: 'SDC-D',
        receiving_site: null,
        inbound: leg(),
        onward: leg({
          leg: 'onward',
          title: 'Customer distribution centre to store',
          note: 'No dispatch and receipt dates are stored, so this leg has no history.',
        }),
      },
    ],
    lead_time_min_deliveries: 5,
    ...over,
  };
}

const candidate: SiteCandidateRow = {
  id: 4,
  customer_id: 1,
  customer_name: 'SDC-C1',
  site_label: 'SDC-HUB-1',
  evidence_kind: 'direct_shipment',
  status: 'open',
  blocked_as_distributor_site: false,
};

describe('ReplenishmentView', () => {
  it('shows a customer with no site and no distribution centre, and a suggestion writes nothing', () => {
    const decide = vi.fn();
    renderWithProviders(
      <ReplenishmentView
        customers={[{ id: 1, code: 'SDC-C1', name: 'SDC-C1' }]}
        customerId={1}
        onSelect={() => undefined}
        view={view()}
        candidates={[candidate]}
        onDecide={decide}
      />,
    );
    expect(screen.getByTestId('no-dc')).toHaveTextContent('no site label and no distribution centre');
    expect(screen.queryByTestId('dc-section')).toBeNull();
    expect(screen.getByTestId('lead-leg-onward')).toHaveTextContent('lead time: no history');
    expect(screen.getByTestId('lead-note-onward')).toHaveTextContent('no history');
    fireEvent.click(screen.getByTestId('suggestion-promote'));
    expect(screen.getByTestId('suggestion-note')).toHaveTextContent('Nothing was created');
    expect(apiPost).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId('candidate-confirm'));
    expect(decide).toHaveBeenCalledWith(4, 'confirm');
    fireEvent.click(screen.getByTestId('candidate-reject'));
    expect(decide).toHaveBeenCalledWith(4, 'reject');
  });

  it('shows stores by their own labels when there is no distribution centre', () => {
    renderWithProviders(
      <ReplenishmentView
        customers={[{ id: 1, code: 'SDC-C1', name: 'SDC-C1' }]}
        customerId={1}
        onSelect={() => undefined}
        view={view({
          grain: 'store',
          account: null,
          sites: [
            {
              site_label: 'SDC-SITE-A',
              customer_id: 1,
              customer_name: 'SDC-C1',
              supply: 'distributor',
              stock_on_hand: 20,
              need_units: 60,
              lead_time_label: 'lead time: 14 days',
              lines: [],
            },
          ],
        })}
        candidates={[]}
        onDecide={() => undefined}
      />,
    );
    expect(screen.getByTestId('no-dc')).toHaveTextContent('No confirmed distribution centre');
    expect(screen.getByTestId('site-block')).toHaveTextContent('SDC-SITE-A');
    expect(screen.queryByTestId('dc-section')).toBeNull();
  });

  it('shows inbound history and an onward leg with no history', () => {
    renderWithProviders(
      <ReplenishmentView
        customers={[{ id: 1, code: 'SDC-C1', name: 'SDC-C1' }]}
        customerId={1}
        onSelect={() => undefined}
        view={view({
          grain: 'store',
          account: null,
          sites: [],
          dc_sections: [
            {
              candidate_id: 8,
              site_label: 'SDC-HUB-1',
              stock_on_hand: 50,
              stock_note: null,
              serves: [{ customer_id: 1, customer_name: 'SDC-C1' }],
              lead_time: leg({ history: 'history', sample_count: 5, median_days: 14, lead_time_label: 'lead time: 14 days' }),
              onward: leg({
                leg: 'onward',
                title: 'Customer distribution centre to store',
                note: 'No dispatch and receipt dates are stored, so this leg has no history.',
              }),
              stores: [],
              need_from_distributor: [],
            },
          ],
          lead_times: [],
        })}
        candidates={[]}
        onDecide={() => undefined}
      />,
    );
    expect(screen.getByTestId('dc-stock')).toHaveTextContent('50');
    expect(screen.getByTestId('lead-leg-inbound')).toHaveTextContent('lead time: 14 days');
    expect(screen.getByTestId('lead-leg-onward')).toHaveTextContent('lead time: no history');
    expect(screen.queryByTestId('no-dc')).toBeNull();
  });
});
