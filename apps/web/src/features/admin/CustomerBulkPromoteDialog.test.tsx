import { fireEvent, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';
import * as apiLib from '@/lib/api';

import {
  CustomerBulkPromoteDialog,
  parseBulkPromoteCsv,
} from './CustomerBulkPromoteDialog';

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof apiLib>('@/lib/api');
  return {
    ...actual,
    apiPost: vi.fn(),
  };
});

const apiPost = apiLib.apiPost as unknown as ReturnType<typeof vi.fn>;

function renderDialog() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderWithProviders(
    <QueryClientProvider client={qc}>
      <CustomerBulkPromoteDialog open onClose={vi.fn()} />
    </QueryClientProvider>
  );
}

describe('parseBulkPromoteCsv', () => {
  it('parses header and blank new_code', () => {
    const rows = parseBulkPromoteCsv('tmp_code,new_code\nTMP-CUST-A,ACME-1\nTMP-CUST-B,');
    expect(rows).toEqual([
      { tmp_code: 'TMP-CUST-A', new_code: 'ACME-1', note: undefined },
      { tmp_code: 'TMP-CUST-B', new_code: '', note: undefined },
    ]);
  });
});

describe('CustomerBulkPromoteDialog', () => {
  beforeEach(() => {
    apiPost.mockReset();
  });

  it('preview shows mixed ready/blocked and confirm posts dry_run false', async () => {
    apiPost.mockResolvedValueOnce({
      dry_run: true,
      summary: { ready: 1, blocked: 1, skipped: 0, applied: 0, total: 2 },
      rows: [
        {
          tmp_code: 'TMP-CUST-A',
          new_code: 'ACME-1',
          customer_id: 10,
          status: 'ready',
          reasons: [],
        },
        {
          tmp_code: 'TMP-CUST-B',
          new_code: 'TAKEN',
          customer_id: 11,
          status: 'blocked',
          reasons: ['code_collision'],
        },
      ],
    });
    apiPost.mockResolvedValueOnce({
      dry_run: false,
      summary: { ready: 0, blocked: 1, skipped: 0, applied: 1, total: 2 },
      rows: [
        {
          tmp_code: 'TMP-CUST-A',
          new_code: 'ACME-1',
          customer_id: 10,
          status: 'applied',
          reasons: [],
          outcome: 'applied',
        },
        {
          tmp_code: 'TMP-CUST-B',
          new_code: 'TAKEN',
          customer_id: 11,
          status: 'blocked',
          reasons: ['code_collision'],
          outcome: 'blocked',
        },
      ],
    });

    renderDialog();
    fireEvent.change(screen.getByTestId('bulk-promote-paste'), {
      target: { value: 'TMP-CUST-A,ACME-1\nTMP-CUST-B,TAKEN' },
    });
    fireEvent.click(screen.getByTestId('bulk-promote-preview-btn'));

    await waitFor(() => expect(screen.getByTestId('bulk-promote-preview')).toBeInTheDocument());
    expect(screen.getByText('Ready')).toBeInTheDocument();
    expect(screen.getByText('Blocked')).toBeInTheDocument();
    expect(screen.getByTestId('bulk-promote-confirm-btn')).toHaveTextContent('Promote 1 ready row');

    fireEvent.click(screen.getByTestId('bulk-promote-confirm-btn'));
    await waitFor(() => expect(screen.getByTestId('bulk-promote-result')).toBeInTheDocument());
    expect(apiPost).toHaveBeenLastCalledWith('/api/v1/customers/promote/batch', {
      rows: [
        { tmp_code: 'TMP-CUST-A', new_code: 'ACME-1', note: undefined },
        { tmp_code: 'TMP-CUST-B', new_code: 'TAKEN', note: undefined },
      ],
      dry_run: false,
    });
    expect(screen.getByText(/applied 1/i)).toBeInTheDocument();
  });
});
