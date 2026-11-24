import React from 'react';
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { apiPost } from '@/lib/api';
import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { DiscoveryLens } from './DiscoveryLens';
import { marketLensFromLocation } from './MarketChrome';

const state = vi.hoisted(() => ({
  missing: [] as string[],
  live: true,
  role: 'steward',
  queue: [71, 72],
}));

vi.mock('@/features/shell/useCurrentUser', () => ({
  useCurrentUser: () => ({ data: { id: 'fixture-user', tenant_id: 'fixture-tenant', role: state.role } }),
}));
vi.mock('@/lib/api', () => ({
  safeDisplayError: (error: unknown) => error instanceof Error ? error.message : 'Request failed',
  apiGet: vi.fn(async (url: string) => {
    if (url.endsWith('/capabilities')) return {
      live_fetch: state.live, browser_available: false, providers: [], settings: { missing: state.missing },
    };
    if (url.includes('/site-candidates')) return {
      items: state.queue.map((id) => ({
        id, customer_id: 83, customer_name: 'Fixture customer', domain: `candidate-${id}.test`,
        evidence: { name_match: { exact: true }, sources: ['email'] }, created_at: null,
      })),
    };
    if (url.includes('/customers')) return {
      items: [{ id: 83, customer_name: 'Fixture customer', customer_code: 'NEVER-DISPLAY', reports_expected: false }],
    };
    if (url.includes('/previews/')) return {
      preview_id: 'fixture-preview', status: 'queued', progress: { done: 0, total: 1 }, applied: null, result: null,
    };
    throw new Error(`Unexpected GET ${url}`);
  }),
  apiPut: vi.fn(),
  apiPost: vi.fn(async (url: string) => {
    if (url.includes('/site-candidates/')) {
      const id = Number(url.split('/').at(-1));
      state.queue = state.queue.filter((value) => value !== id);
      return { id, status: 'confirmed', site_created: false };
    }
    return { preview_id: 'fixture-preview', status: 'queued' };
  }),
}));

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return renderWithProviders(<QueryClientProvider client={client}><DiscoveryLens /></QueryClientProvider>);
}

describe('DiscoveryLens', () => {
  beforeEach(() => {
    state.missing = [];
    state.live = true;
    state.role = 'steward';
    state.queue = [71, 72];
    vi.clearAllMocks();
  });

  it('routes the new Market lens and points missing settings to Discovery settings', async () => {
    expect(marketLensFromLocation('/listing-capture', new URLSearchParams('tab=discovery'))).toBe('discovery');
    state.missing = ['tenant.country', 'tenant.domain_endings'];
    mount();
    expect(await screen.findByRole('link', { name: 'Settings → Discovery' })).toHaveAttribute('href', '/settings#discovery');
    expect(screen.getByRole('button', { name: 'Discover all reporting customers' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Discover listings with no product' })).toBeEnabled();
    expect(apiPost).not.toHaveBeenCalled();
  });

  it('disables every preview when live page checking is off', async () => {
    state.live = false;
    mount();
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(/Live page checking is off on this server/);
    expect(screen.queryByTestId('discover-reporting-reason')).not.toBeInTheDocument();
    for (const button of screen.getAllByRole('button', { name: /^Discover/ })) expect(button).toBeDisabled();
  });

  it('enables Discover one customer when settings are ready and a customer is picked', async () => {
    mount();
    const btn = await screen.findByRole('button', { name: 'Discover one customer' });
    expect(btn).toBeDisabled();
    expect(await screen.findByTestId('discover-customer-reason')).toHaveTextContent(/Choose a customer/);
    fireEvent.change(await screen.findByLabelText('Customer to discover'), { target: { value: 'Fixture' } });
    fireEvent.click(await screen.findByRole('option', { name: 'Fixture customer' }));
    await waitFor(() => expect(btn).toBeEnabled());
    expect(screen.queryByTestId('discover-customer-reason')).not.toBeInTheDocument();
  });

  it('starts the reporting preview only on the button and never applies automatically', async () => {
    mount();
    const button = await screen.findByRole('button', { name: 'Discover all reporting customers' });
    await waitFor(() => expect(button).toBeEnabled());
    expect(apiPost).not.toHaveBeenCalled();
    fireEvent.click(button);
    await screen.findByText(/Nothing saved yet/);
    expect(apiPost).toHaveBeenCalledWith('/api/v1/listing-capture/discovery/previews', { scope: 'reporting' });
    expect(vi.mocked(apiPost).mock.calls.some(([url]) => url.endsWith('/apply'))).toBe(false);
  });

  it('accepts an arbitrary domain for a non-reporting customer and displays names only', async () => {
    mount();
    fireEvent.change(await screen.findByLabelText('Customer for this site'), { target: { value: 'Fixture' } });
    fireEvent.click(await screen.findByRole('option', { name: 'Fixture customer' }));
    fireEvent.change(screen.getByLabelText('Domain'), { target: { value: 'custom-host.test' } });
    fireEvent.click(screen.getByRole('button', { name: 'Discover a site' }));
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith('/api/v1/listing-capture/discovery/previews', {
      scope: 'domain', customer_id: 83, domain: 'custom-host.test',
    }));
    expect(screen.queryByText('NEVER-DISPLAY')).not.toBeInTheDocument();
  });

  it('shows site evidence and sends one-click confirm and reject decisions', async () => {
    mount();
    const first = await screen.findByTestId('site-candidate-71');
    expect(within(first).getByText('Name matches')).toBeInTheDocument();
    fireEvent.click(within(first).getByRole('button', { name: 'Confirm' }));
    await waitFor(() => expect(screen.queryByTestId('site-candidate-71')).not.toBeInTheDocument());
    expect(apiPost).toHaveBeenCalledWith('/api/v1/listing-capture/discovery/site-candidates/71', { action: 'confirm' });
    const second = screen.getByTestId('site-candidate-72');
    fireEvent.click(within(second).getByRole('button', { name: 'Reject' }));
    await waitFor(() => expect(screen.queryByTestId('site-candidate-72')).not.toBeInTheDocument());
    expect(apiPost).toHaveBeenCalledWith('/api/v1/listing-capture/discovery/site-candidates/72', { action: 'reject' });
  });

  it('keeps discovery actions and queue writes out of the read-only view', async () => {
    state.role = 'viewer';
    mount();
    await screen.findByTestId('site-candidate-71');
    expect(screen.queryByRole('button', { name: /^Preview/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Confirm' })).not.toBeInTheDocument();
  });
});
