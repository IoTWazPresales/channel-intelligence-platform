import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { SiteConfirmBar } from './SiteConfirmBar';

const queue = {
  data: { items: [] as { id: number; customer_name: string; domain: string }[] },
  isPending: false,
  isError: false,
  error: null as unknown,
  refetch: vi.fn(),
};
const decide = { mutate: vi.fn(), isPending: false };

vi.mock('./discoveryApi', () => ({
  discoveryError: () => 'Could not load sites',
  useSiteCandidates: () => queue,
  useDecideSiteCandidate: () => decide,
}));

describe('SiteConfirmBar', () => {
  beforeEach(() => {
    queue.data = { items: [] };
    queue.isPending = false;
    queue.isError = false;
    decide.mutate.mockClear();
    decide.isPending = false;
  });

  it('renders nothing when there is nothing to confirm', () => {
    const { container } = render(<SiteConfirmBar />);
    expect(container).toBeEmptyDOMElement();
  });

  it('confirms and rejects the proposed site', () => {
    queue.data = { items: [{ id: 7, customer_name: 'North shop', domain: 'north.example.test' }] };
    render(<SiteConfirmBar />);
    expect(screen.getByTestId('site-confirm-bar')).toHaveTextContent('North shop · north.example.test');
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
    fireEvent.click(screen.getByRole('button', { name: 'Reject' }));
    expect(decide.mutate).toHaveBeenNthCalledWith(1, { id: 7, action: 'confirm' });
    expect(decide.mutate).toHaveBeenNthCalledWith(2, { id: 7, action: 'reject' });
  });
});
