import React from 'react';
import { screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { PaymentEvidenceOverlayPanel } from './PaymentEvidenceOverlay';

vi.mock('@/lib/api', () => ({
  apiGet: (url: string) => {
    if (url.includes('/payment-evidence/overlay')) {
      return Promise.resolve({
        row_count: 3375,
        distinct_file_case_codes: 2544,
        cip_case_count: 311,
        matched_cip_case_count: 264,
        unmatched_cip_case_count: 47,
        unmatched_file_case_count: 2280,
        match_rate: 0.8489,
        pending_row_count: 80,
        pending_with_comment_count: 16,
        pending_rows: [
          {
            id: 1,
            external_case_code: 'C25659655',
            payment_status: 'to_be_clarified',
            latest_comment: 'overclaim 75 units, please check and update.',
            case_id: null,
            currency_code: 'USD',
          },
        ],
        unmatched_cip_sample: ['BATCH0-SMOKE-001'],
        unmatched_file_sample: ['C19A50693'],
        unmatched_file_rows: [
          {
            id: 88,
            external_case_code: 'C19A50693',
            case_id: null,
            payment_status: 'closed',
            amount: 1200,
            currency_code: 'USD',
            customer_token: 'HIST-CUST',
            evidence_basis: 'source_attested',
          },
        ],
        paid_note:
          'Paid on the ZAR open book only sums linked evidence in the case currency. This ASUS pending report is almost all USD, so it does not move R0 paid / R6.0m outstanding.',
        not_claim_evidence: true,
        match_rule: 'exact case_code == Case ID; no fuzzy; unmatched stays reviewable',
      });
    }
    return Promise.resolve({});
  },
}));

describe('PaymentEvidenceOverlayPanel', () => {
  it('shows exact Case ID match rates and Latest Comment on pending rows', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    renderWithProviders(
      <QueryClientProvider client={qc}>
        <PaymentEvidenceOverlayPanel />
      </QueryClientProvider>,
    );
    await waitFor(() => {
      expect(screen.getByText(/264 \/ 311/)).toBeInTheDocument();
    });
    expect(screen.getByTestId('cpor-payment-overlay')).toBeInTheDocument();
    expect(screen.getByText(/overclaim 75 units/i)).toBeInTheDocument();
    expect(screen.getByTestId('cpor-payment-paid-note')).toHaveTextContent(/does not move R0 paid/i);
    expect(screen.getByText(/historical source attestation/i)).toBeInTheDocument();
    const unmatched = screen.getByRole('link', { name: /C19A50693/i });
    expect(unmatched).toHaveAttribute(
      'href',
      '/commercial-planner/cpor-cases/payment-evidence-import?code=C19A50693',
    );
    const pending = screen.getByRole('link', { name: /C25659655/i });
    expect(pending).toHaveAttribute(
      'href',
      '/commercial-planner/cpor-cases/payment-evidence-import?code=C25659655',
    );
  });
});
