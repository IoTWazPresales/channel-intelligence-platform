import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { roleState } = vi.hoisted(() => ({ roleState: { current: 'admin' } }));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/settings',
}));

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

const PROFILE = {
  tenant_id: 'default',
  constraint_axis: 'money',
  over_budget_action: 'require_reapproval',
  reservation_source: 'derived_from_profit',
  pm_attribution_mode: 'business_line',
  overrides_present: [],
  vat_rate_pct: 0.15,
  hard_enforce_budget: true,
  money_ceiling_usd: null,
  support_norms_trailing_quarters: 4,
};

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
        return PROFILE;
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
      if (String(path).includes('/api/v1/dashboards/templates')) {
        return { items: [] };
      }
      if (String(path).endsWith('/capabilities')) {
        return { live_fetch: false, browser_available: false, settings: { missing: [] }, providers: [] };
      }
      if (String(path).includes('/api/v1/tenant-settings')) {
        return { settings: {}, known_keys: [] };
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

  it('leaves the VAT rate empty until the tenant sets one (Opus R-05)', async () => {
    roleState.current = 'admin';
    wrap();
    const vat = (await screen.findByTestId('tenant-profile-vat-rate')) as HTMLInputElement;
    expect(vat.value).toBe('');
    const types = (await screen.findByTestId('tenant-profile-promotion-types')) as HTMLTextAreaElement;
    const channels = (await screen.findByTestId('tenant-profile-channels')) as HTMLTextAreaElement;
    const promote = (await screen.findByTestId('tenant-profile-stock-promote-type')) as HTMLInputElement;
    expect(types.value).toBe('');
    expect(channels.value).toBe('');
    expect(promote.value).toBe('');
  });

  it('leaves currency, time zone, VAT by country and margins empty until set (Warren 2026-11-27)', async () => {
    roleState.current = 'admin';
    wrap();
    for (const id of [
      'tenant-profile-vat-by-country',
      'tenant-profile-currency-code',
      'tenant-profile-reporting-timezone',
      'tenant-profile-customer-margin',
      'tenant-profile-customer-rebate',
      'tenant-profile-distributor-margin',
      'tenant-profile-below-srp-tolerance',
    ]) {
      const el = (await screen.findByTestId(id)) as HTMLInputElement;
      expect(el.value).toBe('');
    }
  });

  it('saves currency, time zone, VAT by country and margins on the tenant profile', async () => {
    roleState.current = 'admin';
    apiPut.mockImplementation(async () => ({ ...PROFILE, overrides_present: [] }));
    wrap();
    await screen.findByText(/Overrides currently set/);
    const set = async (id: string, value: string) => {
      const el = (await screen.findByTestId(id)) as HTMLInputElement;
      fireEvent.change(el, { target: { value } });
      expect(el.value).toBe(value);
    };
    await set('tenant-profile-vat-by-country', 'gb 0.2\nIE=0.23');
    await set('tenant-profile-currency-code', 'gbp');
    await set('tenant-profile-reporting-timezone', 'Europe/London');
    await set('tenant-profile-customer-margin', '0.1');
    await set('tenant-profile-customer-rebate', '0.02');
    await set('tenant-profile-distributor-margin', '0.05');
    fireEvent.click(await screen.findByTestId('tenant-profile-save'));
    await waitFor(() => expect(apiPut).toHaveBeenCalled());
    const [path, body] = apiPut.mock.calls[0];
    expect(path).toBe('/api/v1/auth/tenant-commercial-profile');
    expect(body).toMatchObject({
      vat_rate_by_country: { GB: 0.2, IE: 0.23 },
      currency_code: 'GBP',
      reporting_timezone: 'Europe/London',
      profit_reservation_margins: {
        customer_margin_pct: 0.1,
        customer_rebate_pct: 0.02,
        distributor_margin_pct: 0.05,
      },
    });
  });

  it('hides the shipping digest recipients panel for non-admin', async () => {
    roleState.current = 'steward';
    wrap();
    expect(await screen.findByTestId('tenant-profile-heading')).toBeInTheDocument();
    expect(screen.queryByTestId('shipping-mailer-recipients-heading')).not.toBeInTheDocument();
  });
});
