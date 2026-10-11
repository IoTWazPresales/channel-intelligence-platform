import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { BulkLineupBackfillDialog } from './BulkLineupBackfillDialog';

const mockState = vi.hoisted(() => {
  let releaseSession: (value: unknown) => void = () => {};
  const sessionGate = new Promise((resolve) => {
    releaseSession = resolve;
  });
  return {
    releaseSession: (value: unknown) => releaseSession(value),
    sessionGate,
    apiGet: vi.fn(async (url: string) => {
      if (url === '/api/v1/catalog/product-lines') {
        return {
          product_lines: [
            { code: 'NB', product_count: 10, label: 'NB' },
            { code: 'PT', product_count: 4, label: 'PT' },
            { code: 'LM', product_count: 2, label: 'LM' },
          ],
          null_product_line_count: 1,
        };
      }
      if (url.includes('/lineup/bulk-backfill/preview/')) {
        return sessionGate;
      }
      return {};
    }),
    apiPostFormData: vi.fn(async (url: string, ..._args: unknown[]) => {
      if (String(url).includes('/bulk-backfill/apply')) {
        return { async: true, session_import_job_id: 5, task_id: 'task-bulk-1' };
      }
      return {
    session_import_job_id: 5,
    persisted: true,
    preview: {
      case_proposals: [
        {
          proposal_key: 'f0:PT',
          filename: 'lineup.xlsx',
          sheet_name: 'PT',
          period_label: '2026Q1',
          period_source_tier: 'folder',
          period_flags: [],
          business_unit: 'PT',
          bu_report: { source_tier: 'folder', flags: [] },
          status: 'ready',
          attention_reasons: [],
          row_count: 3,
          flags: [],
        },
      ],
      supersession_collisions: [],
      catalogue_miss_worklist: [],
      totals: {},
    },
  };
    }),
  };
});

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  apiGet: (url: string) => mockState.apiGet(url),
  apiPostFormData: (...args: [string, ...unknown[]]) => mockState.apiPostFormData(...args),
}));

describe('BulkLineupBackfillDialog', () => {
  it('BU override options and archive folder codes come from the product-lines endpoint', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    renderWithProviders(
      <QueryClientProvider client={qc}>
        <BulkLineupBackfillDialog open onClose={() => {}} />
      </QueryClientProvider>,
    );

    await waitFor(() => expect(mockState.apiGet).toHaveBeenCalledWith('/api/v1/catalog/product-lines'));
    await waitFor(() => expect(qc.getQueryData(['catalog', 'product-lines'])).toBeTruthy());
    // Folder staging waits for the codes, so a quick pick cannot lose the BU folder segment.
    await waitFor(() => expect(screen.getByRole('button', { name: 'Select archive folder' })).toBeEnabled());

    // A PT/… archive folder is recognised as a product-line folder from the endpoint's codes.
    const folderInput = document.querySelector('input[webkitdirectory]') as HTMLInputElement;
    const file = new File(['x'], 'lineup.xlsx');
    Object.defineProperty(file, 'webkitRelativePath', { value: 'Product Lineup/PT/2026/Q1/lineup.xlsx' });
    fireEvent.change(folderInput, { target: { files: [file] } });
    expect(await screen.findByText(/1 with product-line\/year\/quarter paths/)).toBeInTheDocument();
    expect(screen.getByText('PT\\2026\\Q1')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Run preview' }));
    const row = (await screen.findByText('lineup.xlsx / PT')).closest('tr') as HTMLElement;
    const select = within(row).getByDisplayValue('PT') as HTMLSelectElement;
    const options = Array.from(select.options).map((o) => o.value);
    expect(options).toEqual(['', 'NB', 'PT', 'LM']);

    const fd = mockState.apiPostFormData.mock.calls[0][1] as FormData;
    expect(fd.getAll('folder_paths')).toEqual(['PT\\2026\\Q1']);
  });

  it('keeps the dialog open after Apply and shows the completion summary', async () => {
    const onClose = vi.fn();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    renderWithProviders(
      <QueryClientProvider client={qc}>
        <BulkLineupBackfillDialog open onClose={onClose} />
      </QueryClientProvider>,
    );

    await waitFor(() => expect(screen.getByRole('button', { name: 'Select archive folder' })).toBeEnabled());
    const folderInput = document.querySelector('input[webkitdirectory]') as HTMLInputElement;
    const file = new File(['x'], 'lineup.xlsx');
    Object.defineProperty(file, 'webkitRelativePath', { value: 'Product Lineup/PT/2026/Q1/lineup.xlsx' });
    fireEvent.change(folderInput, { target: { files: [file] } });
    fireEvent.click(screen.getByRole('button', { name: 'Run preview' }));
    await screen.findByText('lineup.xlsx / PT');

    fireEvent.click(screen.getByRole('checkbox', { name: /I have reviewed the preview/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Apply 1 cases' }));

    expect(await screen.findByTestId('bulk-backfill-apply-status')).toHaveTextContent(
      'Applying session #5. This dialog stays open.',
    );
    expect(screen.getByRole('heading', { name: 'Bulk historical lineup backfill' })).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();

    mockState.releaseSession({
      session_import_job_id: 5,
      job_status: 'completed',
      job_stage: 'loaded',
      apply: { applied: 1, skipped: 2 },
    });

    expect(await screen.findByText(/Applied 1, skipped 2/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Link POs' })).toHaveAttribute('href', '/admin/po-management');
    expect(screen.getByRole('link', { name: 'Review lineup cases' })).toHaveAttribute('href', '/commercial-planner');
    expect(onClose).not.toHaveBeenCalled();
  });
});
