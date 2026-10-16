import React from 'react';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/test-utils/renderWithProviders';

const mockApiPost = vi.fn();
vi.mock('@/lib/api', () => ({
  apiPost: (...args: unknown[]) => mockApiPost(...args),
  safeDisplayError: (e: unknown) => (e instanceof Error ? e.message : String(e)),
}));

import { DsiHeaderRowStrip } from './DsiHeaderRowStrip';

function renderStrip(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderWithProviders(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

const pinnacle = {
  sheet_name: 'Sales',
  sheet_key: 'Sales',
  header_row: 1,
  columns: ['Invoice Number', 'Invoice Date', 'Product Code', 'QTY'],
};

describe('DsiHeaderRowStrip', () => {
  beforeEach(() => {
    mockApiPost.mockReset();
    mockApiPost.mockResolvedValue({});
  });

  it('shows the 1-based row the headers were found on', () => {
    renderStrip(<DsiHeaderRowStrip jobId={7} sheets={[pinnacle]} />);
    expect(screen.getByTestId('dsi-header-row-text-Sales')).toHaveTextContent('Headers found on row 2');
  });

  it('banner layout reads as row 20', () => {
    renderStrip(<DsiHeaderRowStrip jobId={7} sheets={[{ ...pinnacle, sheet_key: 'Sell Out', header_row: 19 }]} />);
    expect(screen.getByTestId('dsi-header-row-text-Sell Out')).toHaveTextContent('Headers found on row 20');
  });

  it('lets the uploader change the row and posts it 1-based', async () => {
    const onChanged = vi.fn();
    renderStrip(<DsiHeaderRowStrip jobId={7} sheets={[pinnacle]} onChanged={onChanged} />);
    const apply = screen.getByTestId('dsi-header-row-apply-Sales');
    expect(apply).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Headers on row'), { target: { value: '3' } });
    expect(apply).toBeEnabled();
    fireEvent.click(apply);
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(mockApiPost).toHaveBeenCalledWith('/api/v1/imports/jobs/7/dsi-header-row', {
      header_row: 3,
      filename: undefined,
      sheet_key: 'Sales',
    });
  });

  it('says so plainly when no header row was found', () => {
    renderStrip(
      <DsiHeaderRowStrip jobId={7} sheets={[{ sheet_key: 'Sales', sheet_name: 'Sales', header_row: 0, columns: ['Unnamed: 0'] }]} />
    );
    expect(screen.getByTestId('dsi-header-row-text-Sales')).toHaveTextContent('No header row found');
  });

  it('marks an uploader-set row and hides the editor once the job is loaded', () => {
    renderStrip(
      <DsiHeaderRowStrip jobId={7} sheets={[{ ...pinnacle, header_row_user_set: true }]} locked />
    );
    expect(screen.getByTestId('dsi-header-row-text-Sales')).toHaveTextContent('(set by you)');
    expect(screen.queryByTestId('dsi-header-row-apply-Sales')).not.toBeInTheDocument();
  });

  it('refuses an out-of-range row', () => {
    renderStrip(<DsiHeaderRowStrip jobId={7} sheets={[pinnacle]} />);
    fireEvent.change(screen.getByLabelText('Headers on row'), { target: { value: '0' } });
    expect(screen.getByTestId('dsi-header-row-apply-Sales')).toBeDisabled();
  });
});
