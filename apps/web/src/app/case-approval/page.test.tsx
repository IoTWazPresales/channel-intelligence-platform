import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, screen, waitFor } from '@testing-library/react';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import CaseApprovalPage from './page';

const apiGet = vi.fn();
const apiPost = vi.fn();

vi.mock('@/lib/api', () => ({
  apiGet: (...args: unknown[]) => apiGet(...args),
  apiPost: (...args: unknown[]) => apiPost(...args),
  safeDisplayError: (err: unknown) => (err instanceof Error ? err.message : 'error'),
}));

const TOKEN = 'a'.repeat(43);

const SUMMARY = {
  case_code: 'C24',
  case_name: 'April',
  customer_name: 'Takealot',
  window_start: '2026-04-01',
  window_end: '2026-04-30',
  currency: 'ZAR',
  export_version: 3,
  lines: [
    { product: 'Widget', estimate_qty: 10, result_qty: 8, support_per_unit: 5, support_total: 40 },
    { product: 'Widget', estimate_qty: 2, result_qty: 2, support_per_unit: 5, support_total: 10 },
  ],
  support_total: 50,
};

describe('CaseApprovalPage', () => {
  beforeEach(() => {
    apiGet.mockReset();
    apiPost.mockReset();
    window.history.replaceState(null, '', `/case-approval?token=${TOKEN}`);
  });

  it('shows one case and records an approval with name and comment', async () => {
    apiGet.mockResolvedValue(SUMMARY);
    apiPost.mockResolvedValue({ ok: true });
    renderWithProviders(<CaseApprovalPage />);

    expect(await screen.findByText(/C24 · April · Takealot/)).toBeTruthy();
    expect(screen.getByTestId('case-approval-lines').querySelectorAll('li')).toHaveLength(2);
    expect(apiGet).toHaveBeenCalledWith(`/api/v1/case-approval?token=${TOKEN}`);

    fireEvent.change(screen.getByTestId('case-approval-name'), { target: { value: 'Ada Buyer' } });
    fireEvent.change(screen.getByTestId('case-approval-comment'), { target: { value: 'Agreed' } });
    fireEvent.click(screen.getByTestId('case-approval-approve'));

    await waitFor(() => expect(screen.getByTestId('case-approval-done')).toBeTruthy());
    expect(apiPost).toHaveBeenCalledWith('/api/v1/case-approval', {
      token: TOKEN,
      decision: 'approved',
      signer_name: 'Ada Buyer',
      comment: 'Agreed',
    });
  });

  it('does not send a rejection without a name and comment', async () => {
    apiGet.mockResolvedValue(SUMMARY);
    renderWithProviders(<CaseApprovalPage />);
    await screen.findByText(/C24 · April · Takealot/);

    fireEvent.click(screen.getByTestId('case-approval-reject'));
    expect(apiPost).not.toHaveBeenCalled();
  });

  it('shows the not-valid message for a short token without calling the API', async () => {
    window.history.replaceState(null, '', '/case-approval?token=short');
    renderWithProviders(<CaseApprovalPage />);
    expect(await screen.findByTestId('case-approval-error')).toBeTruthy();
    expect(apiGet).not.toHaveBeenCalled();
  });
});
