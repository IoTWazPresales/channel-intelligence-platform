import React from 'react';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { apiPut } from '@/lib/api';
import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { DiscoverySettingsPanel } from './DiscoverySettingsPanel';

const state = vi.hoisted(() => ({
  stored: {} as Record<string, unknown>,
  invalid: false,
  role: 'steward',
}));

vi.mock('@/features/shell/useCurrentUser', () => ({
  useCurrentUser: () => ({ data: { id: 'fixture-user', tenant_id: 'fixture-tenant', role: state.role } }),
}));
vi.mock('@/lib/api', () => ({
  safeDisplayError: (error: unknown) => error instanceof Error ? error.message : 'Request failed',
  apiGet: vi.fn(async (url: string) => url.endsWith('/capabilities') ? {
    live_fetch: true, browser_available: false, settings: { missing: [] },
    providers: [
      { id: 'ddg_html', label: 'DuckDuckGo (HTML)', needs_url: false },
      { id: 'ddg_lite', label: 'DuckDuckGo (Lite)', needs_url: false },
      { id: 'searxng', label: 'SearXNG (your own server)', needs_url: true },
    ],
  } : { settings: state.stored, known_keys: [] }),
  apiPost: vi.fn(),
  apiPut: vi.fn(async (url: string, body: { value: unknown }) => {
    if (state.invalid) throw new Error('country code must be two capital letters');
    return { key: url.split('/').at(-1), value: body.value };
  }),
}));

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderWithProviders(<QueryClientProvider client={client}><DiscoverySettingsPanel /></QueryClientProvider>);
}

describe('DiscoverySettingsPanel', () => {
  beforeEach(() => {
    state.stored = {};
    state.invalid = false;
    state.role = 'steward';
    vi.clearAllMocks();
  });

  it('has no seeded country, endings, providers or schedule, and writes nothing on render', async () => {
    mount();
    expect(await screen.findByLabelText('Country code')).toHaveValue('');
    expect(screen.getByLabelText('Country name')).toHaveValue('');
    expect(screen.getByLabelText('Domain endings')).toHaveValue('');
    expect(screen.getByLabelText('Excluded domains')).toHaveValue('');
    expect(screen.getByRole('checkbox', { name: 'DuckDuckGo (HTML)' })).not.toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'DuckDuckGo (Lite)' })).not.toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'Scheduled discovery (off by default)' })).not.toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'Use a browser when a page needs one' })).toBeDisabled();
    expect(screen.getByText('Not installed on the server')).toBeInTheDocument();
    expect(apiPut).not.toHaveBeenCalled();
  });

  it('shows a server validation error inline beside the country fields', async () => {
    state.invalid = true;
    mount();
    fireEvent.change(await screen.findByLabelText('Country code'), { target: { value: 'Q' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save country' }));
    await waitFor(() => expect(screen.getByLabelText('Country code')).toHaveAttribute('aria-invalid', 'true'));
    expect(screen.getAllByText('country code must be two capital letters').length).toBeGreaterThan(0);
    expect(screen.getByLabelText('Country code')).toHaveValue('Q');
  });

  it('loads tenant-provided values and saves only the requested key', async () => {
    state.stored = {
      'tenant.country': { code: 'QX', name: 'Fixture region' },
      'tenant.domain_endings': ['.test'],
      'discovery.scheduled_run_debounce_hours': 24,
      'discovery.confirm_coalesce_seconds': 120,
    };
    mount();
    expect(await screen.findByLabelText('Country name')).toHaveValue('Fixture region');
    expect(screen.getByLabelText('Domain endings')).toHaveValue('.test');
    fireEvent.click(screen.getByRole('checkbox', { name: 'Scheduled discovery (off by default)' }));
    expect(apiPut).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Save scheduled discovery' }));
    await waitFor(() => {
      expect(apiPut).toHaveBeenCalledTimes(1);
      expect(apiPut).toHaveBeenCalledWith(
        '/api/v1/tenant-settings/discovery.schedule_enabled', { value: true },
      );
    });
  });

  it('preserves the chosen provider order and saves the URL independently', async () => {
    mount();
    fireEvent.click(await screen.findByRole('checkbox', { name: 'DuckDuckGo (HTML)' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'DuckDuckGo (Lite)' }));
    fireEvent.click(screen.getByRole('button', { name: 'Move DuckDuckGo (Lite) up' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save search providers' }));
    await waitFor(() => expect(apiPut).toHaveBeenCalledWith(
      '/api/v1/tenant-settings/discovery.search_providers', { value: ['ddg_lite', 'ddg_html'] },
    ));
    await screen.findByText('Saved.');
    fireEvent.click(screen.getByRole('checkbox', { name: 'SearXNG (your own server)' }));
    fireEvent.change(screen.getByLabelText('SearXNG URL'), { target: { value: 'https://search.fixture.test' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save SearXNG URL' }));
    await waitFor(() => expect(apiPut).toHaveBeenCalledWith(
      '/api/v1/tenant-settings/discovery.searxng_url', { value: 'https://search.fixture.test' },
    ));
  });

  it('does not turn scheduled discovery on until both timings are saved', async () => {
    mount();
    fireEvent.click(await screen.findByRole('checkbox', { name: 'Scheduled discovery (off by default)' }));
    expect(screen.getByRole('button', { name: 'Save scheduled discovery' })).toBeDisabled();
    expect(apiPut).not.toHaveBeenCalled();
  });

  it('is hidden from users who cannot edit discovery settings', () => {
    state.role = 'viewer';
    mount();
    expect(screen.queryByTestId('discovery-settings')).not.toBeInTheDocument();
    expect(apiPut).not.toHaveBeenCalled();
  });
});
