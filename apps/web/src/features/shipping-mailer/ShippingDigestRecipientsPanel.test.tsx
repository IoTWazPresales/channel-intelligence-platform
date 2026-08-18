import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ShippingDigestRecipientsPanel } from './ShippingDigestRecipientsPanel';
import type { ShippingMailerRecipient } from './types';

const apiGet = vi.fn();
const apiPost = vi.fn();
const apiPatch = vi.fn();
const apiDelete = vi.fn();

vi.mock('@/lib/api', () => ({
  apiGet: (...args: unknown[]) => apiGet(...args),
  apiPost: (...args: unknown[]) => apiPost(...args),
  apiPatch: (...args: unknown[]) => apiPatch(...args),
  apiDelete: (...args: unknown[]) => apiDelete(...args),
  safeDisplayError: (err: unknown) => (err instanceof Error ? err.message : String(err)),
}));

const seed: ShippingMailerRecipient[] = [
  {
    id: 1,
    tenant_id: 'default',
    address: 'Leigh_Sharpe@asus.com',
    display_name: null,
    enabled: true,
    added_by: 'system:seed',
    created_at: '2026-08-18T10:00:00+00:00',
    updated_at: '2026-08-18T10:00:00+00:00',
  },
  {
    id: 2,
    tenant_id: 'default',
    address: 'Wayne_Holt@asus.com',
    display_name: null,
    enabled: true,
    added_by: 'system:seed',
    created_at: '2026-08-18T10:00:01+00:00',
    updated_at: '2026-08-18T10:00:01+00:00',
  },
];

function wrap(ui: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe('ShippingDigestRecipientsPanel', () => {
  beforeEach(() => {
    apiGet.mockReset();
    apiPost.mockReset();
    apiPatch.mockReset();
    apiDelete.mockReset();
    apiGet.mockResolvedValue({ items: seed });
  });

  it('lists recipients from the API', async () => {
    wrap(<ShippingDigestRecipientsPanel />);
    expect(await screen.findByTestId('shipping-mailer-recipients-heading')).toHaveTextContent(
      'Shipping digest recipients',
    );
    expect(await screen.findByText('Leigh_Sharpe@asus.com')).toBeInTheDocument();
    expect(screen.getByText('Wayne_Holt@asus.com')).toBeInTheDocument();
  });

  it('blocks add without calling the API when the address is invalid', async () => {
    const user = userEvent.setup();
    wrap(<ShippingDigestRecipientsPanel />);
    await screen.findByTestId('shipping-mailer-recipients-add-address');
    await user.type(screen.getByTestId('shipping-mailer-recipients-add-address'), 'not-an-email');
    await user.click(screen.getByTestId('shipping-mailer-recipients-add'));
    expect(await screen.findByTestId('shipping-mailer-recipients-validation-error')).toHaveTextContent(
      'Enter a valid email address.',
    );
    expect(apiPost).not.toHaveBeenCalled();
  });

  it('posts a new recipient and refetches', async () => {
    const user = userEvent.setup();
    const created: ShippingMailerRecipient = {
      id: 9,
      tenant_id: 'default',
      address: 'extra@example.com',
      display_name: 'Extra',
      enabled: true,
      added_by: 'admin@example.com',
      created_at: '2026-08-18T12:00:00+00:00',
      updated_at: '2026-08-18T12:00:00+00:00',
    };
    apiPost.mockResolvedValue(created);
    apiGet.mockResolvedValueOnce({ items: seed }).mockResolvedValueOnce({ items: [...seed, created] });
    wrap(<ShippingDigestRecipientsPanel />);
    await screen.findByTestId('shipping-mailer-recipients-add-address');
    await user.type(screen.getByTestId('shipping-mailer-recipients-add-address'), 'extra@example.com');
    await user.type(screen.getByTestId('shipping-mailer-recipients-add-name'), 'Extra');
    await user.click(screen.getByTestId('shipping-mailer-recipients-add'));
    await waitFor(() => expect(apiPost).toHaveBeenCalled());
    expect(apiPost.mock.calls[0][0]).toBe('/api/v1/shipping-mailer/recipients');
    expect(apiPost.mock.calls[0][1]).toEqual({ address: 'extra@example.com', display_name: 'Extra' });
    expect(await screen.findByText('extra@example.com')).toBeInTheDocument();
  });

  it('toggles enabled via PATCH', async () => {
    const user = userEvent.setup();
    apiPatch.mockResolvedValue({ ...seed[0], enabled: false });
    wrap(<ShippingDigestRecipientsPanel />);
    const toggle = await screen.findByTestId('shipping-mailer-recipients-enabled-1');
    await user.click(toggle);
    await waitFor(() => expect(apiPatch).toHaveBeenCalled());
    expect(apiPatch.mock.calls[0][0]).toBe('/api/v1/shipping-mailer/recipients/1');
    expect(apiPatch.mock.calls[0][1]).toEqual({ enabled: false });
  });

  it('deletes after confirm', async () => {
    const user = userEvent.setup();
    apiDelete.mockResolvedValue(undefined);
    wrap(<ShippingDigestRecipientsPanel />);
    await user.click(await screen.findByTestId('shipping-mailer-recipients-delete-1'));
    await user.click(await screen.findByTestId('shipping-mailer-recipients-delete-confirm'));
    await waitFor(() => expect(apiDelete).toHaveBeenCalledWith('/api/v1/shipping-mailer/recipients/1'));
  });
});
