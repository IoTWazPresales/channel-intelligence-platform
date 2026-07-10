import { fireEvent, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';
import * as apiLib from '@/lib/api';

import { DistributorDispositionDialog } from './DistributorDispositionDialog';

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof apiLib>('@/lib/api');
  return { ...actual, apiPost: vi.fn() };
});

const apiPost = apiLib.apiPost as unknown as ReturnType<typeof vi.fn>;

describe('DistributorDispositionDialog', () => {
  beforeEach(() => apiPost.mockReset());

  it('preview then confirm parked disposition', async () => {
    apiPost.mockResolvedValueOnce({
      dry_run: true,
      disposition: 'parked',
      summary: { ready: 1, blocked: 0, skipped: 0, applied: 0, total: 1 },
      rows: [{ distributor_id: 10, tmp_code: 'TMP-DIST-A', status: 'ready', reasons: [] }],
    });
    apiPost.mockResolvedValueOnce({
      dry_run: false,
      disposition: 'parked',
      summary: { ready: 0, blocked: 0, skipped: 0, applied: 1, total: 1 },
      rows: [{ distributor_id: 10, tmp_code: 'TMP-DIST-A', status: 'applied', reasons: [], outcome: 'applied' }],
    });

    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    renderWithProviders(
      <QueryClientProvider client={qc}>
        <DistributorDispositionDialog open onClose={vi.fn()} distributorIds={[10]} />
      </QueryClientProvider>
    );

    fireEvent.click(screen.getByTestId('disposition-preview-btn'));
    await waitFor(() => expect(screen.getByTestId('disposition-preview')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('disposition-confirm-btn'));
    await waitFor(() => expect(screen.getByTestId('disposition-result')).toBeInTheDocument());
    expect(apiPost).toHaveBeenLastCalledWith('/api/v1/distributors/disposition/batch', {
      distributor_ids: [10],
      disposition: 'parked',
      note: undefined,
      dry_run: false,
    });
  });
});

