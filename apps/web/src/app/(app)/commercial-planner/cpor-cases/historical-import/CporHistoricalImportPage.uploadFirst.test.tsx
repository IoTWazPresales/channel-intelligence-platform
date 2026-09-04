import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactElement } from 'react';

import CporHistoricalImportPage from './page';

const navState = vi.hoisted(() => ({ search: '' }));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/commercial-planner/cpor-cases/historical-import',
  useSearchParams: () => new URLSearchParams(navState.search),
}));

vi.mock('@/features/import-mapping/CanonicalColumnMappingPanel', () => ({
  CanonicalColumnMappingPanel: () => <div data-testid="plan-template-mapping" />,
}));

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return {
    ...actual,
    apiGet: vi.fn(async (path: string) => {
      if (String(path).includes('/imports/sources')) {
        return [{ id: 1, code: 'cpor', name: 'CPOR', import_template_slug: 'cpor_historical_cases' }];
      }
      if (String(path).includes('/profiles')) {
        return {
          profiles: [
            {
              id: 1,
              profile_code: 'asus_default',
              display_name: 'ASUS default',
              column_map_json: { case_code: ['Case ID'], sales_model: ['Sales Model Name'] },
              sheet_roles_json: {},
              is_default: true,
            },
          ],
        };
      }
      return { items: [], total: 0, page: 1, page_size: 500, status_counts: {} };
    }),
  };
});

function wrap(ui: ReactElement) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe('CporHistoricalImportPage', () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    navState.search = '';
  });

  it('default lens is the plan templates surface, not the upload wizard', async () => {
    wrap(<CporHistoricalImportPage />);
    expect(await screen.findByTestId('plan-templates')).toBeInTheDocument();
    expect(screen.getByTestId('template-learn')).toBeInTheDocument();
    expect(screen.queryByTestId('cpor-historical-upload-step')).not.toBeInTheDocument();
  });

  it('learn=1 is upload CTA with no mapping table', async () => {
    navState.search = 'learn=1';
    wrap(<CporHistoricalImportPage />);
    expect(await screen.findByTestId('cpor-historical-upload-step')).toBeInTheDocument();
    expect(screen.getByTestId('cpor-historical-file')).toBeInTheDocument();
    expect(screen.getByTestId('cpor-historical-upload')).toBeInTheDocument();
    expect(await screen.findByTestId('cpor-historical-profile-summary')).toBeInTheDocument();
    expect(screen.queryByTestId('cpor-historical-advanced-mapping')).not.toBeInTheDocument();
    expect(screen.queryByTestId('cpor-historical-samples-Case ID')).not.toBeInTheDocument();
  });
});
