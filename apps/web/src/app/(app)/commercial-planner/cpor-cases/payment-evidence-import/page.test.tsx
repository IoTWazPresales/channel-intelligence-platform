import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import CporPaymentEvidenceImportPage from './page';

let searchString = '';

const apiGetMock = vi.fn();

vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(searchString),
  usePathname: () => '/commercial-planner/cpor-cases/payment-evidence-import',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

vi.mock('@/features/promotions-funding/FundingChrome', () => ({
  FundingChrome: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('@/features/commercial-planner/EntitySearchAutocomplete', () => ({
  EntitySearchAutocomplete: () => null,
}));

vi.mock('@/lib/api', () => ({
  apiGet: (...args: unknown[]) => apiGetMock(...args),
  apiPost: vi.fn(),
  apiPostFormData: vi.fn(),
  safeDisplayError: (e: unknown) => (e instanceof Error ? e.message : String(e)),
}));

describe('CporPaymentEvidenceImportPage ?code=', () => {
  beforeEach(() => {
    searchString = '';
    apiGetMock.mockReset();
  });

  function renderPage() {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return renderWithProviders(
      <QueryClientProvider client={qc}>
        <CporPaymentEvidenceImportPage />
      </QueryClientProvider>,
    );
  }

  function mockApis(overlay: Record<string, unknown>) {
    apiGetMock.mockImplementation(async (path: string) => {
      if (path.includes('/payment-evidence/profiles')) {
        return {
          profiles: [{ id: 1, profile_code: 'asus', display_name: 'ASUS Pending', is_default: true }],
        };
      }
      if (path.includes('/imports/sources')) {
        return [{ id: 9, code: 'pay', name: 'pay' }];
      }
      if (path.includes('/payment-evidence/overlay')) {
        return overlay;
      }
      throw new Error(`unexpected ${path}`);
    });
  }

  it('selects the exact unmatched Case ID from the URL and does not mint', async () => {
    searchString = 'code=C19A50693';
    mockApis({
      focus_code: 'C19A50693',
      focus_match_count: 1,
      focus_minted: false,
      focus_rows: [
        {
          id: 88,
          external_case_code: 'C19A50693',
          case_id: null,
          payment_status: 'closed',
          amount: 1200,
          currency_code: 'USD',
          customer_token: 'HIST-CUST',
          minted: false,
        },
      ],
      unmatched_file_rows: [
        { id: 1, external_case_code: 'OTHERCODE', evidence_basis: 'source_attested' },
      ],
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('cpor-payment-code-match')).toHaveTextContent('C19A50693');
    });
    expect(screen.getByTestId('cpor-payment-code-focus')).toHaveTextContent(/does not mint/i);
    expect(screen.queryByText('OTHERCODE')).not.toBeInTheDocument();
    expect(apiGetMock.mock.calls.some((c) => String(c[0]).includes('code=C19A50693'))).toBe(true);
  });

  it('does not treat a prefix as the Case ID', async () => {
    searchString = 'code=C19A';
    mockApis({
      focus_code: 'C19A',
      focus_match_count: 0,
      focus_minted: false,
      focus_rows: [],
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('cpor-payment-code-focus')).toHaveTextContent(
        /No applied payment-evidence row/,
      );
    });
    expect(screen.queryByTestId('cpor-payment-code-match')).not.toBeInTheDocument();
    expect(screen.queryByText('C19A50693')).not.toBeInTheDocument();
  });
});
