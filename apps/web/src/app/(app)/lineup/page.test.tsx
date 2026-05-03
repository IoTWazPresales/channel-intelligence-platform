import React from 'react';
import { screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import LineupPage from './page';

vi.mock('@/components/PageHeader', () => ({
  PageHeader: ({ title }: { title: string }) => <div>{title}</div>,
}));
vi.mock('@/components/ModuleGridToolbar', () => ({
  ModuleGridToolbar: () => <div data-testid="toolbar" />,
}));
vi.mock('@/components/EnterpriseDataGrid', () => ({
  EnterpriseDataGrid: () => <div data-testid="grid" />,
}));
vi.mock('@/lib/queryError', () => ({ toQueryError: () => null }));

const apiGetMock = vi.fn(async (url: string) => {
  if (url.includes('/lineup/items')) return [];
  if (url.includes('/lineup/events')) return [];
  return [];
});
vi.mock('@/lib/api', () => ({
  apiGet: (url: string) => apiGetMock(url),
  apiDelete: vi.fn(),
  apiPatch: vi.fn(),
  apiPost: vi.fn(),
}));

describe('LineupPage', () => {
  beforeEach(() => {
    apiGetMock.mockClear();
  });

  it('renders ModuleDataSection intro without nesting block content inside a paragraph', async () => {
    const qc = new QueryClient();
    renderWithProviders(
      <QueryClientProvider client={qc}>
        <LineupPage />
      </QueryClientProvider>
    );
    const intro = await screen.findByTestId('module-data-section-intro');
    expect(intro.tagName.toLowerCase()).toBe('div');
    const code = within(intro).getByText('fact_lineup_plan_item');
    expect(code.tagName.toLowerCase()).toBe('code');
    expect(code.closest('p')).toBeNull();
  });
});
