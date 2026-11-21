import React from 'react';
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { apiPost } from '@/lib/api';
import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { DiscoveryPreview } from './DiscoveryPreview';

const state = vi.hoisted(() => ({ polls: 0, running: false, status: 'done', failApply: false }));

vi.mock('@/features/shell/useCurrentUser', () => ({
  useCurrentUser: () => ({ data: { id: 'fixture-user', tenant_id: 'fixture-tenant', role: 'steward' } }),
}));
vi.mock('@/lib/api', () => ({
  safeDisplayError: (error: unknown) => error instanceof Error ? error.message : 'Request failed',
  apiPut: vi.fn(),
  apiGet: vi.fn(async () => {
    state.polls += 1;
    const running = state.running && state.polls === 1;
    return {
      preview_id: 'preview-one', status: running ? 'running' : state.status,
      progress: { done: running ? 0 : 1, total: 1 }, applied: null,
      result: running ? null : {
        scope: 'customer', created_at: '', settings: {
          country: { code: 'QX', name: 'Fixture region' }, domain_endings: ['.test'], search_providers: [],
        },
        search: { status: 'unavailable', provider_used: null, attempts: [{ provider: 'ddg_html', status: 'blocked', http_status: 202, reason: 'anomaly_page' }] },
        customers: [{
          customer_id: 91, customer_name: 'Fixture merchant', reporting: true, notes: [],
          candidates: [
            { item_id: 'c1', domain: 'matched.test', outcome: 'auto_accept', evidence: { name_match: { exact: true } } },
            { item_id: 'c2', domain: 'review.test', outcome: 'steward_queue', evidence: {} },
          ],
          sites: [{
            domain: 'matched.test', site_key: 'matched', state: 'would_create',
            pages: [{ item_id: 'p1', product_id: 16, product_label: 'Fixture product', url: 'https://matched.test/item', outcome: 'auto_link', how: 'gtin', capture: { price: 0, availability: 'in_stock' } }],
          }],
        }],
        listings: [],
        totals: { sites_auto: 1, sites_review: 1, pages_auto: 1, pages_review: 0, listings_auto: 0, listings_review: 0 },
      },
    };
  }),
  apiPost: vi.fn(async () => {
    if (state.failApply) throw new Error('settings_changed');
    return {
      sites_confirmed: 1, sites_created: 1, sites_queued: 1, pages_linked: 1, pages_queued: 0,
      listings_linked: 0, listings_queued: 0, proposals_created: 1, skipped: [],
    };
  }),
}));

function mount(discard = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidate = vi.spyOn(client, 'invalidateQueries');
  renderWithProviders(
    <QueryClientProvider client={client}>
      <DiscoveryPreview previewId="preview-one" canEdit providers={[{ id: 'ddg_html', label: 'DuckDuckGo (HTML)', needs_url: false }]} onDiscard={discard} />
    </QueryClientProvider>,
  );
  return { invalidate, discard };
}

describe('DiscoveryPreview', () => {
  beforeEach(() => {
    state.polls = 0;
    state.running = false;
    state.status = 'done';
    state.failApply = false;
    vi.clearAllMocks();
  });

  it('renders server outcomes and evidence, with no automatic Apply', async () => {
    mount();
    expect(await screen.findByText('Will be added')).toBeInTheDocument();
    expect(screen.getByText('Goes to review')).toBeInTheDocument();
    expect(screen.getByText('Will be linked (barcode)')).toBeInTheDocument();
    expect(screen.getByText(/Web search was unavailable/)).toBeInTheDocument();
    expect(screen.getByText(/DuckDuckGo \(HTML\): blocked \(202\)/)).toBeInTheDocument();
    expect(screen.getByText('Name matches')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'https://matched.test/item' })).toHaveAttribute('href', 'https://matched.test/item');
    expect(screen.getByText(/Nothing saved yet/)).toBeInTheDocument();
    expect(apiPost).not.toHaveBeenCalled();
  });

  it('polls a running preview and saves only after the Apply dialog is confirmed', async () => {
    state.running = true;
    const { invalidate } = mount();
    await screen.findByText('Checked 0 of 1 customers');
    expect(screen.getByRole('button', { name: /^Apply$/ })).toBeDisabled();
    await waitFor(() => expect(screen.getByRole('button', { name: /^Apply$/ })).toBeEnabled(), { timeout: 5000 });
    expect(state.polls).toBeGreaterThan(1);
    expect(apiPost).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: /^Apply$/ }));
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText(/Save 1 sites, link 1 pages/)).toBeInTheDocument();
    expect(apiPost).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save results' }));
    expect(await screen.findByTestId('discovery-applied')).toHaveTextContent('1 pages linked');
    expect(apiPost).toHaveBeenCalledTimes(1);
    expect(apiPost).toHaveBeenCalledWith('/api/v1/listing-capture/discovery/previews/preview-one/apply');
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['listing-capture'] });
    expect(screen.queryByText(/Nothing saved yet/)).not.toBeInTheDocument();
    // MUI hides background controls from accessibility queries until the dialog finishes closing.
    await waitFor(() => expect(dialog).not.toBeInTheDocument());
    expect(screen.getByRole('button', { name: /^Apply$/ })).toBeDisabled();
  });

  it('cancel and discard make no write requests', async () => {
    const { discard } = mount();
    await screen.findByText('Will be added');
    fireEvent.click(screen.getByRole('button', { name: /^Apply$/ }));
    const dialog = screen.getByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    await waitFor(() => expect(dialog).not.toBeInTheDocument());
    expect(apiPost).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Discard' }));
    expect(discard).toHaveBeenCalledTimes(1);
    expect(apiPost).not.toHaveBeenCalled();
  });

  it('leaves failed saves reviewable and explains changed settings', async () => {
    state.failApply = true;
    mount();
    await screen.findByText('Will be added');
    fireEvent.click(screen.getByRole('button', { name: /^Apply$/ }));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Save results' }));
    expect(await screen.findByText(/Settings changed\. Start a new preview before saving/)).toBeInTheDocument();
    expect(screen.queryByTestId('discovery-applied')).not.toBeInTheDocument();
  });

  it('does not allow saving an expired preview', async () => {
    state.status = 'expired';
    mount();
    await screen.findByText(/This preview expired/);
    expect(screen.getByRole('button', { name: /^Apply$/ })).toBeDisabled();
    expect(apiPost).not.toHaveBeenCalled();
  });
});
