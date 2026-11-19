import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { CustomerTimelineSurface, TimelineRows } from './CustomerTimelineSurface';
import type { Timeline } from './types';

const mocks = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('@/lib/api', () => ({ apiGet: mocks.get }));
vi.mock('@/features/shell/useCurrentUser', () => ({ useCurrentUser: () => ({ data: { role: 'viewer' } }) }));
vi.mock('./CalendarUploadPanel', () => ({ CalendarUploadPanel: () => <div>Calendar uploader</div> }));
vi.mock('@/features/commercial-planner/EntitySearchAutocomplete', () => ({
  EntitySearchAutocomplete: ({ onChange }: { onChange: (v: unknown) => void }) => (
    <button onClick={() => onChange({ id: 17, customer_name: 'Selected account', customer_code: 'A' })}>Pick customer</button>
  ),
}));

const timeline: Timeline = {
  customer: { id: 17, name: 'Selected account' }, from: null, to: null,
  promotions: [{ case_id: 1, case_code: 'CASE-A', case_name: 'Our campaign', promotion_type: 'Promotion',
    status: 'active', customer_id: 17, window_start: '2026-03-01', window_end: '2026-03-15' }],
  calendar_events: [{ id: 2, customer_id: 17, name: 'Customer pillar', kind: 'pillar',
    start_date: '2026-03-10', end_date: '2026-03-31', source_file: 'calendar.csv', upload_id: 'calendar' }],
  clashes: [{ case_id: 1, case_code: 'CASE-A', case_name: 'Our campaign', event_id: 2,
    event_name: 'Customer pillar', event_kind: 'pillar', overlap_start: '2026-03-10', overlap_end: '2026-03-15', overlap_days: 6 }],
};

beforeEach(() => vi.clearAllMocks());

it('renders both sources on one axis and highlights the clash with dates and days', () => {
  render(<TimelineRows timeline={timeline} />);
  expect(screen.getByText('Our promotions')).toBeInTheDocument();
  expect(screen.getByText('Customer calendar')).toBeInTheDocument();
  expect(screen.getByTestId('promotion-1')).toHaveAttribute('data-clash', 'true');
  expect(screen.getByTestId('event-2')).toHaveAttribute('data-clash', 'true');
  expect(screen.getByText(/6 days/)).toBeInTheDocument();
  expect(screen.getAllByText(/2026-03-10/).length).toBeGreaterThan(0);
});

it('asks for a customer before fetching and uses that customer in the timeline request', async () => {
  mocks.get.mockResolvedValue(timeline);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><CustomerTimelineSurface /></QueryClientProvider>);
  expect(screen.getByText(/Choose a customer/)).toBeInTheDocument();
  expect(mocks.get).not.toHaveBeenCalled();
  fireEvent.click(screen.getByText('Pick customer'));
  await screen.findByText('Our promotions');
  expect(mocks.get.mock.calls[0][0]).toContain('customer_id=17');
  expect(screen.queryByText('Calendar uploader')).not.toBeInTheDocument();
});

it('shows an unavailable notice instead of a misleading empty calendar', () => {
  render(<TimelineRows timeline={{ ...timeline, data_unavailable: true, message: 'Calendar migration pending' }} />);
  expect(screen.getByText('Calendar migration pending')).toBeInTheDocument();
});
