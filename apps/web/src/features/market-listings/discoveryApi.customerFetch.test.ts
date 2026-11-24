import { beforeEach, describe, expect, it, vi } from 'vitest';

import { apiGet } from '@/lib/api';

import {
  fetchCustomers,
  fetchDiscoveryCustomerOptions,
  fetchReportingCustomers,
} from './discoveryApi';
import { customersListUrl } from './listingCustomerScope';

vi.mock('@/lib/api', () => ({
  apiGet: vi.fn(async () => ({ items: [] })),
}));

describe('discovery customer fetch', () => {
  beforeEach(() => {
    vi.mocked(apiGet).mockClear();
  });

  it('fetchDiscoveryCustomerOptions uses reporting_only on empty query', async () => {
    const ac = new AbortController();
    await fetchDiscoveryCustomerOptions('', ac.signal);
    expect(apiGet).toHaveBeenCalledWith(customersListUrl(true), { signal: ac.signal });
  });

  it('fetchDiscoveryCustomerOptions uses full directory search for typed query', async () => {
    const ac = new AbortController();
    await fetchDiscoveryCustomerOptions('ab', ac.signal);
    expect(apiGet).toHaveBeenCalledWith(customersListUrl(false, { q: 'ab' }), { signal: ac.signal });
  });

  it('fetchReportingCustomers is reporting-only', async () => {
    const ac = new AbortController();
    await fetchReportingCustomers(ac.signal);
    expect(apiGet).toHaveBeenCalledWith(customersListUrl(true), { signal: ac.signal });
  });

  it('fetchCustomers searches the full directory', async () => {
    const ac = new AbortController();
    await fetchCustomers('zz', ac.signal);
    expect(apiGet).toHaveBeenCalledWith(customersListUrl(false, { q: 'zz' }), { signal: ac.signal });
  });
});