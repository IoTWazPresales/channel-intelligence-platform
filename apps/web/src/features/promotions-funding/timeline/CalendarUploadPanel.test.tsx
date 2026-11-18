import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { CalendarUploadPanel } from './CalendarUploadPanel';

const mocks = vi.hoisted(() => ({ get: vi.fn(), form: vi.fn(), post: vi.fn(), put: vi.fn(), del: vi.fn() }));
vi.mock('@/lib/api', () => ({ apiGet: mocks.get, apiPostFormData: mocks.form,
  apiPost: mocks.post, apiPut: mocks.put, apiDelete: mocks.del }));

const profile = { id: 1, profile_code: 'generic', display_name: 'Generic calendar', header_row_index: 1,
  sheet_name: null, column_map_json: { name: ['Name'], start_date: ['Start'] },
  value_maps_json: { kind: {} }, is_default: true, notes: null };
const preview = { ok: true, filename: 'calendar.csv', profile_code: 'generic', upload_id: 'calendar.csv',
  file_sha256: 'hash', headers: ['Name', 'Start'], mapped_columns: { name: 'Name', start_date: 'Start' },
  blocking_errors: [], row_errors: [], parsed_rows: 1, will_insert: 1, will_replace: 2,
  customers: [{ customer_id: 17, customer_name: 'Selected account', events: 1 }], unresolved_customers: [],
  events: [{ row_number: 2, customer_id: 17, customer_name: 'Selected account', name: 'New campaign',
    kind: 'campaign', start_date: '2026-03-01', end_date: '2026-03-05' }], events_truncated: false };

beforeEach(() => {
  vi.clearAllMocks();
  mocks.get.mockResolvedValue({ profiles: [profile] });
  mocks.form.mockImplementation((path: string) => Promise.resolve(path.endsWith('preview') ? preview : { inserted: 1, replaced: 2 }));
});

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const done = vi.fn();
  const view = render(<QueryClientProvider client={client}>
    <CalendarUploadPanel customerId={17} onApplied={done} />
  </QueryClientProvider>);
  return { ...view, done };
}

it('requires preview, shows replacements, then explicitly confirms the same upload', async () => {
  const { container, done } = mount();
  await screen.findByText('Generic calendar');
  expect(screen.getByRole('button', { name: 'Apply calendar' })).toBeDisabled();
  const input = container.querySelector('input[type=file]') as HTMLInputElement;
  fireEvent.change(input, { target: { files: [new File(['Name,Start\nEvent,2026-03-01'], 'calendar.csv')] } });
  fireEvent.click(screen.getByRole('button', { name: 'Preview calendar' }));
  await screen.findByText(/2 existing events/);
  expect(screen.getByText('New campaign')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Apply calendar' }));
  await waitFor(() => expect(done).toHaveBeenCalledOnce());
  const [path, body] = mocks.form.mock.calls[1];
  expect(path).toMatch(/upload\/apply$/);
  expect(body.get('confirm')).toBe('true');
  expect(body.get('customer_id')).toBe('17');
  expect(body.get('upload_id')).toBe('calendar.csv');
});

it('invalidates preview when upload identity or mapping changes', async () => {
  const { container } = mount();
  await screen.findByText('Generic calendar');
  fireEvent.change(container.querySelector('input[type=file]')!, { target: { files: [new File(['csv'], 'calendar.csv')] } });
  fireEvent.click(screen.getByRole('button', { name: 'Preview calendar' }));
  await screen.findByText('New campaign');
  fireEvent.change(screen.getByLabelText('Upload reference'), { target: { value: 'revised' } });
  expect(screen.getByRole('button', { name: 'Apply calendar' })).toBeDisabled();
  expect(mocks.form).toHaveBeenCalledTimes(1);
});
