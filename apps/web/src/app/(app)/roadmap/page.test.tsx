import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import RoadmapPage from './page';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/roadmap',
}));

vi.mock('@/features/planning/PlanningChrome', () => ({
  PlanningChrome: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const gridColumns: string[][] = [];
vi.mock('@/components/EnterpriseDataGrid', () => ({
  EnterpriseDataGrid: ({ columnDefs }: { columnDefs: { headerName?: string }[] }) => {
    gridColumns.push(columnDefs.map((c) => c.headerName ?? ''));
    return <div data-testid="grid">{columnDefs.map((c) => c.headerName).join('|')}</div>;
  },
}));

vi.mock('@/lib/api', () => ({
  apiGet: vi.fn(async (url: string) => {
    if (url.startsWith('/api/v1/grid-fields/roadmap')) {
      return {
        grid_id: 'roadmap',
        items: [{ field: 'retire_target', label: 'Retire Target', group: 'fact', default_hidden: true }],
      };
    }
    if (url === '/api/v1/roadmap') {
      return [
        {
          id: 1,
          sku: 'SKU-1',
          sales_model_name: 'Model 1',
          lifecycle_phase: 'growth',
          whitespace_flag: false,
          overlap_flag: false,
          launch_target: null,
          retire_target: '2027-01-01',
        },
      ];
    }
    return {};
  }),
  apiDelete: vi.fn(),
  apiPost: vi.fn(),
}));

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderWithProviders(
    <QueryClientProvider client={qc}>
      <RoadmapPage />
    </QueryClientProvider>
  );
}

describe('Roadmap grid column picker (N-0034 Tier A host)', () => {
  beforeEach(() => {
    localStorage.clear();
    gridColumns.length = 0;
  });

  it('opens the picker, adds a registry column and keeps it after a remount', async () => {
    const first = renderPage();
    expect(await screen.findByTestId('grid')).toBeInTheDocument();
    expect(screen.getByTestId('grid')).not.toHaveTextContent('Retire Target');

    fireEvent.click(screen.getByTestId('fact-columns-button-roadmap'));
    const toggle = await screen.findByTestId('master-column-toggle-retire_target');
    await waitFor(() => expect(toggle.querySelector('input')).not.toBeDisabled());
    fireEvent.click(toggle.querySelector('input')!);

    await waitFor(() => expect(screen.getByTestId('grid')).toHaveTextContent('Retire Target'));
    expect(screen.getByTestId('fact-columns-button-roadmap')).toHaveTextContent('Columns (1)');
    expect(JSON.parse(localStorage.getItem('cip.grid.roadmap.optional.v1') ?? '{}')).toEqual({
      optionalFields: ['retire_target'],
    });

    first.unmount();
    renderPage();
    await waitFor(() => expect(screen.getByTestId('grid')).toHaveTextContent('Retire Target'));
  });
});
