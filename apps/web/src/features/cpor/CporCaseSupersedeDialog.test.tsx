import React from 'react';
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { CporCaseSupersedeDialog } from './CporCaseSupersedeDialog';

const apiGetMock = vi.fn();
const apiPostMock = vi.fn();

vi.mock('@/lib/api', () => ({
  apiGet: (...args: unknown[]) => apiGetMock(...args),
  apiPost: (...args: unknown[]) => apiPostMock(...args),
}));

const candidates = [
  { id: 311, case_code: 'C26C00311', case_name: null, status: 'settled', window_start: null, window_end: null },
  { id: 312, case_code: 'C26C00312', case_name: 'Re-issue', status: 'approved', window_start: '2026-04-01', window_end: '2026-06-30' },
  { id: 313, case_code: 'C26C00313', case_name: null, status: 'cancelled', window_start: null, window_end: null },
  { id: 314, case_code: 'C26C00314', case_name: null, status: 'draft', window_start: null, window_end: null, superseded_by_case_id: 312 },
];

function renderDialog(onSuperseded = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return renderWithProviders(
    <QueryClientProvider client={qc}>
      <CporCaseSupersedeDialog
        open
        onClose={vi.fn()}
        caseId={311}
        caseCode="C26C00311"
        customerId={7}
        onSuperseded={onSuperseded}
      />
    </QueryClientProvider>
  );
}

describe('CporCaseSupersedeDialog (BACKLOG-138)', () => {
  beforeEach(() => {
    apiGetMock.mockReset();
    apiPostMock.mockReset();
    apiGetMock.mockResolvedValue(candidates);
  });

  it('lists only live, un-superseded other cases for the customer', async () => {
    renderDialog();
    await waitFor(() => expect(apiGetMock).toHaveBeenCalledWith('/api/v1/cpor/cases?customer_id=7&test_data=all'));
    const input = screen.getByTestId('cpor-supersede-winner-input');
    fireEvent.mouseDown(input);
    fireEvent.change(input, { target: { value: 'C26C' } });
    const listbox = await screen.findByRole('listbox');
    const optionText = within(listbox)
      .getAllByRole('option')
      .map((o) => o.textContent ?? '');
    expect(optionText.some((t) => t.includes('C26C00312'))).toBe(true);
    expect(optionText.some((t) => t.includes('C26C00311'))).toBe(false); // self
    expect(optionText.some((t) => t.includes('C26C00313'))).toBe(false); // cancelled
    expect(optionText.some((t) => t.includes('C26C00314'))).toBe(false); // already superseded
    expect(screen.getByTestId('cpor-supersede-confirm')).toBeDisabled();
  });

  it('previews on pick, blocks confirm on blockers, confirms when clean', async () => {
    apiPostMock.mockImplementation(async (path: string, body: { winner_case_id?: number }) => {
      if (path.endsWith('/supersede/preview')) {
        return {
          loser: { id: 311, case_code: 'C26C00311', status: 'approved', line_count: 18 },
          winner: { id: body.winner_case_id, case_code: 'C26C00312', status: 'approved', line_count: 4 },
          already_superseded: false,
          blockers: [],
          warnings: [{ code: 'loser_live', message: 'Case is approved.' }],
          effects: [],
        };
      }
      if (path.endsWith('/supersede')) return { id: 311, superseded_by_case_id: 312 };
      throw new Error(`unexpected ${path}`);
    });
    const onSuperseded = vi.fn();
    renderDialog(onSuperseded);
    const input = screen.getByTestId('cpor-supersede-winner-input');
    fireEvent.mouseDown(input);
    fireEvent.change(input, { target: { value: 'C26C00312' } });
    fireEvent.click(await screen.findByText(/C26C00312/));

    await waitFor(() => expect(screen.getByTestId('cpor-supersede-preview')).toBeInTheDocument());
    expect(screen.getByTestId('cpor-supersede-warning-loser_live')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId('cpor-supersede-confirm')).toBeEnabled());

    fireEvent.change(screen.getByTestId('cpor-supersede-reason'), { target: { value: 'Re-issued Q2' } });
    fireEvent.click(screen.getByTestId('cpor-supersede-confirm'));
    await waitFor(() =>
      expect(apiPostMock).toHaveBeenCalledWith('/api/v1/cpor/cases/311/supersede', {
        winner_case_id: 312,
        confirm: true,
        reason: 'Re-issued Q2',
      })
    );
    await waitFor(() => expect(onSuperseded).toHaveBeenCalled());
  });

  it('keeps confirm disabled when the preview returns a blocker', async () => {
    apiPostMock.mockResolvedValue({
      loser: { id: 311, case_code: 'C26C00311', status: 'settled', line_count: 18 },
      winner: { id: 312, case_code: 'C26C00312', status: 'approved', line_count: 4 },
      already_superseded: false,
      blockers: [{ code: 'loser_settled', message: 'Case is settled.' }],
      warnings: [],
      effects: [],
    });
    renderDialog();
    const input = screen.getByTestId('cpor-supersede-winner-input');
    fireEvent.mouseDown(input);
    fireEvent.change(input, { target: { value: 'C26C00312' } });
    fireEvent.click(await screen.findByText(/C26C00312/));
    await waitFor(() => expect(screen.getByTestId('cpor-supersede-blocker-loser_settled')).toBeInTheDocument());
    expect(screen.getByTestId('cpor-supersede-confirm')).toBeDisabled();
  });
});
