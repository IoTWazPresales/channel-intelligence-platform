import React from 'react';
import { fireEvent, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { CustomerRowsTimeline } from './CustomerRowsTimeline';

// Step 2 (N-0122): the promotion timeline per docs/design/planner/Promotion_Planner Mockup.png.
const row = (id: number, customer: string, status: string, s: string, e: string) => ({
  id,
  case_code: `CPR-${id}`,
  case_name: `Promo ${id}`,
  customer_name: customer,
  status,
  window_start: s,
  window_end: e,
});

describe('CustomerRowsTimeline (mock-up layout)', () => {
  it('names the panel "Promotion timeline", heads the customer column and counts each customer\'s promotions', () => {
    renderWithProviders(
      <CustomerRowsTimeline
        cases={[
          row(1, 'Alpha', 'active', '2026-11-02', '2026-11-20'),
          row(2, 'Alpha', 'approved', '2026-12-01', '2026-12-15'),
          row(3, 'Beta', 'active', '2026-11-10', '2026-11-30'),
        ]}
        today="2026-11-19"
        selectedId={null}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByText('Promotion timeline')).toBeInTheDocument();
    expect(screen.getByTestId('planner-timeline-customer-head')).toHaveTextContent('Customer');
    expect(within(screen.getByTestId('planner-timeline-row-alpha')).getByText('2 promotions')).toBeInTheDocument();
    expect(within(screen.getByTestId('planner-timeline-row-beta')).getByText('1 promotion')).toBeInTheDocument();
  });

  it('legend shows the four mock-up statuses with their counts, named even when no bar has that status', () => {
    renderWithProviders(
      <CustomerRowsTimeline
        cases={[row(1, 'Alpha', 'active', '2026-11-02', '2026-11-20'), row(2, 'Beta', 'active', '2026-11-05', '2026-11-25')]}
        today="2026-11-19"
        selectedId={null}
        onSelect={vi.fn()}
      />,
    );
    const legend = screen.getByTestId('planner-timeline-legend');
    for (const l of ['Live', 'Approved', 'Planned', 'Ended']) expect(within(legend).getByText(l)).toBeInTheDocument();
    expect(screen.getByTestId('planner-legend-count-live')).toHaveTextContent('(2)');
    expect(screen.getByTestId('planner-legend-count-planned')).toHaveTextContent('(0)');
  });

  it('shows the caller\'s empty state when no dated promotion loaded', () => {
    renderWithProviders(
      <CustomerRowsTimeline
        cases={[]}
        today="2026-11-19"
        selectedId={null}
        onSelect={vi.fn()}
        emptyState={<span>No open customer promotions.</span>}
      />,
    );
    expect(screen.getByTestId('planner-timeline-empty')).toHaveTextContent('No open customer promotions.');
  });

  it('labels the week view with ISO weeks above the Monday dates', () => {
    renderWithProviders(
      <CustomerRowsTimeline
        cases={[row(1, 'Alpha', 'active', '2026-11-02', '2026-11-20')]}
        today="2026-11-19"
        selectedId={null}
        onSelect={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Week' }));
    const tl = screen.getByTestId('planner-timeline');
    expect(within(tl).getByText('W45')).toBeInTheDocument();
    expect(within(tl).getByText('2 Nov')).toBeInTheDocument();
  });
});
