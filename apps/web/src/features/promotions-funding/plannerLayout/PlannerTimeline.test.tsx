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
  it('has a Month / Week switch: month ticks by default, Monday ticks in the week view', () => {
    renderWithProviders(<PlannerTimeline cases={rows} today="2026-11-18" selectedId={null} onSelect={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'Month' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'Week' })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByText('Nov 2026')).toBeInTheDocument();
    expect(screen.queryByText('9 Nov')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Week' }));
    expect(screen.getByRole('button', { name: 'Week' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText('9 Nov')).toBeInTheDocument();
    expect(screen.getByText('16 Nov')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Month' }));
    expect(screen.queryByText('9 Nov')).toBeNull();
  });
  it('colours bars by lane and shows a legend of the lanes in view', () => {
    const lanes = [
      { id: 1, case_code: 'L', customer_name: 'A', status: 'active', window_start: '2026-11-01', window_end: '2026-11-20' },
      { id: 2, case_code: 'AP', customer_name: 'B', status: 'approved', window_start: '2026-11-05', window_end: '2026-11-25' },
      { id: 3, case_code: 'PL', customer_name: 'C', status: 'proposed', window_start: '2026-12-01', window_end: '2026-12-10' },
      { id: 4, case_code: 'EN', customer_name: 'D', status: 'settled', window_start: '2026-10-01', window_end: '2026-10-20' },
    ];
    renderWithProviders(<PlannerTimeline cases={lanes} today="2026-11-18" selectedId={null} onSelect={vi.fn()} />);
    const legend = screen.getByTestId('planner-timeline-legend');
    for (const name of ['Live', 'Approved', 'Planned', 'Ended']) expect(legend).toHaveTextContent(name);
    expect(legend).not.toHaveTextContent('Cancelled');
    expect(screen.getByTestId('planner-timeline-bar-1')).toHaveAttribute('data-lane', 'live');
    expect(screen.getByTestId('planner-timeline-bar-2')).toHaveAttribute('data-lane', 'approved');
    expect(screen.getByTestId('planner-timeline-bar-3')).toHaveAttribute('data-lane', 'planned');
    expect(screen.getByTestId('planner-timeline-bar-4')).toHaveAttribute('data-lane', 'ended');
    // each lane has its own colour
    const colours = [1, 2, 3, 4].map((id) => getComputedStyle(screen.getByTestId(`planner-timeline-bar-${id}`)).borderColor);
    expect(new Set(colours).size).toBe(4);
  });
  it('lists a cancelled case under its own legend entry only when one is drawn', () => {
    const withCancelled = [{ id: 9, case_code: 'X', customer_name: 'A', status: 'cancelled', window_start: '2026-11-01', window_end: '2026-11-20' }];
    renderWithProviders(<PlannerTimeline cases={withCancelled} today="2026-11-18" selectedId={null} onSelect={vi.fn()} />);
    expect(screen.getByTestId('planner-timeline-legend')).toHaveTextContent('Cancelled');
  });
  it('groups the rows by customer and writes each customer name once', () => {
    const grouped = [
      { id: 1, case_code: 'A-1', customer_name: 'Alpha', status: 'approved', window_start: '2026-11-10', window_end: '2026-11-30' },
      { id: 2, case_code: 'B-1', customer_name: 'Beta', status: 'approved', window_start: '2026-11-11', window_end: '2026-11-30' },
      { id: 3, case_code: 'A-2', customer_name: 'Alpha', status: 'proposed', window_start: '2026-12-01', window_end: '2026-12-14' },
    ];
    renderWithProviders(<PlannerTimeline cases={grouped} today="2026-11-18" selectedId={null} onSelect={vi.fn()} />);
    expect(screen.getAllByText('Alpha')).toHaveLength(1);
    expect(screen.getAllByText('Beta')).toHaveLength(1);
    const order = screen.getAllByTestId(/^planner-timeline-bar-/).map((el) => el.getAttribute('data-testid'));
    expect(order).toEqual(['planner-timeline-bar-1', 'planner-timeline-bar-3', 'planner-timeline-bar-2']);
    // the second Alpha row still says which case it is
    expect(screen.getByText('A-2')).toBeInTheDocument();
  });
});
