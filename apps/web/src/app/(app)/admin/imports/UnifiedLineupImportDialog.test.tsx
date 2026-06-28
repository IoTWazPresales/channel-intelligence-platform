import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { UnifiedLineupImportDialog } from './UnifiedLineupImportDialog';

vi.mock('@/lib/api', () => ({
  apiGet: vi.fn(),
  apiPostFormData: vi.fn(),
  safeDisplayError: (e: unknown) => (e instanceof Error ? e.message : String(e)),
}));

vi.mock('@/features/background-tasks/backgroundTaskRegistry', () => ({
  registerClientBackgroundTask: vi.fn(),
}));

import { apiGet, apiPostFormData } from '@/lib/api';
import { registerClientBackgroundTask } from '@/features/background-tasks/backgroundTaskRegistry';

const apiGetMock = vi.mocked(apiGet);
const apiPostFormDataMock = vi.mocked(apiPostFormData);
const registerMock = vi.mocked(registerClientBackgroundTask);

function renderDialog() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return {
    user: userEvent.setup(),
    ...renderWithProviders(
      <QueryClientProvider client={qc}>
        <UnifiedLineupImportDialog open onClose={() => {}} />
      </QueryClientProvider>,
    ),
  };
}

describe('UnifiedLineupImportDialog', () => {
  beforeEach(() => {
    apiGetMock.mockReset();
    apiPostFormDataMock.mockReset();
    registerMock.mockReset();
    apiGetMock.mockResolvedValue([
      { id: 5, plan_name: 'Q1 Plan', country_code: 'ZA', currency_code: 'ZAR' },
    ]);
  });

  it('submits selected files as repeated `files` field with shared metadata and registers tasks', async () => {
    apiPostFormDataMock.mockResolvedValue({
      file_count: 2,
      dispatched: 2,
      files: [
        { filename: 'a.csv', case_id: 11, import_job_id: 101, outcome: 'enqueued', task_id: 't-1' },
        { filename: 'b.xlsx', case_id: 12, import_job_id: 102, outcome: 'enqueued', task_id: 't-2' },
      ],
    });

    const { user } = renderDialog();

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const fileA = new File(['x'], 'a.csv', { type: 'text/csv' });
    const fileB = new File(['y'], 'b.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    });
    await user.upload(input, [fileA, fileB]);

    await user.type(screen.getByLabelText('Period label'), '26Q1');

    await user.click(screen.getByTestId('unified-import-submit'));

    await waitFor(() => expect(apiPostFormDataMock).toHaveBeenCalledTimes(1));

    const [path, fd] = apiPostFormDataMock.mock.calls[0];
    expect(path).toBe('/api/v1/commercial-planner/lineup/unified-import');
    const form = fd as FormData;
    expect(form.getAll('files')).toHaveLength(2);
    expect(form.get('period_label')).toBe('26Q1');

    await waitFor(() => expect(registerMock).toHaveBeenCalledTimes(2));
    expect(registerMock).toHaveBeenCalledWith(
      expect.objectContaining({ taskId: 't-1', importJobId: 101, kind: 'commercial_planner_lineup_parse' }),
    );

    expect(await screen.findByTestId('unified-import-results')).toBeInTheDocument();
  });

  it('disables submit until at least one valid file is selected', async () => {
    renderDialog();
    expect(screen.getByTestId('unified-import-submit')).toBeDisabled();
  });

  it('ignores files with unsupported extensions', async () => {
    const { user } = renderDialog();
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, new File(['x'], 'notes.txt', { type: 'text/plain' }));
    expect(screen.getByTestId('unified-import-submit')).toBeDisabled();
  });
});
