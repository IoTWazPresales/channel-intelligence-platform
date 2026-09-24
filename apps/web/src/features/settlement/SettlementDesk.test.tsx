import { describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactElement } from 'react';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { SettlementDesk } from './SettlementDesk';
import type { SettlementDeskView } from './settlementDeskModel';

vi.mock('@/lib/api', () => ({
  apiGet: (url: string) => {
    if (url.includes('/auth/tenant-commercial-profile')) {
      return Promise.resolve({ line_identifier_preference: 'sku' });
    }
    return Promise.resolve({});
  },
  apiPost: vi.fn(),
}));

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

/** SettlementDesk reads the tenant line-identifier preference via useQuery. */
function renderDesk(ui: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderWithProviders(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe('SettlementDesk', () => {
  it('shows customer name primary, not welded to the CIP-minted code', () => {
    renderDesk(<SettlementDesk view={view()} />);
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
    expect(screen.getAllByRole('button', { name: 'Upload customer report' })).toHaveLength(1);
    expect(screen.queryByTestId('settlement-desk-next-cta')).not.toBeInTheDocument();
    expect(screen.getByText(/One CTA for the current stage/)).toHaveTextContent(/header/);
  });

  it('renders an honest unbooked USD line instead of a live conversion', () => {
    renderDesk(
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
    renderDesk(
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

  it('offers end / cancel only from allowedNext and hands the choice to the caller (N-0044)', () => {
    const onLifecycleAction = vi.fn();
    const { unmount } = renderDesk(
      <SettlementDesk
        view={view({ status: 'active', allowedNext: ['ended', 'cancelled'] })}
        onLifecycleAction={onLifecycleAction}
      />,
    );
    screen.getByTestId('settlement-desk-action-end').click();
    expect(onLifecycleAction).toHaveBeenCalledWith('end');
    expect(screen.getByTestId('settlement-desk-action-cancel')).toBeInTheDocument();
    unmount();

    renderDesk(<SettlementDesk view={view({ allowedNext: [] })} onLifecycleAction={onLifecycleAction} />);
    expect(screen.queryByTestId('settlement-desk-action-end')).toBeNull();
    expect(screen.queryByTestId('settlement-desk-action-cancel')).toBeNull();
  });

  it('shows the reapproval warning and links pre-approval work to the planner', () => {
    renderDesk(
      <SettlementDesk
        view={view({ status: 'proposed', allowedNext: ['approved', 'rejected', 'cancelled'], needsReapproval: true })}
        plannerHref="/promotions?plan=311"
      />,
    );
    expect(screen.getByTestId('settlement-desk-needs-reapproval')).toHaveTextContent(/Needs reapproval \(over budget\)/);
    expect(screen.getByTestId('settlement-desk-open-planner')).toHaveAttribute('href', '/promotions?plan=311');
  });

  it('puts approved support first in the headline strip via DualMoney', () => {
    renderDesk(
      <SettlementDesk
        view={view({ approvedAmount: 1878, approvedUsd: 100, fxMode: 'booked', fxBookedBy: 'ken' })}
      />,
    );
    expect(screen.getByTestId('desk-approved-usd')).toHaveTextContent(/\$ 100[.,]00/);
    expect(screen.getByText('Booked 18.78 · booked · by ken')).toBeInTheDocument();
    expect(screen.queryByTestId('settlement-desk-open-planner')).toBeNull();
  });
});
