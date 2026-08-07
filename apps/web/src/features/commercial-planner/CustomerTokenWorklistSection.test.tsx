/**
 * Unit 6b — CustomerTokenWorklistSection: STAMP requiresTarget + opts.target apply path.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactElement } from 'react';
import { CustomerTokenWorklistSection } from './CustomerTokenWorklistSection';

const apiGet = vi.fn();
const apiPost = vi.fn();

vi.mock('@/lib/api', () => ({
  apiGet: (...args: unknown[]) => apiGet(...args),
  apiPost: (...args: unknown[]) => apiPost(...args),
}));

function wrap(ui: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe('CustomerTokenWorklistSection', () => {
  beforeEach(() => {
    apiGet.mockImplementation(async (path: string) => {
      if (path.includes('/minted-aliases')) return { aliases: [], total: 0 };
      return {
        items: [
          {
            item_key: 'sadc - compuspeed',
            norm_token: 'sadc - compuspeed',
            sample_token: 'sadc - Compuspeed',
            line_count: 3,
            bucket: 'specificity',
            preferred_target_id: 107,
            stamp_enabled: true,
            conflict: false,
            competing_customer_ids: [],
            dispositions: [],
            alias_candidates: [
              {
                targetKey: '107',
                label: 'TBH (id 107)',
                meta: { customer_id: 107, is_open_channel: false, preferred: true },
              },
              {
                targetKey: '1',
                label: 'Open Channel (id 1)',
                meta: { customer_id: 1, is_open_channel: true, preferred: false },
              },
            ],
          },
          {
            item_key: 'sadc - dcc',
            norm_token: 'sadc - dcc',
            sample_token: 'sadc - dcc',
            line_count: 2,
            bucket: 'genuine_conflict',
            preferred_target_id: null,
            stamp_enabled: false,
            conflict: true,
            competing_customer_ids: [47, 299],
            dispositions: ['scoped', 'merge', 'data_error'],
            alias_candidates: [
              { targetKey: '47', label: 'Eshop (id 47)', meta: { is_open_channel: false } },
              { targetKey: '299', label: 'Amazon (id 299)', meta: { is_open_channel: false } },
            ],
          },
        ],
        total: 2,
        bucket_counts: { all: 2, clean: 0, specificity: 1, genuine_conflict: 1, empty_token: 0 },
        open_channel_customer_id: 1,
      };
    });
    apiPost.mockReset();
  });

  it('renders target picker and prefers named customer (not OPEN_CHANNEL)', async () => {
    wrap(<CustomerTokenWorklistSection />);
    await screen.findByTestId('customer-token-section');
    await screen.findByText(/sadc - Compuspeed/i);
    await userEvent.click(screen.getByText(/sadc - Compuspeed/i));
    expect(await screen.findByTestId('customer-token-target-picker')).toBeInTheDocument();
    expect(screen.getByTestId('customer-token-target-107')).toBeInTheDocument();
    expect(screen.getByTestId('customer-token-target-1')).toBeInTheDocument();
  });

  it('posts stamp apply with target_customer_id from opts.target only', async () => {
    apiPost.mockImplementation(async (path: string, body: Record<string, unknown>) => {
      if (path.includes('/stamp/preview')) {
        return {
          line_count: 3,
          target_customer_label: 'TBH (id 107)',
          current_resolution_breakdown: { null: 3 },
          would_create_alias: true,
          sample_lines: [],
        };
      }
      if (path.includes('/stamp/apply')) {
        return { alias_id: 9, stamped_count: 3, norm_token: 'sadc - compuspeed', target_customer_id: body.target_customer_id };
      }
      return {};
    });

    wrap(<CustomerTokenWorklistSection />);
    await screen.findByTestId('customer-token-stamp-sadc - compuspeed');
    await userEvent.click(screen.getByTestId('customer-token-stamp-sadc - compuspeed'));
    expect(await screen.findByTestId('customer-token-stamp-dialog')).toBeInTheDocument();
    expect(screen.getByTestId('customer-token-opts-target')).toHaveTextContent('107');
    await userEvent.click(screen.getByTestId('customer-token-stamp-submit'));
    await waitFor(() => {
      const applyCalls = apiPost.mock.calls.filter((c: unknown[]) => String(c[0]).includes('/stamp/apply'));
      expect(applyCalls.length).toBeGreaterThan(0);
      expect(applyCalls[0][1]).toMatchObject({
        norm_token: 'sadc - compuspeed',
        target_customer_id: 107,
      });
    });
  });

  it('shows conflict dispositions without inline resolve control', async () => {
    wrap(<CustomerTokenWorklistSection />);
    await screen.findByText(/sadc - dcc/i);
    await userEvent.click(screen.getByText(/sadc - dcc/i));
    expect(await screen.findByTestId('customer-token-drawer-conflict')).toBeInTheDocument();
    expect(screen.getByTestId('customer-token-drawer-conflict')).toHaveTextContent('SCOPED');
    expect(screen.getByTestId('customer-token-drawer-conflict')).toHaveTextContent('MERGE');
    expect(screen.getByTestId('customer-token-drawer-conflict')).toHaveTextContent('DATA_ERROR');
    expect(screen.queryByTestId('customer-token-conflict-override')).not.toBeInTheDocument();
  });
});
