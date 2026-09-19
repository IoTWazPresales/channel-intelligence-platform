import { describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { SettlementDesk } from './SettlementDesk';
import type { SettlementDeskView } from './settlementDeskModel';

vi.mock('@/components/EnterpriseDataGrid', () => ({
  EnterpriseDataGrid: ({ rowData }: { rowData: { sku: string; corroborationReason: string; customerQty: number | null }[] }) => (
    <div data-testid="mock-grid">
      {rowData.map((r) => (
        <div key={r.sku}>
          <span>{r.sku}</span>
          <span>{r.corroborationReason}</span>
          <span>{r.customerQty == null ? '—' : r.customerQty}</span>
        </div>
      ))}
    </div>
  ),
}));

function view(over: Partial<SettlementDeskView> = {}): SettlementDeskView {
  return {
    caseId: 311,
    caseCode: 'C26760971',
    customerName: 'Takealot',
    customerCode: 'CUST-000012',
    programme: 'Pinnacle',
    windowLabel: '2026-07-30 → 2026-08-31',
    distributorName: 'Pinnacle',
    currency: 'ZAR',
    openedOn: '2026-07-01',
    endedOn: '2026-08-31',
    stage: 'customer_confirmed',
    status: 'settled',
    cipAmount: 1200,
    customerAmount: null,
    agreedAmount: null,
    hqCreditAmount: null,
    hqCreditLineCount: 0,
    matchedCount: 0,
    openCount: 2,
    claimRowCount: 0,
    paidInSchema: false,
    settledWithoutClaims: true,
    agreedActor: null,
    lines: [
      {
        id: '1',
        sku: '90NB0ZR2-M06MU0',
        salesModel: null,
        product: 'NB A',
        distributor: 'Pinnacle',
        estimateQty: 10,
        cipQty: 8,
        customerQty: null,
        supportUnit: 100,
        corroboration: 'pending',
        corroborationReason: 'Awaiting customer',
        includeInCredit: false,
      },
      {
        id: '2',
        sku: 'SKU-B',
        salesModel: null,
        product: 'NB B',
        distributor: 'Pinnacle',
        estimateQty: 4,
        cipQty: 4,
        customerQty: null,
        supportUnit: 50,
        corroboration: 'pending',
        corroborationReason: 'Awaiting customer',
        includeInCredit: false,
      },
    ],
    evidence: [],
    canSettle: false,
    fxSettleAllowed: true,
    fxDeclared: true,
    roeSnapshot: 18.78,
    allowedNext: [],
    ...over,
  };
}

describe('SettlementDesk', () => {
  it('shows customer name primary, not welded to the CIP-minted code', () => {
    renderWithProviders(<SettlementDesk view={view()} />);
    expect(screen.getByText(/C26760971 · Takealot/)).toBeInTheDocument();
    expect(screen.queryByText(/CUST-000012 — Takealot/)).not.toBeInTheDocument();
    expect(screen.getByText(/System-owned/)).toBeInTheDocument();
    expect(screen.getByText(/Customer-owned/)).toBeInTheDocument();
    expect(screen.getByText(/Not in schema today/)).toBeInTheDocument();
    expect(screen.getByText(/Matched · 0/)).toBeInTheDocument();
    expect(screen.getByText(/Open · 2/)).toBeInTheDocument();
    expect(
      screen.getByText('Matched lines can lock. Open lines stay on the grid until Ken or a PM agrees a qty.'),
    ).toBeInTheDocument();
    expect(screen.getByTestId('settlement-desk-settled-without-claims')).toBeInTheDocument();
    expect(screen.getAllByText('Awaiting customer').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Disabled until HQ credit exists — not a status today')).toBeInTheDocument();
    expect(screen.queryByTestId('settlement-desk-fx-blocked')).not.toBeInTheDocument();
    expect(screen.getByTestId('desk-cip-usd')).toHaveTextContent(/at booked 18\.78/);
    expect(screen.queryByTestId('settlement-desk-upload')).not.toBeInTheDocument();
    expect(screen.getByTestId('settlement-desk-primary')).toHaveTextContent('Upload customer report');
    expect(screen.getByTestId('settlement-desk-next-cta')).toHaveTextContent('Upload customer report');
  });

  it('renders an honest unbooked USD line instead of a live conversion', () => {
    renderWithProviders(
      <SettlementDesk
        view={view({
          fxDeclared: false,
          roeSnapshot: null,
          cipAmount: 1878,
        })}
      />,
    );
    expect(screen.getByTestId('desk-cip-usd')).toHaveTextContent('unbooked — no USD equivalent');
    expect(screen.getByTestId('desk-cip-usd')).not.toHaveTextContent('$');
  });

  it('surfaces FX blocked with the existing Alert primitive', () => {
    renderWithProviders(
      <SettlementDesk
        view={view({
          fxSettleAllowed: false,
          settledWithoutClaims: false,
          status: 'ended',
          fxBasisLine: 'FX rate 18.78 · mode not declared',
        })}
      />,
    );
    expect(screen.getByTestId('settlement-desk-fx-blocked')).toHaveTextContent(
      'FX rate 18.78 · mode not declared',
    );
  });
});
