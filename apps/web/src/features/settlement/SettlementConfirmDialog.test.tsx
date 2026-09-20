import { describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { SettlementConfirmDialog } from './SettlementConfirmDialog';

const base = {
  open: true,
  onClose: vi.fn(),
  onConfirm: vi.fn(),
  caseCode: 'C26760971',
  customerLabel: 'Takealot',
  outstandingAmount: 1878,
  currencyCode: 'ZAR',
  claimRowCount: 1,
};

describe('SettlementConfirmDialog', () => {
  it('shows the outstanding amount as ZAR with booked USD alongside', () => {
    renderWithProviders(
      <SettlementConfirmDialog
        {...base}
        settleReadiness={{
          fx_declared: true,
          roe_snapshot: 18.78,
          fx_mode: 'fixed',
          fx_mode_declared: true,
          fx_settle_allowed: true,
          open_assumption_count: 0,
          claim_evidence_count: 1,
        }}
      />,
    );
    // Intl output is machine-locale dependent (`1,878.00` vs `1 878,00`) — match shape, not separators.
    expect(screen.getByTestId('settlement-confirm-amount')).toHaveTextContent(/R\s1[\s,.]?878[.,]00/);
    expect(screen.getByTestId('settlement-confirm-amount-dual-usd')).toHaveTextContent(
      /\$\s100[.,]00 at booked 18\.78/,
    );
    expect(screen.getByTestId('settlement-confirm-submit')).toBeEnabled();
  });

  it('renders an honest unbooked USD line and blocks settlement when FX is not ready', () => {
    renderWithProviders(
      <SettlementConfirmDialog
        {...base}
        settleReadiness={{
          fx_declared: false,
          roe_snapshot: null,
          fx_settle_allowed: false,
          open_assumption_count: 0,
          claim_evidence_count: 1,
        }}
      />,
    );
    expect(screen.getByTestId('settlement-confirm-amount-dual-usd')).toHaveTextContent(
      'unbooked — no USD equivalent',
    );
    expect(screen.getByTestId('settlement-confirm-amount-dual-usd')).not.toHaveTextContent('$');
    expect(screen.getByTestId('settlement-confirm-fx-blocked')).toBeInTheDocument();
    expect(screen.getByTestId('settlement-confirm-submit')).toBeDisabled();
  });

  it('falls back to the local amount when readiness has not loaded', () => {
    renderWithProviders(<SettlementConfirmDialog {...base} />);
    expect(screen.getByTestId('settlement-confirm-amount')).toHaveTextContent(/R\s1[\s,.]?878[.,]00/);
    expect(screen.queryByTestId('settlement-confirm-amount-dual-usd')).not.toBeInTheDocument();
  });
});
