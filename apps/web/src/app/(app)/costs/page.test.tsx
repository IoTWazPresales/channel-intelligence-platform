import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, screen, waitFor } from '@testing-library/react';
import type { ReactElement } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { PlannerDefaultsMaintenance } from '@/features/commercial-planner/PlannerDefaultsMaintenance';
import { renderWithProviders } from '@/test-utils/renderWithProviders';

import CostsPage from './page';

const edge = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
  postForm: vi.fn(),
  download: vi.fn(),
}));

vi.mock('@/lib/api', () => ({
  apiGet: edge.get,
  apiPost: edge.post,
  apiPatch: edge.patch,
  apiDelete: edge.delete,
  apiPostFormData: edge.postForm,
  apiDownloadBlob: edge.download,
}));

const clients: QueryClient[] = [];
const previewPath = '/api/v1/commercial-planner/sku-assumptions/import-preview';
const applyPath = '/api/v1/commercial-planner/sku-assumptions/import-apply';
const confirmation = 'I confirm applying these SKU economics changes to the database.';

function preview(canApply = true) {
  return {
    parse_errors: [],
    rows: [
      {
        source_row: 2,
        sku: 'SKU-TEST',
        part_number: null,
        sales_model: null,
        model_name: null,
        product_id: 1,
        product_sku: 'SKU-TEST',
        product_name: 'Test product',
        match_method: 'sku',
        action: canApply ? 'create' : 'error',
        messages: canApply ? [] : ['Controlled cost must be positive'],
        blocking: !canApply,
        current: null,
        proposed: {
          controlled_cost_amount: 25,
          controlled_cost_currency_code: 'USD',
          vat_rate_pct: 0.15,
          fx_plan_currency_per_cost_currency: 1,
          reserve_total_pct: 0.1,
          promo_reserve_split_pct: 0.5,
        },
      },
    ],
    summary: {
      creates: canApply ? 1 : 0,
      updates: 0,
      errors: canApply ? 0 : 1,
      blocking_errors: canApply ? 0 : 1,
    },
    can_apply: canApply,
  };
}

function renderPage(element: ReactElement = <CostsPage />) {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Infinity },
      mutations: { retry: false },
    },
  });
  clients.push(qc);
  renderWithProviders(
    <QueryClientProvider client={qc}>
      {element}
    </QueryClientProvider>,
  );
  return qc;
}

function upload(name = 'costs.csv') {
  const file = new File(['sku,controlled_cost_amount\nSKU-TEST,25'], name, { type: 'text/csv' });
  fireEvent.change(screen.getByLabelText('SKU economics file'), { target: { files: [file] } });
  return file;
}

describe('Costs page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    edge.get.mockResolvedValue([]);
    edge.postForm.mockImplementation(async (path: string) => {
      if (path === previewPath) return preview();
      if (path === applyPath) return { applied_creates: 1, applied_updates: 0, summary: {} };
      throw new Error(`Unexpected upload route: ${path}`);
    });
  });

  afterEach(() => {
    cleanup();
    for (const client of clients.splice(0)) client.clear();
  });

  it('uses the existing template, preview, confirmation and apply endpoints', async () => {
    const qc = renderPage();
    const invalidate = vi.spyOn(qc, 'invalidateQueries');

    expect(screen.getByRole('heading', { name: 'Costs' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Planning' })).toHaveAttribute('href', '/lineup');

    fireEvent.click(screen.getByRole('button', { name: 'Download template' }));
    expect(edge.download).toHaveBeenCalledWith(
      '/api/v1/commercial-planner/sku-assumptions/import-template',
      'sku_economics_template.csv',
    );

    const file = upload();
    await screen.findByText(/Preview: 1 create/);
    expect(screen.getByText('SKU-TEST - Test product')).toBeInTheDocument();
    expect(edge.postForm).toHaveBeenCalledTimes(1);
    const previewForm = edge.postForm.mock.calls[0][1] as FormData;
    expect(edge.postForm.mock.calls[0][0]).toBe(previewPath);
    expect(previewForm.get('file')).toBe(file);
    expect(previewForm.get('confirm')).toBeNull();

    const apply = screen.getByRole('button', { name: 'Apply import' });
    expect(apply).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox', { name: confirmation }));
    expect(apply).toBeEnabled();
    fireEvent.click(apply);

    expect(await screen.findByTestId('sku-import-apply-summary')).toHaveTextContent(
      'Applied: 1 created, 0 updated.',
    );
    expect(edge.postForm).toHaveBeenCalledTimes(2);
    const applyForm = edge.postForm.mock.calls[1][1] as FormData;
    expect(edge.postForm.mock.calls[1][0]).toBe(applyPath);
    expect(applyForm.get('file')).toBe(file);
    expect(applyForm.get('confirm')).toBe('true');

    for (const key of [
      'commercial-planner',
      'commercial-plan-lines',
      'commercial-plan-summary',
      'commercial-plan-suggestions',
      'plan-readiness',
      'admin-products',
    ]) {
      expect(invalidate).toHaveBeenCalledWith({ queryKey: [key] });
    }
    expect(screen.queryByRole('button', { name: 'Apply import' })).not.toBeInTheDocument();
    expect(edge.get).not.toHaveBeenCalled();
  });

  it('keeps a blocking preview from being confirmed or applied', async () => {
    edge.postForm.mockResolvedValue(preview(false));
    renderPage();
    upload();

    expect(await screen.findByText('Controlled cost must be positive')).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: confirmation })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Apply import' })).toBeDisabled();
    expect(edge.postForm).toHaveBeenCalledTimes(1);
    expect(edge.postForm.mock.calls[0][0]).toBe(previewPath);
  });

  it('requires fresh confirmation after previewing another file', async () => {
    renderPage();
    upload('first.csv');
    await screen.findByText(/Preview: 1 create/);
    fireEvent.click(screen.getByRole('checkbox', { name: confirmation }));
    expect(screen.getByRole('button', { name: 'Apply import' })).toBeEnabled();

    upload('second.csv');
    await waitFor(() => expect(edge.postForm).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.getByRole('checkbox', { name: confirmation })).not.toBeChecked());
    expect(screen.getByRole('button', { name: 'Apply import' })).toBeDisabled();
    expect(edge.postForm.mock.calls.every(([path]) => path === previewPath)).toBe(true);
  });

  it('leaves a Costs link in planner defaults and removes the upload controls there', async () => {
    renderPage(<PlannerDefaultsMaintenance />);
    expect(screen.getByRole('link', { name: 'Costs page' })).toHaveAttribute('href', '/costs');
    expect(screen.getByText(/Costs are uploaded on the/)).toHaveTextContent(
      'Costs are uploaded on the Costs page.',
    );
    expect(screen.queryByRole('button', { name: 'Upload SKU economics file' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Download template' })).not.toBeInTheDocument();
    expect(screen.queryByLabelText('SKU economics file')).not.toBeInTheDocument();
    expect(await screen.findByText(/No SKU assumptions yet/)).toBeInTheDocument();
    expect(edge.postForm).not.toHaveBeenCalled();
  });
});
