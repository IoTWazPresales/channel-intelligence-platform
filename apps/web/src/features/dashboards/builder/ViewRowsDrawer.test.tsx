import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { builderCatalog as catalog } from '@/design-lab/fixtures/builder';
import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { V2ExecutorProvider } from './BuilderData';
import { requestFor } from './requestFor';
import type { DefinitionV2, V2Response } from './types';
import { ViewRowsDrawer } from './ViewRowsDrawer';

vi.mock('@/components/EnterpriseDataGrid', () => ({ EnterpriseDataGrid: () => <div>Grouped rows</div> }));

describe('drill-down totals', () => {
  it.each(['dsi_sellout.units', 'cst_sellthrough.reported_soh', 'cpor.delivery_rate'])(
    'labels the total at the drill grouping without asserting widget equality: %s',
    async (measure) => {
      const def: DefinitionV2 = { v: 1, query: { measures: [measure] } };
      const response: V2Response = {
        ok: true, columns: [], rows: [{ [measure]: 44 }], totals: { [measure]: 44 }, truncated: false, refusals: [],
      };
      const execute = vi.fn().mockResolvedValue(response);
      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      renderWithProviders(
        <QueryClientProvider client={qc}>
          <V2ExecutorProvider execute={execute}>
            <ViewRowsDrawer open onClose={() => undefined} def={def} plan={requestFor(def, { catalog, filters: {}, window: null })} catalog={catalog} title="Figure" dashboardName="Board" />
          </V2ExecutorProvider>
        </QueryClientProvider>,
      );
      const footer = await screen.findByTestId('view-rows-footer');
      expect(footer).not.toHaveTextContent(/match(es)? the widget/i);
      expect(footer).toHaveTextContent('Total at this grouping:');
      expect(screen.getByTestId('view-rows-heading')).toHaveTextContent('not single transactions');
      expect(execute).toHaveBeenCalledOnce();
    },
  );
});
