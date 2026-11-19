import React from 'react';
import { fireEvent, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { PlannerTimeline } from './PlannerTimeline';

const rows = [
  { id: 1, case_code: 'CPR-1', customer_name: 'Alpha', status: 'approved', window_start: '2026-11-10', window_end: '2026-11-30' },
  { id: 2, case_code: 'CPR-2', customer_name: 'Beta', status: 'proposed', window_start: '2026-12-01', window_end: '2026-12-14' },
  { id: 3, case_code: 'CPR-3', customer_name: 'Gamma', status: 'draft', window_start: null, window_end: null },
];

describe('PlannerTimeline', () => {
  it('draws one bar per dated case and says how many are undated', () => {
    renderWithProviders(<PlannerTimeline cases={rows} today="2026-11-18" selectedId={null} onSelect={vi.fn()} />);
    expect(screen.getByTestId('planner-timeline')).toBeInTheDocument();
    expect(screen.getByTestId('planner-timeline-bar-1')).toBeInTheDocument();
    expect(screen.getByTestId('planner-timeline-bar-2')).toBeInTheDocument();
    expect(screen.queryByTestId('planner-timeline-bar-3')).toBeNull();
    expect(screen.getByTestId('planner-timeline-undated')).toHaveTextContent('1');
  });
  it('selects a case when its bar is clicked and marks the selected one', () => {
    const onSelect = vi.fn();
    renderWithProviders(<PlannerTimeline cases={rows} today="2026-11-18" selectedId={2} onSelect={onSelect} />);
    fireEvent.click(screen.getByTestId('planner-timeline-bar-1'));
    expect(onSelect).toHaveBeenCalledWith(1);
    expect(screen.getByTestId('planner-timeline-bar-2')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByTestId('planner-timeline-bar-1')).toHaveAttribute('aria-pressed', 'false');
  });
  it('shows a plain empty state without cases', () => {
    renderWithProviders(<PlannerTimeline cases={[]} today="2026-11-18" selectedId={null} onSelect={vi.fn()} />);
    expect(screen.getByTestId('planner-timeline-empty')).toBeInTheDocument();
  });
  it('shows an error, not "no dated cases", when the case list failed', () => {
    renderWithProviders(
      <PlannerTimeline cases={[]} today="2026-11-18" selectedId={null} onSelect={vi.fn()} status="error" />,
    );
    expect(screen.getByTestId('planner-timeline-error')).toBeInTheDocument();
    expect(screen.queryByTestId('planner-timeline-empty')).toBeNull();
  });
  it('shows loading, not an empty result, while the case list loads', () => {
    renderWithProviders(
      <PlannerTimeline cases={[]} today="2026-11-18" selectedId={null} onSelect={vi.fn()} status="loading" />,
    );
    expect(screen.getByTestId('planner-timeline-loading')).toBeInTheDocument();
    expect(screen.queryByTestId('planner-timeline-empty')).toBeNull();
  });
});
