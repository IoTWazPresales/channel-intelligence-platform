import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import type { ReactElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { ReplenishmentBoard } from './ReplenishmentBoard';
import { ReplenishmentView } from './ReplenishmentView';
import type { ReplenishmentViewData, SiteCandidateRow, StoreDcConfig } from './types';

const api = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  apiPut: vi.fn(),
}));

vi.mock('@/lib/api', () => ({
  apiGet: (...args: unknown[]) => api.apiGet(...args),
  apiPost: (...args: unknown[]) => api.apiPost(...args),
  apiPut: (...args: unknown[]) => api.apiPut(...args),
  safeDisplayError: (error: unknown) => String(error),
}));

function wrap(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderWithProviders(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

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

const config: StoreDcConfig = {
  tenant_id: 't',
  lead_time_min_deliveries: 5,
  dc_name_patterns: ['DC'],
  stock_behaviour_min_soh: 1,
  stored: true,
};

describe('ReplenishmentView', () => {
  beforeEach(() => {
    api.apiGet.mockReset();
    api.apiPost.mockReset();
    api.apiPut.mockReset();
  });

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
    expect(api.apiPost).not.toHaveBeenCalled();
    expect(screen.queryByTestId('served-save-4')).toBeNull();
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

  it('sends settings, thresholds, served accounts, refresh, and lead-time reload through the existing controls', () => {
    const onRefresh = vi.fn();
    const onSaveConfig = vi.fn();
    const onSaveThresholds = vi.fn();
    const onAssignServed = vi.fn();
    const onReloadLeadTimes = vi.fn();
    renderWithProviders(
      <ReplenishmentView
        customers={[
          { id: 1, code: 'SDC-C1', name: 'SDC-C1' },
          { id: 2, code: 'SDC-C2', name: 'SDC-C2' },
        ]}
        customerId={1}
        onSelect={() => undefined}
        view={view({
          dc_sections: [
            {
              candidate_id: 4,
              site_label: 'SDC-HUB-1',
              stock_on_hand: 50,
              stock_note: null,
              serves: [{ customer_id: 1, customer_name: 'SDC-C1' }],
              lead_time: leg(),
              onward: leg({ leg: 'onward', title: 'Customer distribution centre to store' }),
              stores: [],
              need_from_distributor: [],
            },
          ],
        })}
        candidates={[{ ...candidate, status: 'confirmed' }]}
        onDecide={() => undefined}
        onRefresh={onRefresh}
        config={config}
        onSaveConfig={onSaveConfig}
        onSaveThresholds={onSaveThresholds}
        onAssignServed={onAssignServed}
        onReloadLeadTimes={onReloadLeadTimes}
      />,
    );

    fireEvent.click(screen.getByTestId('candidates-refresh'));
    expect(onRefresh).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByTestId('config-save'));
    expect(onSaveConfig).toHaveBeenCalledWith({
      lead_time_min_deliveries: 5,
      dc_name_patterns: ['DC'],
      stock_behaviour_min_soh: 1,
    });
    fireEvent.change(screen.getByTestId('threshold-slow'), { target: { value: '2.5' } });
    fireEvent.click(screen.getByTestId('threshold-save'));
    expect(onSaveThresholds).toHaveBeenCalledWith({ slow_cover_multiple: 2.5 });
    fireEvent.click(screen.getByTestId('served-customer-2').querySelector('input') as HTMLInputElement);
    fireEvent.click(screen.getByTestId('served-save-4'));
    expect(onAssignServed).toHaveBeenCalledWith(4, [1, 2], [1, 2]);
    fireEvent.click(screen.getByTestId('lead-time-reload'));
    expect(onReloadLeadTimes).toHaveBeenCalledOnce();
    expect(api.apiPost).not.toHaveBeenCalled();
    expect(api.apiPut).not.toHaveBeenCalled();
  });

  it('does not save a blank threshold or an invalid minimum delivery count', () => {
    const onSaveConfig = vi.fn();
    const onSaveThresholds = vi.fn();
    renderWithProviders(
      <ReplenishmentView
        customers={[{ id: 1, code: 'SDC-C1', name: 'SDC-C1' }]}
        customerId={1}
        onSelect={() => undefined}
        view={view()}
        candidates={[]}
        onDecide={() => undefined}
        config={{ ...config, lead_time_min_deliveries: 5 }}
        onSaveConfig={onSaveConfig}
        onSaveThresholds={onSaveThresholds}
      />,
    );
    fireEvent.click(screen.getByTestId('threshold-save'));
    expect(onSaveThresholds).not.toHaveBeenCalled();
    expect(screen.getByText(/blank field stays as it is/)).toBeTruthy();
    fireEvent.change(screen.getByTestId('config-min-deliveries'), { target: { value: '0' } });
    fireEvent.click(screen.getByTestId('config-save'));
    expect(onSaveConfig).not.toHaveBeenCalled();
  });
});

describe('ReplenishmentBoard', () => {
  beforeEach(() => {
    api.apiGet.mockReset();
    api.apiPost.mockReset();
    api.apiPut.mockReset();
  });

  it('calls the existing refresh, config, threshold, served-account, and lead-time endpoints', async () => {
    api.apiGet.mockImplementation((path: string) => {
      if (path === '/api/v1/store-dc/customers') {
        return Promise.resolve({
          customers: [
            { id: 1, code: 'SDC-C1', name: 'SDC-C1' },
            { id: 2, code: 'SDC-C2', name: 'SDC-C2' },
          ],
        });
      }
      if (path === '/api/v1/store-dc/customers/1') return Promise.resolve(view());
      if (path === '/api/v1/store-dc/candidates') {
        return Promise.resolve({ candidates: [{ ...candidate, status: 'confirmed' }] });
      }
      if (path === '/api/v1/store-dc/config') return Promise.resolve(config);
      if (path === '/api/v1/store-dc/lead-times?customer_id=1') {
        return Promise.resolve({
          customer_id: 1,
          lead_time_min_deliveries: 8,
          lead_times: view().lead_times,
        });
      }
      return Promise.reject(new Error(path));
    });
    api.apiPost.mockResolvedValue({ inserted: 1, open_questions: 3, locations_created: 0 });
    api.apiPut.mockImplementation((path: string, body: unknown) => {
      if (path === '/api/v1/store-dc/config') return Promise.resolve({ ...config, ...(body as object), stored: true });
      if (path === '/api/v1/store-dc/customers/1/thresholds') {
        const fields = body as { slow_cover_multiple?: number; unsold_weeks?: number };
        return Promise.resolve({
          customer_id: 1,
          slow_cover_multiple: fields.slow_cover_multiple ?? null,
          unsold_weeks: fields.unsold_weeks ?? null,
          cover: { min_weeks: 4, target_weeks: 6, source: 'fallback' },
        });
      }
      return Promise.resolve(body);
    });

    wrap(<ReplenishmentBoard />);

    await waitFor(() => expect(screen.getByTestId('config-save')).toBeTruthy());
    await waitFor(() =>
      expect(api.apiGet).toHaveBeenCalledWith('/api/v1/store-dc/lead-times?customer_id=1', expect.anything()),
    );
    expect(screen.getByTestId('cover-settings')).toHaveTextContent('at least 8 deliveries');

    fireEvent.click(screen.getByTestId('candidates-refresh'));
    await waitFor(() => expect(api.apiPost).toHaveBeenCalledWith('/api/v1/store-dc/candidates/refresh'));
    await waitFor(() => expect(screen.getByTestId('refresh-note')).toHaveTextContent('New questions: 1. Open questions: 3.'));

    fireEvent.click(screen.getByTestId('config-save'));
    await waitFor(() =>
      expect(api.apiPut).toHaveBeenCalledWith('/api/v1/store-dc/config', {
        lead_time_min_deliveries: 5,
        dc_name_patterns: ['DC'],
        stock_behaviour_min_soh: 1,
      }),
    );

    fireEvent.change(screen.getByTestId('threshold-unsold'), { target: { value: '8' } });
    fireEvent.click(screen.getByTestId('threshold-save'));
    await waitFor(() =>
      expect(api.apiPut).toHaveBeenCalledWith('/api/v1/store-dc/customers/1/thresholds', { unsold_weeks: 8 }),
    );

    fireEvent.click(screen.getByTestId('served-customer-2').querySelector('input') as HTMLInputElement);
    fireEvent.click(screen.getByTestId('served-save-4'));
    await waitFor(() =>
      expect(api.apiPut).toHaveBeenCalledWith('/api/v1/store-dc/candidates/4/served-accounts', {
        customer_ids: [1, 2],
        context_customer_id: 1,
        visible_customer_ids: [1, 2],
      }),
    );

    const before = api.apiGet.mock.calls.filter((call) => String(call[0]).includes('/lead-times')).length;
    fireEvent.click(screen.getByTestId('lead-time-reload'));
    await waitFor(() => {
      const after = api.apiGet.mock.calls.filter((call) => String(call[0]).includes('/lead-times')).length;
      expect(after).toBeGreaterThan(before);
    });
  });
});
