import { screen, waitFor, within } from '@testing-library/react';
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
const LEGACY_LABEL = 'Product, any identifier (older layouts)';
const TARGETS = [
  { value: 'raw_sales_model_token', label: 'Sales model / marketing name', group: 'main' },
  { value: 'raw_part_number_token', label: 'Part number', group: 'main' },
  { value: 'raw_barcode_token', label: 'Barcode (EAN or UPC)', group: 'main' },
  { value: 'raw_article_token', label: 'Customer product code', group: 'main' },
  { value: 'units_sold', label: 'Units sold', group: 'main' },
  { value: 'reported_soh', label: 'On-hand (stock)', group: 'main' },
  { value: 'unit_mac', label: 'Unit MAC', group: 'more' },
  { value: 'raw_product_token', label: LEGACY_LABEL, group: 'more', legacy: true },
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

    // Open the first row's list (Artikel Nr) with its popup button: it shows every target.
    await user.click(within(card).getAllByRole('button', { name: 'Open' })[0]);
    // The dropdown is portalled outside the dialog, so the dialog marks it hidden to role queries.
    // It offers the separate identifier columns and a "More columns" group, but not the older single column.
    expect(await screen.findByRole('option', { name: /^Part number/, hidden: true })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /^Sales model \/ marketing name/, hidden: true })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /^Customer product code/, hidden: true })).toBeInTheDocument();
    expect(screen.getByText('More columns')).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /^Unit MAC/, hidden: true })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: LEGACY_LABEL, hidden: true })).toBeNull();
    await user.click(screen.getByRole('option', { name: /^Barcode \(EAN or UPC\)/, hidden: true }));
    await waitFor(() => expect(screen.getByTestId('cst-bulk-upload-submit')).toBeEnabled());

    await user.click(screen.getByTestId('cst-bulk-upload-submit'));
    await waitFor(() => expect(onJobsCreated).toHaveBeenCalledWith([56]));
    const fd = apiPostMock.mock.calls[1][1] as FormData;
    expect(fd.get('customer_id')).toBe('299');
    expect(JSON.parse(String(fd.get('layouts')))).toEqual([
      {
        signature: 'sigNEW',
        name: 'amazon w1 layout',
        field_mapping: { Stuks: 'units_sold', 'Artikel Nr': 'raw_barcode_token' },
      },
    ]);
  });

  it('a layout that maps the older single product column keeps loading and is offered a re-map into the new slots', async () => {
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
              columns: ['Artikel Nr', 'Stuks'],
              layout_signature: 'sigOLD',
              layout: {
                id: 7,
                name: 'Weekly report',
                legacy_product_slot: true,
                mapping: { 'Artikel Nr': 'raw_product_token', Stuks: 'units_sold' },
              },
              detected_mapping: {},
              samples: { 'Artikel Nr': ['A1'], Stuks: ['3'] },
            },
          ],
        };
      }
      return { group_count: 1, jobs: [{ outcome: 'created', import_job_id: 57, filenames: ['week 1.csv'] }] };
    });
    const { user, onJobsCreated } = renderDialog();
    await pickCustomer(user, 'Takealot');
    await user.upload(document.querySelector('input[type="file"]') as HTMLInputElement, file());
    await user.click(screen.getByTestId('cst-bulk-preview-groups'));

    // It still matches by itself (nothing to map) and the file list says the layout is the older kind.
    expect(await screen.findByText(/Every file matches a saved layout/)).toBeInTheDocument();
    expect(screen.getByText('Layout: Weekly report (older product column)')).toBeInTheDocument();
    const offer = screen.getByTestId('cst-legacy-layout-sigOLD');
    expect(offer).toHaveTextContent('It keeps loading as before');
    expect(screen.getByTestId('cst-bulk-upload-submit')).toBeEnabled();

    // Re-map: the mapping step opens on what the layout maps today, with the older column flagged.
    await user.click(within(offer).getByTestId('cst-remap-sigOLD'));
    const card = await screen.findByTestId('cst-new-layout-sigOLD');
    expect(within(card).getByText(/Re-map column layout/)).toBeInTheDocument();
    expect(within(card).getByText(/Older single product column/)).toBeInTheDocument();
    await user.click(within(card).getAllByRole('button', { name: 'Open' })[0]);
    await user.click(await screen.findByRole('option', { name: /^Part number/, hidden: true }));
    await waitFor(() => expect(screen.getByTestId('cst-bulk-upload-submit')).toBeEnabled());

    await user.click(screen.getByTestId('cst-bulk-upload-submit'));
    await waitFor(() => expect(onJobsCreated).toHaveBeenCalledWith([57]));
    const fd = apiPostMock.mock.calls[1][1] as FormData;
    expect(JSON.parse(String(fd.get('layouts')))).toEqual([
      {
        signature: 'sigOLD',
        layout_id: 7,
        name: 'Weekly report',
        field_mapping: { 'Artikel Nr': 'raw_part_number_token', Stuks: 'units_sold' },
      },
    ]);
  });

  it('a saved layout that already uses the new columns can still be edited', async () => {
    apiPostMock.mockImplementation(async (path: string) => {
      if (path.endsWith('/batch-propose')) {
        return {
          group_count: 1,
          file_count: 1,
          customer_id: 20,
          targets: TARGETS,
          files: [
            {
              filename: 'amazon.csv',
              readable: true,
              columns: ['EAN', 'UPC', 'Units'],
              layout_signature: 'sigNEW',
              layout: {
                id: 9,
                name: 'Amazon daily',
                legacy_product_slot: false,
                mapping: { EAN: 'raw_barcode_token', UPC: 'raw_barcode_token', Units: 'units_sold' },
              },
              detected_mapping: {},
              samples: { EAN: ['4711'], UPC: ['1234'], Units: ['3'] },
            },
          ],
        };
      }
      return { group_count: 1, jobs: [{ outcome: 'created', import_job_id: 58, filenames: ['amazon.csv'] }] };
    });
    const { user } = renderDialog();
    await pickCustomer(user, 'Takealot');
    await user.upload(document.querySelector('input[type="file"]') as HTMLInputElement, file());
    await user.click(screen.getByTestId('cst-bulk-preview-groups'));

    expect(await screen.findByText(/Every file matches a saved layout/)).toBeInTheDocument();
    const offer = screen.getByTestId('cst-saved-layout-sigNEW');
    expect(offer).toHaveTextContent('is saved for this customer');
    expect(screen.queryByTestId('cst-legacy-layout-sigNEW')).toBeNull();

    // Editing opens the mapping step on what the layout maps today and updates that layout.
    await user.click(within(offer).getByTestId('cst-remap-sigNEW'));
    const card = await screen.findByTestId('cst-new-layout-sigNEW');
    expect(within(card).getByText(/Re-map column layout/)).toBeInTheDocument();
  });

  it('does not send a re-map unless the uploader asks for one', async () => {
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
              columns: ['Artikel Nr', 'Stuks'],
              layout_signature: 'sigOLD',
              layout: {
                id: 7,
                name: 'Weekly report',
                legacy_product_slot: true,
                mapping: { 'Artikel Nr': 'raw_product_token', Stuks: 'units_sold' },
              },
              detected_mapping: {},
              samples: {},
            },
          ],
        };
      }
      return { group_count: 1, jobs: [{ outcome: 'created', import_job_id: 58, filenames: ['week 1.csv'] }] };
    });
    const { user, onJobsCreated } = renderDialog();
    await pickCustomer(user, 'Takealot');
    await user.upload(document.querySelector('input[type="file"]') as HTMLInputElement, file());
    await user.click(screen.getByTestId('cst-bulk-preview-groups'));
    await screen.findByTestId('cst-legacy-layout-sigOLD');
    await user.click(screen.getByTestId('cst-bulk-upload-submit'));
    await waitFor(() => expect(onJobsCreated).toHaveBeenCalledWith([58]));
    expect((apiPostMock.mock.calls[1][1] as FormData).has('layouts')).toBe(false);
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
