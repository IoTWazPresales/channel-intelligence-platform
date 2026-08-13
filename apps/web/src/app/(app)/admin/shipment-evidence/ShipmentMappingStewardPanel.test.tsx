import type { ReactElement } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';

import { ShipmentMappingStewardPanel } from './ShipmentMappingStewardPanel';
import type { ShipmentMappingCandidateRow } from './shipmentMappingCandidateDisplay';
import { ShipmentStewardActionsProvider } from './shipmentStewardRowActions';

const apiPost = vi.fn();
const apiGet = vi.fn(async () => ({ items: [] }));

vi.mock('@/lib/api', () => ({
  apiPost: (...args: unknown[]) => apiPost(...args),
  apiGet: (...args: unknown[]) => apiGet(...args),
  safeDisplayError: (e: unknown) => (e instanceof Error ? e.message : String(e ?? 'error')),
}));

function wrap(ui: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ShipmentStewardActionsProvider importJobId={9} onInvalidate={() => undefined}>
        {ui}
      </ShipmentStewardActionsProvider>
    </QueryClientProvider>
  );
}

function customerRow(overrides: Partial<ShipmentMappingCandidateRow> = {}): ShipmentMappingCandidateRow {
  return {
    id: 102,
    import_job_id: 9,
    entity_type: 'shipment_customer_token',
    normalized_key: 'takealot',
    row_count: 1,
    total_units: 1,
    total_reported_value: 10,
    sample_raw_values: ['Q2 Takealot'],
    suggested_entity_id: null,
    suggested_distributor_code: null,
    suggested_distributor_name: null,
    suggested_customer_code: null,
    suggested_customer_name: null,
    suggested_action: 'create_provisional_customer',
    match_reason: 'no_alias_or_exact_dim_match',
    confidence_score: 0.2,
    status: 'needs_review',
    context: {
      line_ids: [3],
      suggested_name: 'Takealot',
      possible_duplicate_of: ['takealot-marketplace'],
    },
    ...overrides,
  };
}

describe('ShipmentMappingStewardPanel duplicate review', () => {
  beforeEach(() => {
    apiPost.mockReset();
    apiPost.mockResolvedValue({ ok: true, candidate_id: 102, message: 'stamped' });
  });

  it('renders Same/Different actions for unresolved duplicate hints', () => {
    wrap(<ShipmentMappingStewardPanel candidate={customerRow()} />);
    expect(screen.getByTestId('shipment-possible-duplicates')).toBeTruthy();
    expect(screen.getByTestId('shipment-duplicate-same-entity')).toBeTruthy();
    expect(screen.getByTestId('shipment-duplicate-different-entity')).toBeTruthy();
  });

  it('posts different-entity review to shipment-evidence API', async () => {
    const onInvalidate = vi.fn();
    const onFast = vi.fn();
    wrap(
      <ShipmentMappingStewardPanel
        candidate={customerRow()}
        onInvalidate={onInvalidate}
        onStewardFastComplete={onFast}
      />
    );
    fireEvent.click(screen.getByTestId('shipment-duplicate-different-entity'));
    await waitFor(() => expect(apiPost).toHaveBeenCalled());
    expect(apiPost.mock.calls[0][0]).toContain(
      '/api/v1/shipment-evidence/import-candidates/102/duplicate-review/different-entity'
    );
    expect(apiPost.mock.calls[0][1]).toEqual({ peer_normalized_key: 'takealot-marketplace' });
    await waitFor(() => expect(onFast).toHaveBeenCalledWith([102]));
    expect(onInvalidate).toHaveBeenCalled();
  });

  it('posts same-entity review without eviction', async () => {
    const onInvalidate = vi.fn();
    const onFast = vi.fn();
    wrap(
      <ShipmentMappingStewardPanel
        candidate={customerRow()}
        onInvalidate={onInvalidate}
        onStewardFastComplete={onFast}
      />
    );
    fireEvent.click(screen.getByTestId('shipment-duplicate-same-entity'));
    await waitFor(() => expect(apiPost).toHaveBeenCalled());
    expect(apiPost.mock.calls[0][0]).toContain('duplicate-review/same-entity');
    await waitFor(() => expect(onInvalidate).toHaveBeenCalled());
    expect(onFast).not.toHaveBeenCalled();
  });

  it('hides Same/Different once a decision exists', () => {
    wrap(
      <ShipmentMappingStewardPanel
        candidate={customerRow({
          context: {
            possible_duplicate_of: ['takealot-marketplace'],
            duplicate_review: { decision: 'same_entity' },
          },
        })}
      />
    );
    expect(screen.getByTestId('shipment-possible-duplicates')).toBeTruthy();
    expect(screen.queryByTestId('shipment-duplicate-same-entity')).toBeNull();
    expect(screen.getByText(/Steward decision/i)).toBeTruthy();
  });
});
