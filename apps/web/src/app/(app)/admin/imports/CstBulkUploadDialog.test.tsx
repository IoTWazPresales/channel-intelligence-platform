import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { CstBulkUploadDialog } from './CstBulkUploadDialog';

vi.mock('@/lib/api', () => ({
  apiGet: vi.fn(),
  apiPatch: vi.fn(),
  apiPostFormData: vi.fn(),
  safeDisplayError: (e: unknown) => (e instanceof Error ? e.message : String(e)),
}));

import { apiGet, apiPatch, apiPostFormData } from '@/lib/api';

const apiGetMock = vi.mocked(apiGet);
const apiPatchMock = vi.mocked(apiPatch);
const apiPostMock = vi.mocked(apiPostFormData);

const CUSTOMERS = [
  { id: 20, name: 'Takealot', layout_count: 2 },
  { id: 299, name: 'AMAZON COMMERCIAL SERVICES (SOUTH AFRICA)', layout_count: 0 },
];
const TARGETS = [
  { value: 'raw_product_token', label: 'Product (code, barcode or SKU)' },
  { value: 'units_sold', label: 'Units sold' },
  { value: 'reported_soh', label: 'On-hand (stock)' },
];
const LAYOUT = {
  id: 7,
  customer_id: 20,
  name: 'Weekly report',
  headers: ['barcode', 'sales'],
  report_structure_type: 'flat',
  is_hidden: false,
};

function file(name = 'week 1.csv') {
  return new File(['x'], name, { type: 'text/csv' });
}

function renderDialog(onJobsCreated = vi.fn(), onClose = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return {
    user: userEvent.setup(),
    onJobsCreated,
    onClose,
    ...renderWithProviders(
      <QueryClientProvider client={qc}>
        <CstBulkUploadDialog open onClose={onClose} onJobsCreated={onJobsCreated} />
      </QueryClientProvider>,
    ),
  };
}

async function pickCustomer(user: ReturnType<typeof userEvent.setup>, name: string) {
  await user.click(screen.getByRole('combobox', { name: 'Reporting customer' }));
  await user.click(await screen.findByRole('option', { name }));
}

describe('CstBulkUploadDialog (N-0111: pick a reporting customer, not a source)', () => {
  beforeEach(() => {
    apiGetMock.mockReset();
    apiPatchMock.mockReset();
    apiPostMock.mockReset();
    apiGetMock.mockImplementation(async (path: string) => {
      if (path.startsWith('/api/v1/imports/cst/reporting-customers')) return CUSTOMERS;
      if (path.startsWith('/api/v1/imports/cst/layouts')) return [LAYOUT];
      throw new Error(`unexpected GET ${path}`);
    });
  });

  it('lists only the reporting customers by name, with no source and no customer code', async () => {
    const { user } = renderDialog();
    await user.click(await screen.findByRole('combobox', { name: 'Reporting customer' }));
    expect(await screen.findByRole('option', { name: 'Takealot' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'AMAZON COMMERCIAL SERVICES (SOUTH AFRICA)' })).toBeInTheDocument();
    expect(screen.queryByText(/source/i)).toBeNull();
    expect(apiGetMock.mock.calls.map((c) => c[0])).not.toContain('/api/v1/imports/sources');
  });

  it('shows the customer\'s saved layouts and renames one', async () => {
    apiPatchMock.mockResolvedValue({ ...LAYOUT, name: 'Takealot weekly' });
    const { user } = renderDialog();
    await pickCustomer(user, 'Takealot');
    const saved = await screen.findByTestId('cst-saved-layouts');
    expect(within(saved).getByText('Weekly report')).toBeInTheDocument();
    await user.click(within(saved).getByRole('button', { name: 'Rename' }));
    const input = within(saved).getByLabelText('Name of layout Weekly report');
    await user.clear(input);
    await user.type(input, 'Takealot weekly');
    await user.click(within(saved).getByRole('button', { name: 'Save name' }));
    await waitFor(() =>
      expect(apiPatchMock).toHaveBeenCalledWith('/api/v1/imports/cst/layouts/7', { name: 'Takealot weekly' }),
    );
  });

  it('a file that matches a saved layout needs no mapping and uploads for the customer', async () => {
    apiPostMock.mockImplementation(async (path: string) => {
      if (path.endsWith('/batch-propose')) {
        return {
          group_count: 1,
          file_count: 1,
          customer_id: 20,
          targets: TARGETS,
          files: [
            {
              filename: 'week 1.csv',
              readable: true,
              columns: ['Barcode', 'sales'],
              layout_signature: 'sig1',
              layout: { id: 7, name: 'Weekly report' },
              detected_mapping: {},
              samples: {},
            },
          ],
        };
      }
      return { group_count: 1, jobs: [{ outcome: 'created', import_job_id: 55, filenames: ['week 1.csv'] }] };
    });
    const { user, onJobsCreated, onClose } = renderDialog();
    await pickCustomer(user, 'Takealot');
    await user.upload(document.querySelector('input[type="file"]') as HTMLInputElement, file());
    await user.click(screen.getByTestId('cst-bulk-preview-groups'));
    expect(await screen.findByText(/Every file matches a saved layout/)).toBeInTheDocument();
    expect(screen.getByText('Layout: Weekly report')).toBeInTheDocument();
    await user.click(screen.getByTestId('cst-bulk-upload-submit'));

    await waitFor(() => expect(onJobsCreated).toHaveBeenCalledWith([55]));
    expect(onClose).toHaveBeenCalled();
    const [, fd] = apiPostMock.mock.calls[1];
    expect((fd as FormData).get('customer_id')).toBe('20');
    expect((fd as FormData).has('source_id')).toBe(false);
    expect((fd as FormData).has('layouts')).toBe(false);
  });

  it('an unrecognised layout opens the mapping step, blocks upload until the product is mapped, then saves it', async () => {
    apiPostMock.mockImplementation(async (path: string) => {
      if (path.endsWith('/batch-propose')) {
        return {
          group_count: 1,
          file_count: 1,
          customer_id: 299,
          targets: TARGETS,
          files: [
            {
              filename: 'amazon w1.csv',
              readable: true,
              columns: ['Artikel Nr', 'Stuks'],
              layout_signature: 'sigNEW',
              layout: null,
              similar_layout: null,
              detected_mapping: { Stuks: 'units_sold' },
              samples: { 'Artikel Nr': ['A1'], Stuks: ['3'] },
            },
          ],
        };
      }
      return { group_count: 1, jobs: [{ outcome: 'created', import_job_id: 56, filenames: ['amazon w1.csv'] }] };
    });
    const { user, onJobsCreated } = renderDialog();
    await pickCustomer(user, 'AMAZON COMMERCIAL SERVICES (SOUTH AFRICA)');
    await user.upload(document.querySelector('input[type="file"]') as HTMLInputElement, file('amazon w1.csv'));
    await user.click(screen.getByTestId('cst-bulk-preview-groups'));

    const card = await screen.findByTestId('cst-new-layout-sigNEW');
    expect(within(card).getByText(/New column layout/)).toBeInTheDocument();
    expect(screen.getByText('New layout: map the columns')).toBeInTheDocument();
    // Units are detected; the product column is not mapped yet, so the upload is blocked.
    expect(screen.getByTestId('cst-bulk-upload-submit')).toBeDisabled();

    const mapProduct = within(card).getByTestId('cst-map-sigNEW-map-Artikel Nr');
    await user.click(mapProduct);
    fireEvent.change(mapProduct, { target: { value: 'Product' } });
    // The dropdown is portalled outside the dialog, so the dialog marks it hidden to role queries.
    await user.click(await screen.findByRole('option', { name: /Product \(code, barcode or SKU\)/, hidden: true }));
    await waitFor(() => expect(screen.getByTestId('cst-bulk-upload-submit')).toBeEnabled());

    await user.click(screen.getByTestId('cst-bulk-upload-submit'));
    await waitFor(() => expect(onJobsCreated).toHaveBeenCalledWith([56]));
    const fd = apiPostMock.mock.calls[1][1] as FormData;
    expect(fd.get('customer_id')).toBe('299');
    expect(JSON.parse(String(fd.get('layouts')))).toEqual([
      {
        signature: 'sigNEW',
        name: 'amazon w1 layout',
        field_mapping: { Stuks: 'units_sold', 'Artikel Nr': 'raw_product_token' },
      },
    ]);
  });

  it('keeps the dialog open and shows the reason when a file could not be placed', async () => {
    apiPostMock.mockImplementation(async (path: string) => {
      if (path.endsWith('/batch-propose')) {
        return {
          group_count: 1,
          file_count: 1,
          customer_id: 20,
          targets: TARGETS,
          files: [
            {
              filename: 'week 1.csv',
              readable: true,
              columns: ['Barcode', 'sales'],
              layout_signature: 'sig1',
              layout: { id: 7, name: 'Weekly report' },
              detected_mapping: {},
              samples: {},
            },
          ],
        };
      }
      return { group_count: 0, jobs: [{ outcome: 'error', filenames: ['week 1.csv'], error: 'Map the product column' }] };
    });
    const { user, onClose } = renderDialog();
    await pickCustomer(user, 'Takealot');
    await user.upload(document.querySelector('input[type="file"]') as HTMLInputElement, file());
    await user.click(screen.getByTestId('cst-bulk-preview-groups'));
    await screen.findByText(/Every file matches a saved layout/);
    await user.click(screen.getByTestId('cst-bulk-upload-submit'));
    expect(await screen.findByTestId('cst-bulk-error')).toHaveTextContent('Map the product column');
    expect(onClose).not.toHaveBeenCalled();
  });
});
