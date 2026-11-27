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

  it('opens on Week, with a month row and ISO week labels, over the three-month block', () => {
    // Requirement: docs/design/planner/Promotion_Planner Mockup.png shows Week selected, a month row
    // ("Nov 2026") and week labels ("W47 / Nov 16"), plus the navigator "Nov – Jan 2027".
    renderWithProviders(
      <CustomerRowsTimeline
        cases={[row(1, 'Alpha', 'active', '2026-11-02', '2026-11-20')]}
        today="2026-11-19"
        selectedId={null}
        onSelect={vi.fn()}
      />,
    );
    const tl = screen.getByTestId('planner-timeline');
    expect(within(tl).getByText('Nov 2026')).toBeInTheDocument();
    expect(within(tl).getByText('W45 / 2 Nov')).toBeInTheDocument();
    expect(screen.getByTestId('planner-period-label')).toHaveTextContent('Nov – Jan 2027');
    expect(screen.getByTestId('planner-period-label')).not.toHaveTextContent('Q');
  });

  it('appends the tenant gregorian quarter when the block is one quarter', () => {
    renderWithProviders(
      <CustomerRowsTimeline
        cases={[row(1, 'Alpha', 'active', '2026-11-02', '2026-11-20')]}
        today="2026-11-19"
        selectedId={null}
        onSelect={vi.fn()}
        fiscalYearStartMonth={2}
      />,
    );
    expect(screen.getByTestId('planner-period-label')).toHaveTextContent('Nov – Jan 2027 (Q4)');
  });

  it('moves the visible block with the period arrows and hides a promotion outside it', () => {
    renderWithProviders(
      <CustomerRowsTimeline
        cases={[row(1, 'Alpha', 'ended', '2026-10-01', '2026-10-10')]}
        today="2026-11-19"
        selectedId={null}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.queryByTestId('planner-timeline-bar-1')).toBeNull();
    fireEvent.click(screen.getByTestId('planner-period-prev'));
    expect(screen.getByTestId('planner-period-label')).toHaveTextContent('Aug – Oct 2026');
    expect(screen.getByTestId('planner-timeline-bar-1')).toBeInTheDocument();
  });

  it('shows the list instead of the bars when List is selected', () => {
    // Requirement: the mock-up's Timeline | List switch. Timeline is selected; the list is the other view.
    renderWithProviders(
      <CustomerRowsTimeline
        cases={[row(1, 'Alpha', 'active', '2026-11-02', '2026-11-20')]}
        today="2026-11-19"
        selectedId={null}
        onSelect={vi.fn()}
        list={<div data-testid="planner-list-slot">the list</div>}
      />,
    );
    expect(screen.getByTestId('planner-timeline-bar-1')).toBeInTheDocument();
    expect(screen.queryByTestId('planner-list-slot')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'List' }));
    expect(screen.getByTestId('planner-list-slot')).toBeInTheDocument();
    expect(screen.queryByTestId('planner-timeline-bar-1')).toBeNull();
    expect(screen.queryByTestId('planner-period-nav')).toBeNull();
  });
});
