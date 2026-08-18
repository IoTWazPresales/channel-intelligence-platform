import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { roleState } = vi.hoisted(() => ({ roleState: { current: 'admin' } }));

vi.mock('@/features/shell/useCurrentUser', () => ({
  useCurrentUser: () => ({ data: { id: 'u1', role: roleState.current } }),
}));

vi.mock('@/lib/wipeAvailability', () => ({
  loadWipeAvailability: async () => ({ wipe_enabled: false }),
}));

const apiGet = vi.fn();
const apiPut = vi.fn();
const apiPost = vi.fn();
const apiPatch = vi.fn();
const apiDelete = vi.fn();

vi.mock('@/lib/api', () => ({
  apiGet: (...args: unknown[]) => apiGet(...args),
  apiPut: (...args: unknown[]) => apiPut(...args),
  apiPost: (...args: unknown[]) => apiPost(...args),
  apiPatch: (...args: unknown[]) => apiPatch(...args),
  apiDelete: (...args: unknown[]) => apiDelete(...args),
  getApiBase: () => '',
  safeDisplayError: (err: unknown) => String(err),
}));

import SettingsPage from './page';

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SettingsPage />
    </QueryClientProvider>
  );
}

describe('SettingsPage semantic overlay gate', () => {
  beforeEach(() => {
    roleState.current = 'admin';
    apiGet.mockImplementation(async (path: string) => {
      if (String(path).includes('tenant-commercial-profile')) {
        return {
          tenant_id: 'default',
          constraint_axis: 'money',
          over_budget_action: 'require_reapproval',
          reservation_source: 'derived_from_profit',
          pm_attribution_mode: 'business_line',
          overrides_present: [],
          hard_enforce_budget: true,
          money_ceiling_usd: null,
          support_norms_trailing_quarters: 4,
        };
      }
      if (String(path).includes('semantics/overlay')) {
        return {
          tenant_id: 'default',
          overlay: { metrics: {} },
          base_metrics: [],
          compose_ops: ['ratio', 'alias'],
        };
      }
      if (String(path).includes('shipping-mailer/recipients')) {
        return { items: [] };
      }
      return {};
    });
  });

  it('shows the semantic catalog panel for admin', async () => {
    roleState.current = 'admin';
    wrap();
    expect(await screen.findByTestId('semantic-overlay-heading')).toBeInTheDocument();
  });

  it('hides the semantic catalog panel for non-admin', async () => {
    roleState.current = 'steward';
    wrap();
    expect(await screen.findByTestId('tenant-profile-heading')).toBeInTheDocument();
    expect(screen.queryByTestId('semantic-overlay-heading')).not.toBeInTheDocument();
  });

  it('shows the shipping digest recipients panel for admin', async () => {
    roleState.current = 'admin';
    wrap();
    expect(await screen.findByTestId('shipping-mailer-recipients-heading')).toBeInTheDocument();
  });

  it('hides the shipping digest recipients panel for non-admin', async () => {
    roleState.current = 'steward';
    wrap();
    expect(await screen.findByTestId('tenant-profile-heading')).toBeInTheDocument();
    expect(screen.queryByTestId('shipping-mailer-recipients-heading')).not.toBeInTheDocument();
  });
});
