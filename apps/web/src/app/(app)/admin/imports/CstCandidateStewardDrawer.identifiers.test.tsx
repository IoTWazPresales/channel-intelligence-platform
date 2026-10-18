import { screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { CstCandidateStewardDrawer } from './CstCandidateStewardDrawer';
import type { CstMappingCandidate } from './cstImportSteward.config';

vi.mock('@/lib/api', () => ({
  apiGet: vi.fn(async () => ({ items: [] })),
  safeDisplayError: (e: unknown) => (e instanceof Error ? e.message : String(e)),
}));

function candidate(context: Record<string, unknown> | null): CstMappingCandidate {
  return {
    id: 1,
    import_job_id: 9,
    entity_type: 'cst_product_token',
    normalized_key: '90nb1',
    row_count: 2,
    total_units: 10,
    sample_raw_values: ['90NB1'],
    status: 'needs_review',
    suggestions: [],
    context,
  };
}

function renderDrawer(c: CstMappingCandidate, entity: 'product' | 'location' = 'product') {
  return renderWithProviders(
    <CstCandidateStewardDrawer
      candidate={c}
      entity={entity}
      customerId={20}
      onClose={vi.fn()}
      onResolve={vi.fn(async () => undefined)}
      onIgnore={vi.fn(async () => undefined)}
    />,
  );
}

describe('CstCandidateStewardDrawer: every identifier the rows carried (N-0111, 2026-10-19)', () => {
  it('lists each identifier of a row with what it matched, and warns when they disagree', () => {
    renderDrawer(
      candidate({
        identifier_conflict_rows: 1,
        identifier_rows: [
          {
            identifiers: { part_number: '90NB1', barcode: '4711000000028', customer_code: 'ART-7' },
            tier: 'identifier_conflict',
            matched: [
              { slot: 'part_number', token: '90NB1', status: 'unique', tier: 'part_number', product_ids: [11] },
              { slot: 'barcode', token: '4711000000028', status: 'unique', tier: 'ean', product_ids: [12] },
              { slot: 'customer_code', token: 'ART-7', status: 'no_match', tier: null, product_ids: [] },
            ],
          },
        ],
      }),
    );
    expect(screen.getByTestId('cst-import-identifier-conflict')).toHaveTextContent(
      '1 row carries identifiers that point at different products',
    );
    const box = screen.getByTestId('cst-import-identifiers');
    expect(within(box).getByText(/Part number:/)).toHaveTextContent('90NB1');
    expect(within(box).getByText(/Part number:/)).toHaveTextContent('matches product 11 (part_number)');
    expect(within(box).getByText(/Barcode:/)).toHaveTextContent('4711000000028');
    expect(within(box).getByText(/Barcode:/)).toHaveTextContent('matches product 12 (ean)');
    expect(within(box).getByText(/Customer product code:/)).toHaveTextContent('no match');
  });

  it('shows nothing extra for a candidate without identifier rows', () => {
    renderDrawer(candidate(null));
    expect(screen.queryByTestId('cst-import-identifiers')).toBeNull();
    expect(screen.queryByTestId('cst-import-identifier-conflict')).toBeNull();
  });

  it('is not shown for a location candidate', () => {
    renderDrawer(candidate({ identifier_rows: [{ identifiers: { part_number: 'X' } }] }), 'location');
    expect(screen.queryByTestId('cst-import-identifiers')).toBeNull();
  });
});
