import { describe, expect, it, vi } from 'vitest';
import { fireEvent, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactElement } from 'react';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { SettlementCaseTabs } from './SettlementCaseTabs';

vi.mock('@/lib/api', () => ({
  apiGet: (url: string) => {
    if (url.includes('/pivot')) {
      return Promise.resolve({ cells: {}, row_totals: {}, col_totals: {}, grand_total_usd: 0, missing_roe: false });
    }
    if (url.includes('/events')) {
      return Promise.resolve([{ id: 1, event_type: 'approve', actor: 'ken', created_at: '2026-09-01T10:00:00Z' }]);
    }
    if (url.includes('/exports')) return Promise.resolve({ exports: [] });
    if (url.includes('/promo-load-recon')) {
      return Promise.resolve({ data_unavailable: true, reason: 'no_cst', import_steward_hint: 'CST import steward' });
    }
    if (url.includes('/payment-evidence')) return Promise.resolve({ items: [], total: 0 });
    if (url.includes('/payment-recon')) {
      return Promise.resolve({
        case_id: 46, case_code: 'C1', currency_code: 'ZAR', owed_amount: null, paid_amount: null, outstanding_amount: null,
        owed_amount_file: null, paid_other_currency_amount: null, paid_other_currencies: [], last_payment_date: null,
        credit_note_ids: [], recon_status: 'open', flags: [], explanations: [], paid_row_count: 0, pending_row_count: 0,
        payment_evidence_count: 0,
      });
    }
    if (url.includes('/auth/tenant-commercial-profile')) return Promise.resolve({ line_identifier_preference: 'sku' });
    return Promise.resolve({});
  },
  apiPost: vi.fn(),
}));

vi.mock('@/components/EnterpriseDataGrid', () => ({
  EnterpriseDataGrid: () => <div data-testid="mock-grid" />,
}));

function renderTabs(ui: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderWithProviders(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe('SettlementCaseTabs', () => {
  it('exposes the five orphaned case tabs and mounts only the active one', async () => {
    renderTabs(<SettlementCaseTabs caseId={46} roeSnapshot={16.5} />);
    for (const key of ['pivot', 'events', 'exports', 'promo-load', 'payments']) {
      expect(screen.getByTestId(`settlement-tab-${key}`)).toBeInTheDocument();
    }
    expect(await screen.findByText('No USD pivot yet')).toBeInTheDocument();
    expect(screen.queryByTestId('cpor-events')).toBeNull();
  });

  it('names the panel by its active tab and links every tab to the panel', () => {
    renderTabs(<SettlementCaseTabs caseId={46} />);
    const panel = screen.getByRole('tabpanel', { name: 'USD pivot' });
    for (const tab of screen.getAllByRole('tab')) {
      expect(tab).toHaveAttribute('aria-controls', panel.id);
    }
    fireEvent.click(screen.getByTestId('settlement-tab-events'));
    expect(screen.getByRole('tabpanel', { name: 'Events' })).toBe(panel);
  });

  it('switches to Events and renders the API rows through the panel', async () => {
    renderTabs(<SettlementCaseTabs caseId={46} />);
    fireEvent.click(screen.getByTestId('settlement-tab-events'));
    expect(await screen.findByTestId('cpor-events')).toBeInTheDocument();
    expect(screen.getByText('approve')).toBeInTheDocument();
    expect(screen.getByText(/ken/)).toBeInTheDocument();
  });

  it('mounts the existing promo-load and payment panels unchanged', async () => {
    renderTabs(<SettlementCaseTabs caseId={46} defaultTab="promo-load" />);
    expect(await screen.findByTestId('cpor-promo-load-no-cst')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('settlement-tab-payments'));
    expect(await screen.findByTestId('cpor-payment-evidence-panel')).toBeInTheDocument();
  });
});
