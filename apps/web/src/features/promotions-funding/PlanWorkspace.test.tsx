import React from 'react';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { PlanWorkspace } from './PlanWorkspace';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/promotions',
}));

vi.mock('@/components/EnterpriseDataGrid', () => ({
  EnterpriseDataGrid: () => <div data-testid="mock-grid" />,
}));

vi.mock('@/features/commercial-planner/EntitySearchAutocomplete', () => ({
  EntitySearchAutocomplete: () => null,
}));

vi.mock('@/app/(app)/commercial-planner/cpor-cases/[id]/CporComparableCasesPanel', () => ({
  CporComparableCasesPanel: () => null,
}));

const baseCase = {
  id: 77,
  case_code: 'C26P00077',
  case_name: null,
  customer_name: 'Takealot',
  customer_code: 'CUST-000012',
  promotion_type: 'Sell out PP',
  window_start: '2026-10-01',
  window_end: '2026-10-31',
  status: 'proposed',
  workflow_status: 'pending_approval',
  currency_code: 'ZAR',
  roe_snapshot: null,
  fx_mode: 'booked',
  fx_proposed_rate: 18.42,
  missing_roe: true,
  allowed_next: ['approved', 'rejected', 'cancelled'],
  lines: [],
  flags: [],
  ttl_support_zar: 0,
  ttl_support_usd: null,
  needs_reapproval: true,
};

let detail: Record<string, unknown> = baseCase;

vi.mock('@/lib/api', () => ({
  apiGet: vi.fn(async (url: string) => {
    if (url === '/api/v1/cpor/cases/77') return detail;
    return {};
  }),
  apiPost: vi.fn(async () => ({})),
  apiPatch: vi.fn(async () => ({})),
  apiDownloadBlob: vi.fn(),
}));

function renderWorkspace() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderWithProviders(
    <QueryClientProvider client={qc}>
      <PlanWorkspace caseId={77} onBack={() => undefined} />
    </QueryClientProvider>,
  );
}

describe('PlanWorkspace approve / FX (N-0044, ported from CporCaseWorkspace)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    detail = baseCase;
  });

  it('approves through the book-FX dialog carrying fx_rate and the over-budget reapproval', async () => {
    const { apiPost } = await import('@/lib/api');
    renderWorkspace();
    expect(await screen.findByTestId('plan-needs-reapproval')).toBeInTheDocument();
    const approve = screen.getByTestId('plan-approve');
    expect(approve).toHaveTextContent('Reapprove (over budget)');
    fireEvent.click(approve);
    expect(vi.mocked(apiPost)).not.toHaveBeenCalled();

    const rate = screen.getByTestId('plan-approve-fx-rate') as HTMLInputElement;
    expect(rate.value).toBe('18.42');
    fireEvent.change(rate, { target: { value: '18.9' } });
    fireEvent.click(screen.getByTestId('plan-approve-confirm'));
    await waitFor(() =>
      expect(vi.mocked(apiPost)).toHaveBeenCalledWith('/api/v1/cpor/cases/77/transition', {
        action: 'approve',
        confirm_over_budget_reapproval: true,
        fx_rate: 18.9,
      }),
    );
  });

  it('sends confirm_over_budget_reapproval false when the case is within budget', async () => {
    detail = { ...baseCase, needs_reapproval: false };
    const { apiPost } = await import('@/lib/api');
    renderWorkspace();
    fireEvent.click(await screen.findByTestId('plan-approve'));
    fireEvent.click(screen.getByTestId('plan-approve-confirm'));
    await waitFor(() =>
      expect(vi.mocked(apiPost)).toHaveBeenCalledWith('/api/v1/cpor/cases/77/transition', {
        action: 'approve',
        confirm_over_budget_reapproval: false,
        fx_rate: 18.42,
      }),
    );
  });

  it('edits FX mode and the proposed rate on a draft through the existing PATCH', async () => {
    detail = { ...baseCase, status: 'draft', allowed_next: ['proposed', 'cancelled'], needs_reapproval: false };
    const { apiPatch } = await import('@/lib/api');
    renderWorkspace();
    fireEvent.click(await screen.findByTestId('plan-fx-mode-floating'));
    await waitFor(() =>
      expect(vi.mocked(apiPatch)).toHaveBeenCalledWith('/api/v1/cpor/cases/77', { fx_mode: 'floating' }),
    );
    fireEvent.change(screen.getByTestId('plan-fx-proposed-edit'), { target: { value: '19.05' } });
    fireEvent.click(screen.getByTestId('plan-fx-proposed-save'));
    await waitFor(() =>
      expect(vi.mocked(apiPatch)).toHaveBeenCalledWith('/api/v1/cpor/cases/77', { fx_proposed_rate: 19.05 }),
    );
  });

  it('locks FX edits outside draft/rejected', async () => {
    renderWorkspace();
    expect(await screen.findByTestId('plan-fx-mode-floating')).toBeDisabled();
    expect(screen.queryByTestId('plan-fx-proposed-edit')).toBeNull();
  });

  it('routes settle to the desk instead of posting it from the planner', async () => {
    detail = { ...baseCase, status: 'ended', allowed_next: ['settled', 'cancelled'], needs_reapproval: false };
    renderWorkspace();
    const desk = await screen.findByTestId('plan-open-desk');
    expect(desk).toHaveTextContent('Settle on the desk');
    expect(desk).toHaveAttribute('href', '/commercial-planner/cpor-cases/77');
    expect(screen.queryByTestId('plan-settle')).toBeNull();
  });

  it('shows the PM comment on a rejected plan (was a workspace header chip)', async () => {
    detail = {
      ...baseCase,
      status: 'rejected',
      allowed_next: ['proposed', 'cancelled'],
      needs_reapproval: false,
      last_comment: 'Support too high for Q4',
    };
    renderWorkspace();
    expect(await screen.findByTestId('plan-last-comment')).toHaveTextContent('PM comment: Support too high for Q4');
  });
});
