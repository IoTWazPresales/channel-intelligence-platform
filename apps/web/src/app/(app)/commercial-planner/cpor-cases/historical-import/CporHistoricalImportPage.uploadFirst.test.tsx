import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactElement } from 'react';

import CporHistoricalImportPage from './page';

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
      return {};
    }),
  };
});

function wrap(ui: ReactElement) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe('CporHistoricalImportPage upload-first', () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
  });

  it('first paint is upload CTA with no mapping table', async () => {
    wrap(<CporHistoricalImportPage />);
    expect(await screen.findByTestId('cpor-historical-upload-step')).toBeInTheDocument();
    expect(screen.getByTestId('cpor-historical-file')).toBeInTheDocument();
    expect(screen.getByTestId('cpor-historical-upload')).toBeInTheDocument();
    expect(await screen.findByTestId('cpor-historical-profile-summary')).toBeInTheDocument();
    expect(screen.queryByTestId('cpor-historical-advanced-mapping')).not.toBeInTheDocument();
    expect(screen.queryByTestId('cpor-historical-samples-Case ID')).not.toBeInTheDocument();
  });
});
