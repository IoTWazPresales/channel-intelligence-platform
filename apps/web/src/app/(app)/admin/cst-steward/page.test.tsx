import React from 'react';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderWithProviders } from '@/test-utils/renderWithProviders';

import CstStewardPage from './page';

vi.mock('./CstArticleAliasesSection', () => ({
  CstArticleAliasesSection: () => <div data-testid="cst-article-aliases-section">aliases-section</div>,
}));

vi.mock('@/components/EnterpriseDataGrid', () => ({
  EnterpriseDataGrid: () => <div data-testid="ops-grid-mock" />,
}));

vi.mock('@/lib/api', () => ({
  apiGet: vi.fn(async (url: string) => {
    if (url.startsWith('/api/v1/cst-steward/key-accounts')) return [];
    if (url.startsWith('/api/v1/cst-steward/report-slots')) return { counts: {}, items: [] };
    return [];
  }),
  apiPatch: vi.fn(async () => ({})),
  apiPost: vi.fn(async () => ({})),
}));

describe('CST steward page Article aliases tab', () => {
  function renderPage() {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return renderWithProviders(
      <QueryClientProvider client={qc}>
        <CstStewardPage />
      </QueryClientProvider>
    );
  }

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('mounts the aliases section on tab 2 and does not use MasterDataGridShell', async () => {
    renderPage();
    expect(screen.queryByTestId('cst-article-aliases-section')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: 'Article aliases' }));
    await waitFor(() => expect(screen.getByTestId('cst-article-aliases-section')).toBeInTheDocument());
    expect(screen.queryByTestId('customers-columns-open')).not.toBeInTheDocument();
    expect(document.body.innerHTML).not.toMatch(/MasterDataGridShell/);
  });
});
