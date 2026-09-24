import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { BulkLineupBackfillDialog } from './BulkLineupBackfillDialog';

const mockState = vi.hoisted(() => ({
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
    return {};
  }),
  apiPostFormData: vi.fn(async (..._args: unknown[]) => ({
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
  })),
}));

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  apiGet: (url: string) => mockState.apiGet(url),
  apiPostFormData: (...args: unknown[]) => mockState.apiPostFormData(...args),
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
});
