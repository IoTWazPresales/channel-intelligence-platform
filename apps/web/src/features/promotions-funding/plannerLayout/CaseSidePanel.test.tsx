import React from 'react';
import { fireEvent, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { CaseSidePanel } from './CaseSidePanel';

const row = {
  id: 41,
  case_code: 'CPR-41',
  case_name: 'A plan',
  customer_name: 'Alpha',
  customer_code: 'ALP',
  promotion_type: 'Sell-Through PP',
  window_start: '2026-11-10',
  window_end: '2026-11-30',
  status: 'proposed',
  workflow_status: 'proposed',
  line_count: 4,
  estimate_qty_sum: 1820,
  ttl_support_zar: 1000,
  ttl_support_usd: null,
  currency_code: 'ZAR',
  flags: ['missing_cost'],
};

describe('CaseSidePanel', () => {
  it('asks for a selection when nothing is selected', () => {
    renderWithProviders(<CaseSidePanel row={null} onOpen={vi.fn()} onClear={vi.fn()} />);
    expect(screen.getByTestId('planner-side-panel-empty')).toBeInTheDocument();
  });
  it('summarises the case by name (no customer code) and opens the plan workspace', () => {
    const onOpen = vi.fn();
    renderWithProviders(<CaseSidePanel row={row} onOpen={onOpen} onClear={vi.fn()} />);
    const panel = screen.getByTestId('planner-side-panel');
    expect(panel).toHaveTextContent('CPR-41');
    expect(panel).toHaveTextContent('Alpha');
    expect(panel).not.toHaveTextContent('ALP');
    expect(panel).toHaveTextContent('2026-11-10');
    expect(panel).toHaveTextContent('missing_cost');
    fireEvent.click(screen.getByTestId('planner-side-open'));
    expect(onOpen).toHaveBeenCalledWith(41);
  });
  it('clears the selection', () => {
    const onClear = vi.fn();
    renderWithProviders(<CaseSidePanel row={row} onOpen={vi.fn()} onClear={onClear} />);
    fireEvent.click(screen.getByTestId('planner-side-clear'));
    expect(onClear).toHaveBeenCalled();
  });
  it('says the summary could not be loaded when a case is selected but its row is not available, and still offers the workspace', () => {
    const onOpen = vi.fn();
    renderWithProviders(<CaseSidePanel row={null} unavailableId={41} onOpen={onOpen} onClear={vi.fn()} />);
    expect(screen.queryByTestId('planner-side-panel-empty')).toBeNull();
    expect(screen.getByTestId('planner-side-panel-unavailable')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('planner-side-open'));
    expect(onOpen).toHaveBeenCalledWith(41);
  });
  describe('evidence and next actions (mock-up alignment)', () => {
    it('shows the evidence basis and the number of claim files applied when the row carries them', () => {
      renderWithProviders(
        <CaseSidePanel
          row={{
            ...row,
            status: 'ended',
            evidence_basis: 'claim_evidenced',
            settle_readiness: { fx_declared: true, roe_snapshot: 18, open_assumption_count: 0, claim_evidence_count: 2 },
          }}
          onOpen={vi.fn()}
          onClear={vi.fn()}
        />,
      );
      const evidence = screen.getByTestId('planner-side-evidence');
      expect(evidence).toHaveTextContent(/claim files applied2/i);
      expect(evidence).toHaveTextContent(/claim/i);
    });
    it('says no claim file is applied when the count is zero, and omits the line when the row has no readiness data', () => {
      const { unmount } = renderWithProviders(
        <CaseSidePanel
          row={{ ...row, settle_readiness: { fx_declared: true, roe_snapshot: 18, open_assumption_count: 0, claim_evidence_count: 0 } }}
          onOpen={vi.fn()}
          onClear={vi.fn()}
        />,
      );
      expect(screen.getByTestId('planner-side-evidence')).toHaveTextContent(/claim files applied0/i);
      unmount();
      renderWithProviders(<CaseSidePanel row={row} onOpen={vi.fn()} onClear={vi.fn()} />);
      expect(screen.queryByTestId('planner-side-evidence')).toBeNull();
    });
    it('lists what is waiting on this case from the action queue, and says so when nothing is', () => {
      const { unmount } = renderWithProviders(
        <CaseSidePanel
          row={row}
          actions={[
            { key: 'awaiting-41', kind: 'awaiting_approval', caseId: 41, caseCode: 'CPR-41', label: 'CPR-41 · awaiting approval · overdue', hint: 'The window started 2026-11-10: approve or reject it now.', tone: 'warning', overdue: true },
          ]}
          onOpen={vi.fn()}
          onClear={vi.fn()}
        />,
      );
      expect(screen.getByTestId('planner-side-next-actions')).toHaveTextContent('approve or reject it now');
      unmount();
      renderWithProviders(<CaseSidePanel row={row} actions={[]} onOpen={vi.fn()} onClear={vi.fn()} />);
      expect(screen.getByTestId('planner-side-next-actions')).toHaveTextContent(/nothing waiting on this case/i);
    });
    it('does not claim nothing is waiting when the queue is not known', () => {
      renderWithProviders(<CaseSidePanel row={row} onOpen={vi.fn()} onClear={vi.fn()} />);
      expect(screen.queryByTestId('planner-side-next-actions')).toBeNull();
    });
  });
});
