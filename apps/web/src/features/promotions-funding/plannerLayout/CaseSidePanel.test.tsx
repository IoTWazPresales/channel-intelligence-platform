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
});
