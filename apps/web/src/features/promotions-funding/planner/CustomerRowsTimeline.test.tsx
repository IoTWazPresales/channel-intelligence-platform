import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { CustomerRowsTimeline } from './CustomerRowsTimeline';

vi.mock('@mui/material/styles', async () => {
  const actual = await vi.importActual<typeof import('@mui/material/styles')>('@mui/material/styles');
  return {
    ...actual,
    useTheme: () => ({
      palette: {
        success: { main: '#0a0' },
        primary: { main: '#00f' },
        warning: { main: '#f90' },
        error: { main: '#f00' },
        text: { secondary: '#666', disabled: '#999' },
        divider: '#ddd',
      },
    }),
  };
});

describe('CustomerRowsTimeline', () => {
  it('renders reporting subtitle and thinned month axis', () => {
    render(
      <CustomerRowsTimeline
        today="2026-06-15"
        selectedId={null}
        onSelect={() => {}}
        cases={[
          {
            id: 1,
            case_code: 'C-1',
            case_name: 'Promo',
            customer_name: 'Acme',
            status: 'active',
            window_start: '2026-05-01',
            window_end: '2026-05-31',
          },
        ]}
      />,
    );
    expect(screen.getByText(/Reporting customers/i)).toBeInTheDocument();
    expect(screen.getByTestId('planner-timeline-bar-1')).toHaveAttribute('data-lane', 'live');
  });
});